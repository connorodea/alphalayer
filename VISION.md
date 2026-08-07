# AlphaLayer — Vision

> One-sentence north star: turn a library of one-shot skills into composable, resumable,
> artifact-audited pipelines — walkable by hand in a conversation today, driven unattended
> by a control plane tomorrow.

_Last updated: 2026-08-06 · Version: v1.1_

## What it is

A compositing framework — Skill / Layer / Flow, borrowed from video/image compositing —
for chaining AI automations. The stdlib-only Python package (`pip install alphalayer`) is
the one real execution engine; the Claude Code companion skill (`~/.claude/skills/
alphalayer/`) is the Claude-facing half of the same contract — it explains what a Skill/
Layer/Flow *is* and points at the package rather than maintaining its own parallel,
hand-rolled walkthrough. Both share the **Artifact Contract** — a markdown file with a
small provenance header (flow/stage/layer/schema/upstream) — so output from one stage is
discoverable and trustworthy by the next, whether that handoff happens by hand inside one
conversation or across a fresh process days later.

## Who it's for

Primary, and the only confirmed user today: **Connor**, across a 200+-skill Claude Code
ecosystem and a dozen-plus active projects (AIWholesail, Sightline, Cutroom, GeoStamp,
Preecursor, etc.) where the same shape of problem recurs — an audit skill's output needs
to become a task-creation skill's input, reliably, without re-explaining the handoff by
hand every time. The MIT license, public `connorodea/alphalayer` repo, and zero-forced-
dependency core all point toward a second audience — other Claude Code / agent-runtime
developers — but nothing in the codebase yet confirms that's an intended, resourced goal
rather than good hygiene applied out of habit. See open questions.

## The problem

