# AlphaLayer ↔ LoopX Integration — Design

_Date: 2026-08-06 · Status: approved, not yet implemented · Spec 1 of 2 (Spec 2: Codexia ↔ LoopX)_

## Summary

Give an AlphaLayer `Flow` durable, gated, multi-day unattended execution by letting
[LoopX](https://github.com/connorodea/loopx) (a deterministic, no-LLM local control plane
for long-running agent work) drive it one bounded stage per external "tick." No change to
AlphaLayer's existing tested behavior; two additive pieces plus a new CLI subcommand.

## Background / motivation

AlphaLayer's `Flow.run(resume=True)` already models "resumable, artifact-backed progress
across fresh processes" — but a single call still executes every remaining stage in one
shot. LoopX's own documented integration contract ("Direct CLI orchestration," see
`docs/guides/custom-agent-runner-integration.md` in the LoopX repo) expects a host to
perform exactly *one bounded action* per wake: `quota should-run` → claim → execute → 
validate → writeback → `spend-slot` → apply a scheduler hint. AlphaLayer needs a
single-stage execution primitive to fill that "one bounded action" slot; today it has none.

This is the smaller, lower-risk half of a two-part integration (see `VISION.md`'s
roadmap). It touches only the AlphaLayer repo and uses LoopX exclusively through its
documented, stable CLI surface — no code changes to the LoopX fork itself, no dependency
on LoopX's internal Python modules.

## Non-goals

- Not a LoopX "domain capability" (i.e. not built inside the LoopX package using its
  internal Capability/Provider interfaces). That's a heavier, more tightly-coupled
  alternative considered and rejected for v1 — see the chat discussion preceding this
  spec for the tradeoff.
- Not a scheduler. `LoopXRunner` performs one tick when called; owning wakeups (cron,
  Claude Code's native `/loop`, or Codexia's automation scheduler in Spec 2) is the
  caller's job, per LoopX's own "your runner owns wakeups" boundary.
- Not a change to `Flow.run()`'s existing signature or behavior for non-LoopX callers.

## Architecture

### 1. `Flow.step()` (`src/alphalayer/flow.py`)

```python
def step(self, *inputs: Artifact, resume: bool = True) -> Artifact | None:
    """Execute exactly the next stage whose artifact isn't already on disk, and return
    it. Returns None once every stage is resolved. Stateless across calls — re-derives
    "what's next" from disk each time, so a fresh process picking up mid-Flow (the
    per-tick case) needs no in-memory state carried over from a prior call."""
```

Implementation approach: extract the current per-stage execution body of `run()` — run
the stage, stamp `flow`/`stage`/`layer`/`upstream`, save to `<NN>-<stage-name>.md` — into
a private `_run_one_stage(index, stage, produced) -> Artifact` helper. `run()` keeps its
existing loop-every-stage control flow, now calling the shared helper (pure refactor, no
behavior change — existing `test_flow.py` cases must pass unmodified). `step()` is new:
it walks stages from index 0, and for each one whose `out_path` already exists on disk
*and* `resume=True`, loads it via `Artifact.load` and continues; the first stage without
an on-disk artifact is executed via `_run_one_stage` and returned immediately without
looking at any further stages. If every stage already has an on-disk artifact, returns
`None`.

`resume=False` on `step()` always (re-)executes the first stage in the list — it exists
for signature symmetry with `run()`, but `step()` is intended to be called with
`resume=True` (the default) for real, cross-process ticking. Document this explicitly in
the docstring so a caller doesn't expect `resume=False` to "advance" anything across
repeated calls.

### 2. `LoopXRunner` (new `src/alphalayer/loopx.py`)

Stdlib-only — no new dependency. Shells out to the `loopx` binary via `subprocess` with
`--format json`; checks `shutil.which("loopx")` at construction and raises a clear
`LoopXNotInstalledError` (new exception in `exceptions.py`) if missing, rather than
failing confusingly deep in a subprocess call.

```python
@dataclass
class TickResult:
    ran: bool                       # False if should-run said not to act
    artifact: Artifact | None       # the stage artifact produced this tick, if any
    flow_complete: bool             # True if step() returned None (nothing left to run)
    reason: str | None              # why ran=False, or None
    scheduler_hint: dict | None     # the should-run packet's scheduler hint, for the caller to apply

class LoopXRunner:
    def __init__(self, flow: Flow, *, goal_id: str, agent_id: str = "alphalayer",
                 available_capabilities: Sequence[str] = ("shell",)) -> None: ...

    def tick(self, *inputs: Artifact) -> TickResult: ...
    def run_to_completion(self, *inputs: Artifact, poll_interval: float | None = None) -> list[TickResult]: ...
```

`tick()` sequence:

1. `loopx --format json quota should-run --goal-id <goal_id> --agent-id <agent_id> --available-capability shell` — parse JSON. If not runnable, return `TickResult(ran=False, reason=<from packet>, scheduler_hint=<hint if present>)` without claiming or spending anything.
2. `loopx todo claim` for the todo id selected by the should-run packet.
3. `artifact = flow.step(*inputs, resume=True)`.
   - If `None`: the Flow was already fully complete before this tick. Call `loopx todo complete` (not `update`), `refresh-state`, `spend-slot`, and return `TickResult(ran=True, artifact=None, flow_complete=True, ...)`.
