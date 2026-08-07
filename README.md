# AlphaLayer

A compositing framework for AI skills — the alpha-channel/compositing metaphor from video
and image editing (layers, stacks, alpha blending), applied to how automations combine.

```bash
pip install alphalayer
```

## The three tiers

- **Skill** — an atomic capability. Does one job, produces an `Artifact`. Doesn't know or
  care what happens to its output next.
- **Layer** — a `Skill` whose entire job is piping: it declares the schema it consumes and
  the schema it produces, and does no original work beyond transforming its input.
- **Flow** — a named, ordered chain of Skills/Layers, composable with `|`. A `Flow` can
  itself be nested inside another `Flow` as a single stage — the same way a composition can
  nest inside a composition in compositing software.

```python
from alphalayer import Artifact, Flow, Layer, Skill

class FetchIssues(Skill):
    def run(self, *inputs: Artifact) -> Artifact:
        issues = fetch_from_somewhere()
        return Artifact(layer=self.name, schema="issues-v1", content=render(issues))

class Summarize(Layer):
    consumes_schema = "issues-v1"
    produces_schema = "summary-v1"

    def transform(self, *inputs: Artifact) -> Artifact:
        return Artifact(layer=self.name, schema=self.produces_schema, content=summarize(inputs[-1].content))

flow = Flow("weekly-digest") | FetchIssues() | Summarize()
result = flow.run()
print(result.content)
```

## The Artifact Contract

Every `Artifact` carries a small provenance header — which flow, which stage, what schema,
what it was built from — serialized as a markdown file with a front-matter block:

```
---
flow: weekly-digest
stage: 1
layer: Summarize
schema: summary-v1
upstream: docs/flows/weekly-digest/00-FetchIssues.md
---
<the actual content>
```

Running a `Flow` writes every stage's artifact to `docs/flows/<flow-name>/<NN>-<stage>.md`
by default (configurable via `artifact_dir`). This is what makes a Flow resumable — pick it
back up in a new process, days later, with `flow.run(resume=True)`, and any stage whose
artifact already exists on disk is loaded instead of re-run.

`Artifact.discover(schema, context=..., explicit_path=..., flow_dir=...)` implements the
same lookup a Layer needs manually if it's ever run outside a `Flow`'s automatic wiring:
context first, then an explicit path, then a directory search for the highest-stage file
with a matching schema — raising rather than guessing when more than one candidate matches.

## Bridging to Claude Code skills

If you already have skills authored as Markdown (`SKILL.md` files, e.g. for interactive use
in Claude Code), `LLMSkill.from_skill_md` runs one headlessly via an API backend — the same
skill, invoked programmatically instead of by hand:

```python
from alphalayer import AnthropicBackend, LLMSkill

audit = LLMSkill.from_skill_md(
    "~/.claude/skills/prod-readiness-auditor/SKILL.md",
    backend=AnthropicBackend(),
    produces_schema="audit-v1",
)
flow = Flow("nightly-audit", artifact_dir=Path("docs/flows")) | audit | ...
```

`AnthropicBackend`/`OpenAIBackend` require their extras (`pip install alphalayer[anthropic]`
/ `alphalayer[openai]`) — the core library has zero required dependencies. `Backend` is a
`Protocol`, so any callable with a `complete(system=..., prompt=..., max_tokens=...) -> str`
method works, including a hand-rolled one for a local model.

## CLI

```bash
alphalayer new-layer my-thing --consumes in-v1 --produces out-v1   # scaffold a Layer module
alphalayer new-flow my-pipeline                                     # scaffold a Flow module
alphalayer run my_flows.digest:flow                                 # run a Flow (module:attribute)
alphalayer run my_flows.digest:flow --resume                        # skip already-completed stages
alphalayer inspect docs/flows/weekly-digest                         # list a run's artifacts
alphalayer loopx-tick my_flows.digest:flow --goal-id my-goal         # advance one stage, gated by LoopX
```

`loopx-tick` advances a Flow one stage per call, gated by a
[LoopX](https://github.com/connorodea/loopx) goal — `quota should-run` decides whether to
act, and the tick claims a todo, runs `Flow.step()`, writes back compact evidence, and
spends quota, so a Flow can run unattended across days under an external scheduler (a
cron job, Claude Code's native `/loop`, or any host that wakes this command once per
tick). See `docs/superpowers/specs/2026-08-06-loopx-integration-design.md` and
`VISION.md` for the design and roadmap.

## Design notes

- **No forced dependencies.** The core (`Artifact`/`Skill`/`Layer`/`Flow`/CLI) is stdlib-only.
  Vendor SDKs live behind optional extras.
- **No hidden control flow.** A `Flow` is a straight-line sequence of stages, each seeing
  every artifact produced so far. Branching/conditional logic belongs in a stage's own code
  (have it call `Artifact.discover` or just inspect `inputs`), not in the `Flow` object.
- **Markdown by default**, not a rigid schema language. `schema` is a short, human-assigned
  version tag (`audit-v1`) a consumer checks before parsing — bump it when a shape change
  would break an existing consumer's assumptions, not on every edit.

## Development

```bash
pip install -e ".[dev]"
pytest
ruff check src tests
mypy src
```

## License

MIT — see `LICENSE`.