A Skill today is atomic and stateless: invoked once, hands its output back to a human or
a fresh model turn, and nothing formalizes how stage N's output becomes stage N+1's
trusted input. That's fine for a single interactive exchange. It breaks down for (a)
multi-stage workflows spanning a long conversation, (b) workflows that need to resume
days later without re-deriving state from a transcript, and (c) workflows that need to
run with nobody watching between stages — which the Claude Code skill form explicitly
punts on ("out of scope for this version of AlphaLayer... revisit only if a specific Flow
actually needs it"). That revisit is now underway (see Roadmap).

## Core value proposition

One small, mechanical contract — a markdown artifact with a provenance header — that lets
any two Skills/Layers chain without hand-wiring, and that reads *identically* whether it
was written by a human-walked Flow inside Claude Code or an automated `Flow.run()` in a
script. `LLMSkill.from_skill_md` is the concrete proof: the exact same skill definition
authored for interactive use runs headlessly through a swappable `Backend`, no rewrite.

## Principles / non-negotiables

- Stdlib-only core; vendor SDKs (`anthropic`, `openai`) are opt-in extras, never forced.
- No hidden control flow — a Flow is a straight-line stage sequence; branching belongs in
  a stage's own code, not in the `Flow` object.
- Markdown by default, not a rigid schema language — `schema` is a human-assigned version
  tag, not a contract a machine validates structurally.
- One Artifact format, two runtimes: the contract must read the same by hand and by code.
- **Not** a general workflow engine. Fan-out, parallelism, and judge-panel patterns belong
  to the `Workflow` tool's `agent()`/`parallel()`/`pipeline()` — AlphaLayer's job is
  composition and resumability of a straight-line pipeline, not orchestration at scale.
- **Not** a scheduler or durable-state store. Multi-day unattended state is explicitly
  deferred to an external control plane (LoopX) rather than reinvented here.

## Main workflows

1. Author a Skill (atomic capability) or Layer (pure transform) — as a Python
   class/decorator, or as a Claude Code `SKILL.md`.
2. Compose a Flow by piping Skills/Layers with `|`; run it (`flow.run()` /
   `alphalayer run`); inspect the artifact trail (`alphalayer inspect`).
3. Resume a Flow in a fresh process, days later — `resume=True` loads already-completed
   stages from disk instead of re-running them.
4. Bridge an interactive Claude Code skill into headless execution via
   `LLMSkill.from_skill_md` + a `Backend`, so the same skill runs unattended.
5. *(Emerging — in design now)* Advance a Flow one bounded stage per external tick —
   `Flow.step()` + `LoopXRunner` — so a durable control plane can gate, schedule, and
   resume a multi-day unattended run without losing state between wakes.

## System modules

- **Artifact** (`artifact.py`) — the contract: header format, save/load, discovery order
  (context → explicit path → highest-stage disk match).
- **Skill / Layer** (`skill.py`, `layer.py`) — atomic capability vs. pure-transform piping
  unit; `@skill`/`@layer` decorators for function-based authoring without a class.
- **Flow** (`flow.py`) — ordered stage chain, `|` composition, resume-by-disk; `step()`
  (planned) for single-stage, cross-process advancement.
- **Backends** (`backends.py`) — a pluggable `Backend` protocol plus `AnthropicBackend`/
  `OpenAIBackend`; `LLMSkill.from_skill_md` is the Claude-Code-skill bridge.
- **CLI** (`cli.py`) — `run`, `inspect`, `new-layer`, `new-flow`; `loopx-tick` (planned).
- **Claude Code companion skill** (`~/.claude/skills/alphalayer/`) — the Claude-facing
  half of the same contract: explains the three tiers, points authoring/running guidance
  at the pip package, holds the reference `prod-readiness-remediation` Flow doc, and the
  rule that Flow *definitions* are global while Flow *run artifacts* are project-local.

## Data model implications

The only durable entity is the Artifact file itself — no database. A Flow's state is
literally "which numbered files exist under `docs/flows/<flow>/`." That's deliberate and
is what makes resumability free, but it means there's no way today to query or report
across flows or across projects ("show me every flow that ran this week across all my
repos") — that would need either a Layer/Skill that scans multiple `docs/flows/` trees,
or to be deferred entirely to a downstream control plane's own state once the LoopX
integration lands.

## UI/UX implications

No GUI. The interface is the CLI's own output (`run`/`inspect`) and the artifact markdown
files themselves, meant to be read directly in an editor or a git diff without tooling.
If the Codexia integration lands, its automation-task list becomes a de facto dashboard
for which Flows are ticking on schedule — but that's an adjacent tool's UI, not
AlphaLayer's own; AlphaLayer stays a library and a CLI.

## MVP boundary

**In:** Skill/Layer/Flow core, the Artifact Contract + discovery rules, the CLI
(`run`/`inspect`/`new-layer`/`new-flow`), the two backend bridges (Anthropic/OpenAI +
`from_skill_md`), and the parallel Claude Code skill form for manual/interactive use.

**Out (for now):** unattended/scheduled execution (the LoopX integration, currently in
spec), any GUI/dashboard, cross-flow or cross-project reporting, backends beyond
Anthropic/OpenAI, and parallel/fan-out stage execution (explicitly the `Workflow` tool's
job, not AlphaLayer's).

## Roadmap (vision → milestones)

- **Now:** Spec 1 — `Flow.step()` + `LoopXRunner` + `alphalayer loopx-tick`, giving a Flow
  durable, gated, multi-day unattended execution for the first time.
- **Next:** Spec 2 — Codexia automation-scheduler integration (a small tick-prompt skill
  plus an optional `should-run` pre-flight patch in `execution.rs`), so a Flow can be
  woken by a cron/GUI scheduler instead of only Claude Code's native `/loop`.
- **Later:** grow past the single `prod-readiness-remediation` reference Flow into more of
  Connor's own recurring workflows (SEO pipelines, dev-tracker sync, and similar) as named
  reusable Flows; deliberately decide whether investment in public/OSS adoption (docs
  site, more backends, community Flows) is worth it, rather than defaulting into it.

## How to decompose this

Each roadmap line is its own spec → plan → implementation cycle — Spec 1 and Spec 2 are
already scoped separately under `docs/superpowers/specs/`. There's no Todoist project for
AlphaLayer yet, unlike AIWholesail/Cutroom/Sightline; worth creating one once Spec 1 ships
so backlog tracking matches the rest of the portfolio. A good next objective is always
"the smallest Flow that proves the next roadmap line end-to-end," not a batch of unrelated
improvements bundled together.

## Open questions

- Internal tool or real OSS project? The license/repo/dependency choices all read as
  "built to be shipped," but nothing confirms that's an intended, resourced goal versus
  good habit. This changes how much docs/polish/community investment is warranted.
- Once LoopX and Codexia integrations exist, does AlphaLayer stay agnostic to whichever
  control plane/scheduler drives it (today's design), or does LoopX become a de facto
  required dependency for any real unattended use — and if so, is "stdlib-only, no forced
  dependencies" still the right invariant to hold once unattended execution is the main
  event rather than a bonus capability?

## Changelog

- 2026-08-06 v1.1 — Resolved the "two parallel forms" open question: the Claude Code
  skill now points at `pip install alphalayer` / `LLMSkill.from_skill_md` instead of
  maintaining its own manual-walkthrough templates. `SKILL.md` and
  `references/artifact-contract.md` updated to match; the old `templates/` directory
  (`LAYER_TEMPLATE.md`/`FLOW_TEMPLATE.md`) is now unreferenced and superseded by
  `alphalayer new-layer`/`new-flow` — left in place rather than deleted since
  `~/.claude/skills` isn't under version control here.
- 2026-08-06 v1 — Initial vision, authored from codebase inference (no prior vision doc
  existed). Captures the Claude-Code-skill-form → Python-package trajectory and the
  in-progress LoopX (Spec 1) / Codexia (Spec 2) integration work as the immediate roadmap.
