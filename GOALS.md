# AlphaLayer — Goals (north-star cascade)

> North star: turn a library of one-shot skills into composable, resumable,
> artifact-audited pipelines — walkable by hand in a conversation today, driven unattended
> by a control plane tomorrow.
> Source: VISION.md (v1.1) · _Last updated: 2026-08-06 · Plan version: v3_

## Alignment anchors (every goal must serve these)

**Pillars:**
- Stdlib-only core; vendor SDKs are opt-in extras, never forced.
- No hidden control flow — a Flow is a straight-line stage sequence.
- Markdown by default, not a rigid schema language.
- **One Artifact format, two runtimes** — the contract must read the same whether a stage
  runs by hand (interactive Claude Code) or headless (script/control-plane).
- Not a general workflow engine (fan-out/parallelism stays the `Workflow` tool's job).
- Not a scheduler or durable-state store — multi-day state is deferred to an external
  control plane (LoopX), not reinvented here.

**Non-goals (out of scope now):** a GUI/dashboard; cross-flow/cross-project reporting;
backends beyond Anthropic/OpenAI; parallel/fan-out stage execution.

**MVP boundary:** Core (Skill/Layer/Flow, Artifact Contract, CLI, two backend bridges,
Claude Code skill form) is built and shipped. Unattended/scheduled execution is actively
moving from "out" to "in" via Goals 1–2 below.

## Goals

### Goal 1 — A Flow can run unattended across days, gated by LoopX · serves: core value prop + "one contract, two runtimes"
**Done when:** `alphalayer loopx-tick` advances a real multi-stage Flow one stage per
tick against a live LoopX goal, end to end, with `Flow.step()`/`LoopXRunner`/CLI all
covered by passing tests. This is Spec 1 (`docs/superpowers/specs/
2026-08-06-loopx-integration-design.md`) — already designed and approved; this goal is
its execution.
**Status:** in-progress
**Sub-goals:**
- [x] **1a** Implement `Flow.step()` (extract `_run_one_stage` helper; `run()` unchanged
  behavior) — _advances:_ gives LoopX a single-stage execution primitive — _accept:_ new
  `test_flow.py` cases pass, existing ones pass unmodified.
- [x] **1b** Implement `LoopXRunner` + `TickResult` + `LoopXNotInstalledError` in new
  `src/alphalayer/loopx.py` — _advances:_ implements the documented LoopX "Direct CLI
  orchestration" tick sequence — _accept:_ fake-`loopx`-binary test suite covers
  should-run=false short-circuit, happy path, last-stage-completes, already-complete flow,
  missing binary.
- [x] **1c** Implement `alphalayer loopx-tick` CLI subcommand — _advances:_ the actual
  integration surface a runner (Claude Code `/loop`, cron, Codexia) invokes — _accept:_
  `test_cli.py` case passes; exit codes match the spec's contract.
- [ ] **1d** Verify real `loopx todo claim/update/complete` flag names against a live
  `loopx --help` and reconcile with 1b — _advances:_ resolves the spec's two open
  implementation questions — _accept:_ `LoopXRunner` calls match the real CLI, not just
  the docs snapshot.
- [ ] **1e** End-to-end smoke: tick a real 2+ stage Flow against a live local LoopX goal
  across multiple ticks — _advances:_ proves the whole chain, not just unit tests —
  _accept:_ the Flow reaches completion purely via repeated `loopx-tick` calls.
**Loop:** N/A — one-and-done per Spec 1; becomes done when 1a–1e are all checked.

### Goal 2 — Codexia's scheduler can wake and tick a Flow, no core changes to its job model · serves: unattended-execution reach + "AlphaLayer stays agnostic to whichever scheduler drives it"
**Done when:** a real Codexia `AutomationTask` (prompt = a one-shot LoopX-tick
instruction) advances a live Flow across multiple scheduled wakes. Spec 2 exists as a
**draft** (`docs/superpowers/specs/2026-08-06-codexia-loopx-integration-design.md`),
produced unattended without the usual interactive approval gate — **blocked on
Connor's review** before 2b/2c/2d proceed.
**Status:** blocked (spec drafted, awaiting review)
**Sub-goals:**
- [x] **2a** Brainstorm + write the Spec 2 design doc (tick-prompt skill content, and
  whether to pursue the optional `should-run` pre-flight patch in Codexia's
  `execution.rs`) — _advances:_ mirrors Spec 1's process for the second integration —
  _accept:_ spec committed, same self-review bar as Spec 1. Committed as a **draft**
  (no interactive approval ran — see spec header's provenance note and its 4 "Open
  questions for Connor"). Treat as incomplete until reviewed, not as approved.
- [ ] **2b** Author the reusable "run one LoopX tick" prompt/skill that a Codexia
  `AutomationTask.prompt` references — _advances:_ keeps the automation task's prompt
  field small and stable regardless of project/goal — _accept:_ works for both `agent:
  codex` and `agent: cc` task types per Codexia's model.
- [ ] **2c** *(stretch, only if 2a recommends it)* Implement the `should-run` pre-flight
  check in `execution.rs::execute_task` — _advances:_ avoids burning a full agent session
  on a quiet/wait tick — _accept:_ contained diff, doesn't touch `run_task_with_cc`/
  `run_task_with_codex` internals.
- [ ] **2d** End-to-end smoke: a configured Codexia automation task ticks a real Flow
  across several cron wakes — _advances:_ proves the GUI/cron path, not just the CLI path
  — _accept:_ observed in Codexia's own run history / `automation_runs`.
**Loop:** N/A.

### Goal 3 — Claude-facing docs and the Python package never drift back apart · serves: "one contract, two runtimes" (ongoing, not one-shot)
**Done when:** N/A — this is a loop, not a one-shot outcome.
**Status:** ongoing
**Loop:** each cycle → diff `SKILL.md` / `references/artifact-contract.md` / `README.md`
against the package's actual CLI flags and public API (especially right after Goals 1–2
land new commands like `loopx-tick`); fix any mismatch found; stop this cycle when a full
pass finds zero mismatches. Re-run this check after every Goal 1/2 sub-goal that changes
the CLI or public API — don't wait for a scheduled audit.

### Goal 4 — A second proven, reusable Flow exists beyond prod-readiness-remediation · serves: core value prop generalization
**Done when:** a second named Flow (candidate: an SEO pipeline or the AIWholesail
dev-tracker sync — both already exist as recurring manual processes per Connor's other
projects) is defined, runs via `alphalayer run`, and is documented alongside the
reference example.
**Status:** todo (Later — not started)
**Sub-goals:**
- [ ] **4a** Pick the second Flow candidate and confirm its stages already exist as
  Skills/Layers (or identify the gap).
- [ ] **4b** Wire it as a Flow, run it end-to-end, document it in
  `~/.claude/skills/alphalayer/flows/`.

### Goal 5 — A conscious, resourced decision on OSS distribution · serves: resolving VISION.md open question #1
**Done when:** VISION.md's open question ("internal tool or real OSS project?") is
explicitly answered and documented; if OSS, the packaging/docs gap to a real release is
closed (PyPI publish, CONTRIBUTING polish); if internal, public-facing polish is
explicitly deprioritized rather than silently drifting.
**Status:** todo (Later — not started, blocked on a decision only Connor can make)

## Sequencing

- **Now:** Goal 1 (Spec 1 execution — starting immediately, see below) running alongside
  Goal 3's loop (check docs stay in sync as Goal 1's sub-goals land).