4. Validate: the postcondition here is simply "the artifact file exists on disk" — `Flow.step()` only returns after `Artifact.save()` succeeds, so this is effectively free; no separate validation pass needed for v1.
5. Write compact evidence — `"<schema>@stage<N> -> <artifact.path>"`, **not** the full artifact content, per LoopX's "compact run history" evidence guidance — via `loopx todo update` if more stages remain after this one, or `loopx todo complete` if this was the last stage (compare `artifact.stage` to `len(flow.stages) - 1`).
6. `loopx refresh-state`.
7. `loopx quota spend-slot`.
8. Return `TickResult(ran=True, artifact=artifact, flow_complete=<last stage?>, scheduler_hint=<from step 1's packet>)`.

`run_to_completion()` is an explicitly secondary convenience for simple/dev hosts (e.g. a
one-off script): loops `tick()` until `flow_complete` or a non-runnable result, optionally
sleeping `poll_interval` between ticks. It is **not** the recommended integration surface
for a real host — LoopX's own design principle is that the *runner* owns wakeups, so a
real host (Claude Code's `.claude/loop.md`, a cron job, or Codexia's scheduler in Spec 2)
should call one tick per external wake via the CLI, not have AlphaLayer loop internally.

### 3. CLI: `alphalayer loopx-tick`

```
alphalayer loopx-tick <module:flow-attribute> --goal-id <id> [--agent-id <id>] [--seed PATH]...
```

Thin wrapper: loads the Flow via the existing `_load_flow` helper, loads any `--seed`
artifacts via the existing `Artifact.load`, constructs a `LoopXRunner`, calls `.tick()`
once, and prints a one-line human-readable summary (ran/not, stage, schema, artifact
path, `flow_complete`, scheduler hint). Exit code 0 whenever the tick was *attempted*
regardless of `ran` (a quiet/wait result is a normal outcome, not a failure); nonzero only
for infrastructure failure (missing binary, malformed CLI response, an unhandled
exception from the stage itself).

## Data flow

```
external wake (Claude Code /loop tick, cron, Codexia automation task)
  -> `alphalayer loopx-tick <flow> --goal-id <id>`
     -> LoopXRunner.tick()
        -> loopx quota should-run   (JSON packet: runnable? which todo? scheduler hint?)
        -> loopx todo claim
        -> Flow.step(resume=True)  -> one stage's Artifact, saved to docs/flows/<name>/<NN>-<stage>.md
        -> loopx todo update|complete  (evidence = compact pointer to the artifact path)
        -> loopx refresh-state
        -> loopx quota spend-slot
  <- TickResult (ran, artifact, flow_complete, scheduler_hint) printed / returned
next external wake applies scheduler_hint, repeats
```

## Error handling

- Missing `loopx` binary → `LoopXNotInstalledError` at construction time, not a buried
  subprocess `FileNotFoundError`.
- Any `loopx` CLI call returning non-zero exit or malformed JSON → treated as an
  infrastructure failure and propagated (fail loud/closed, matching LoopX's own
  `--harden` adapter philosophy) — never silently treated as "nothing to do."
- A stage raising during `flow.step()` → propagates normally, exactly as `run()` does
  today. The todo is left un-claimed-complete for this tick (no evidence write happens
  for a failed stage), so the next tick's `should-run` → claim → `step()` naturally
  retries the same stage. No bespoke retry/backoff logic in v1.
- Concurrent ticks (two hosts ticking the same goal): entirely LoopX's responsibility via
  `todo claim` semantics ("two Agents cannot silently claim the same work" is LoopX's own
  acceptance criterion). `LoopXRunner` adds no locking of its own.

## Testing

- `Flow.step()`: new cases alongside `tests/test_flow.py` — repeated `step()` calls reach
  the same final state as one `run()` call; `step()` returns `None` once exhausted;
  `resume=True` correctly skips stages with an existing on-disk artifact; `run()`'s
  existing test cases pass unmodified (proves the refactor didn't change behavior).
- `LoopXRunner`: shells out to a real binary, so tests use a small fake `loopx` script
  placed on `PATH` (via a pytest fixture/`monkeypatch`) that echoes canned JSON packets
  for `should-run`/`todo`/`refresh-state`/`spend-slot` — keeps the test suite dependency-
  free rather than requiring a real LoopX install + goal state. Cases: `should-run: false`
  short-circuits without claiming or spending; happy-path single-stage tick; last-stage
  tick calls `todo complete` not `update`; already-complete Flow ticks straight to
  `todo complete` without running a stage; missing `loopx` binary raises
  `LoopXNotInstalledError`.
- CLI: extend `tests/test_cli.py` with a `loopx-tick` case using the same fake-binary
  fixture, asserting exit code and summary line.

## Open implementation questions

- Exact `loopx todo claim` / `todo update` / `todo complete` flag names (todo id
  parameter name, evidence flag name, etc.) need confirming against a live `loopx --help`
  / `loopx todo --help` at implementation time — this design was written against a cloned
  snapshot of the LoopX docs, not a live install, and the docs describe the contract
  conceptually rather than as an exhaustive CLI reference.
- Whether `--agent-id` should default to a stable value (`"alphalayer"`) or be required —
  leaning default-with-override, confirm no LoopX convention conflicts with that at
  implementation time.

## Relationship to Spec 2 (Codexia ↔ LoopX)

Spec 2 will document Codexia's automation scheduler as another LoopX "runner" — its
`AutomationTask.prompt` field, for a project using AlphaLayer, would itself invoke
`alphalayer loopx-tick <flow> --goal-id <id>` as its one bounded action per cron wake.
Spec 2 depends on this spec's CLI subcommand existing but requires no changes to it.
