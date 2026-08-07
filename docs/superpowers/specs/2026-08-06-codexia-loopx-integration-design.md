# Codexia ↔ LoopX Integration — Design

_Date: 2026-08-06 · Status: **DRAFT — pending Connor's review, not yet approved** · Spec 2 of 2 (Spec 1: AlphaLayer ↔ LoopX, shipped/merged to main)_

> **Provenance note:** this draft was produced during an unattended `/loop` tick
> (Goal 2, sub-goal 2a), reusing the Codexia research already done earlier in this
> session rather than a fresh interactive brainstorm — there was no one present to
> answer clarifying questions. It follows the same structure/rigor as Spec 1, but
> **the brainstorming skill's normal back-and-forth approval gate has not run.**
> Nothing past this document should be implemented until Connor reviews it — see
> "Open questions for Connor," below, and treat sub-goal 2b/2c/2d as blocked on that
> review, not as approved next steps.

## Summary

Let [Codexia](https://github.com/connorodea/codexia-task-management)'s Automation
Scheduler act as a second LoopX "runner" (alongside Claude Code's native `/loop`,
already covered by Spec 1's `alphalayer loopx-tick`), so a LoopX-gated AlphaLayer Flow
can also be advanced by a GUI-configured, cron-driven task instead of only an
interactively-started `/loop` session.

## Background

Codexia's `AutomationTask` (`crates/cc/src/automation/model.rs`) already wakes on a
cron schedule, spins up a **fresh** Codex or Claude Code session in a target project
directory, sends `task.prompt` as a single message/turn, and disconnects
(`crates/cc/src/automation/execution.rs::execute_task`). That one-shot-per-wake shape
is exactly LoopX's documented "custom host" runner contract from
`docs/guides/custom-agent-runner-integration.md` (wake → one bounded action → apply
scheduler hint → next wake) — not the native `/loop` adapter, which loops *inside* one
session.

## Non-goals

- Not a change to Codexia's core job model (`AutomationTask`'s fields, scheduling, or
  session-launch mechanics) — the base integration is prompt content only.
- Not a fork of Codexia for AlphaLayer-specific purposes — any code change (2c) stays
  a small, contained, upstream-mergeable-shaped diff to `execution.rs`, not a
  divergent branch.
- Not a replacement for Spec 1's `alphalayer loopx-tick` — Codexia is a *caller* of
  that CLI command, identical to how a cron job or Claude Code's `/loop` would call it.

## Architecture

### 1. Base integration — a prompt template, no Codexia code changes

Codexia's `AutomationTask.prompt` is arbitrary text sent as the first turn to a fresh
Codex or Claude Code session, with `cwd` already set to the target project directory.
The entire base integration is therefore just the *content* of that prompt — no new
Claude Code skill file, no Codexia code change:

```text
Run `alphalayer loopx-tick <module:flow-attribute> --goal-id <goal-id>` in this
directory via the shell. Report its one-line output, then stop — do nothing else
and ask nothing else.
```

Filled in per project/goal when the `AutomationTask` is created (e.g. `alphalayer
loopx-tick myflows.digest:flow --goal-id nightly-digest`). This works unmodified for
both `agent: "cc"` (Claude Code, via its Bash tool) and `agent: "codex"` (Codex CLI,
via its shell tool) task types — satisfying sub-goal 2b's acceptance criterion without
adding a maintained skill file, since the instruction is short and stable enough to
just template directly into Codexia's UI.

**Considered and rejected:** a dedicated Claude Code skill/slash-command (e.g.
`/loopx-tick-runner`) that Codexia's prompt would reference instead of the raw Bash
instruction. Rejected for v1 as unnecessary indirection — the raw instruction is
already short, and a skill file would be one more thing to keep in sync across two
repos for no behavioral gain. Revisit only if the raw-prompt approach proves flaky in
practice (2d will surface that, if so).

### 2. Optional: `should-run` pre-flight in `execution.rs` (sub-goal 2c)

`execute_task` currently fires unconditionally on schedule — even when LoopX's
`should_run` would say "quiet/wait," Codexia still spins up a full session, sends the
prompt, and only *inside* that session does `alphalayer loopx-tick` discover there's
nothing to do (a cheap, fast exit, but not free — session connect/disconnect and at
least one model turn are still spent). A pre-flight check in `execute_task`, before
dispatching to `run_task_with_cc`/`run_task_with_codex`, would shell out to `loopx
quota should-run` and skip the session entirely on a non-runnable result.

This is a genuinely optional enhancement (GOALS.md already scoped it as "stretch,
only if 2a recommends it") — **this draft's recommendation is yes, pursue it**, since
the diff is small and contained (wraps the existing dispatch, touches neither
`run_task_with_cc` nor `run_task_with_codex` internals), but it's a code change to a
third-party fork rather than a prompt template, which is a different and larger kind
of commitment than anything Spec 1 required. Flagged explicitly below for Connor's
go-ahead rather than assumed.

## Data flow

```
Codexia cron wake (AutomationTask.schedule)
  -> execute_task
     -> [2c, if pursued] loopx quota should-run --goal-id <id>  -- skip session if not runnable
     -> run_task_with_cc / run_task_with_codex
        -> fresh session, cwd = task.projects[i]
        -> sends task.prompt = "Run `alphalayer loopx-tick ...`. Report, then stop."
           -> agent runs the shell command -> LoopXRunner.tick() (Spec 1) -> one Flow stage
        -> session disconnects
  <- automation_runs record (Codexia's own run history)
next cron wake repeats
```

## Error handling

- If `alphalayer` or `loopx` aren't installed in the target environment, the agent's
  shell command fails visibly in that turn — surfaces in Codexia's own
  `automation_runs` failure state (`mark_run_status_by_session(..., "failed")`),
  which is already wired. No new error path needed on AlphaLayer's side.
- If 2c is pursued and `loopx quota should-run` itself fails (LoopX not installed,
  infra error) rather than returning a clean "not runnable," the pre-flight check
  should fail *open* (still launch the session) rather than silently skipping a wake
  — the reverse of `LoopXRunner`'s own fail-closed rule, because here the fallback
  (an unnecessary session) is cheap and reversible, while fail-closed (silently never
  running) would be a much harder failure to notice from Codexia's UI. This is the
  one deliberate asymmetry from Spec 1's error philosophy — flagged as an open
  question below rather than assumed correct.

## Testing

- Prompt-template approach (2b): no unit tests possible (it's operator-facing text,
  not code) — validated entirely by 2d's live smoke test.
- `execution.rs` pre-flight (2c, if pursued): Rust unit test around `execute_task`
  mocking `should_run`'s two outcomes (runnable / not), asserting
  `run_task_with_cc`/`run_task_with_codex` is called only in the runnable case. Exact
  test harness TBD at implementation time — Codexia's existing Rust test conventions
  haven't been surveyed yet (unlike Spec 1, where AlphaLayer's own test conventions
  were read in full before writing test code).

## Open questions for Connor (must resolve before approval)

1. **Approve or reject 2c** (the `execution.rs` pre-flight patch) — this draft
   recommends yes, but it's a code change to a third-party fork, a different kind of
   commitment than Spec 1's pure-Python, own-repo change.
2. **Fail-open vs. fail-closed for 2c's own infra errors** — this draft proposes
   fail-open (launch the session anyway) as the one deliberate exception to Spec 1's
   fail-closed default; confirm that's actually the right tradeoff here.
3. **What real project/goal to use for 2d's end-to-end smoke** — needs a live Codexia
   install, a live LoopX goal, and a real AlphaLayer Flow in some project; nothing in
   this session has that set up yet.
4. **Is the raw-Bash-instruction prompt template good enough**, or does Connor want
   the dedicated-skill-file approach this draft rejected — worth a second opinion
   before 2b is built out either way.

## Relationship to Spec 1

Depends on Spec 1's `alphalayer loopx-tick` CLI command (shipped, merged to `main`).
No changes to Spec 1's code are required by this design.