- **Next:** Goal 2 (Spec 2 — Codexia integration), once Goal 1 ships.
- **Later:** Goal 4 (second Flow), Goal 5 (OSS decision) — both explicitly deferred in
  VISION.md's own roadmap; not started until Now/Next clear.

## Drift watch

- `~/.claude/skills/alphalayer/templates/{LAYER_TEMPLATE,FLOW_TEMPLATE}.md` are
  superseded (per today's decision to point authoring at `alphalayer new-layer`/
  `new-flow`) but still physically present, left in place rather than deleted since
  `~/.claude/skills` isn't under version control. Not a blocker, but worth a deliberate
  cleanup decision later rather than leaving it indefinitely orphaned.
- No other backlog/in-progress items currently found outside these goals.

## Runnable prompts

```text
/goal Goal 1: A Flow can run unattended across days, gated by LoopX
Serves vision pillar: core value prop + "one contract, two runtimes". Done when:
`alphalayer loopx-tick` advances a real multi-stage Flow one stage per tick against a
live LoopX goal, end to end, with Flow.step()/LoopXRunner/CLI all covered by passing
tests. Non-goals: no LoopX fork changes, no scheduler ownership in AlphaLayer itself.
Read GOALS.md, VISION.md, and docs/superpowers/specs/2026-08-06-loopx-integration-design.md
first. Acceptance checks: new + existing test suites pass; a real 2+ stage Flow reaches
completion via repeated `loopx-tick` calls against a live LoopX goal. Report what shipped
and what's left.
```

```text
/sub-goal 1a: Implement Flow.step()
Parent goal: Goal 1. Advances it by: gives LoopX a single-stage execution primitive to
tick against.
Acceptance criteria: extract `_run_one_stage` helper from `run()`'s current per-stage
body; add `step(*inputs, resume=True) -> Artifact | None`; existing test_flow.py cases
pass unmodified; new cases cover step-by-step equals run()'s final state, None once
exhausted, resume-skip behavior.
Dependencies: none — first sub-goal in the chain.
Smallest correct production-grade change; validate with pytest; report the diff.
```

```text
/loop Goal 3 — keep docs and package in sync
Each cycle: re-read GOALS.md + VISION.md + the current state of SKILL.md /
artifact-contract.md / README.md against the package's actual CLI (`alphalayer --help`)
and public API (`alphalayer/__init__.py`'s `__all__`). Fix any mismatch found — prefer
updating docs to match shipped behavior, not the reverse, unless the mismatch reveals a
real API gap. Check against pillar: "one contract, two runtimes" — the docs must describe
what's actually true of the package today. Report what was found/fixed. Stop when: a full
pass finds zero mismatches two cycles in a row, or there's no unresolved Goal 1/2
sub-goal left to trigger a re-check.
```

## Changelog

- 2026-08-06 v3 — Sub-goal 2a: Spec 2 (Codexia↔LoopX) drafted unattended during a
  `/loop` tick — no interactive approval ran, so it's marked blocked/draft, not done.
  4 open questions for Connor in the spec itself. 2b/2c/2d do not proceed until
  reviewed.
- 2026-08-06 v2 — Sub-goals 1a–1c shipped (Flow.step(), LoopXRunner, alphalayer
  loopx-tick, all with passing tests; 47/47 suite green, ruff + mypy strict clean). 1d/1e
  need a live LoopX install and remain open — see Sequencing.
- 2026-08-06 v1 — Initial cascade from VISION.md v1.1. Goal 1 (Spec 1 execution) starts
  immediately; Goal 3 (docs/package sync) runs as a background loop alongside it.
