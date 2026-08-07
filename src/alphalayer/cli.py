"""The `alphalayer` command: run a Flow, inspect a run's artifacts, or scaffold a new
Layer/Flow module. Stdlib-only — the CLI never requires an optional backend extra."""

from __future__ import annotations

import argparse
import importlib
import sys
from pathlib import Path

from .artifact import Artifact
from .flow import Flow
from .loopx import LoopXRunner


def _load_flow(spec: str) -> Flow:
    module_name, _, attr = spec.partition(":")
    if not attr:
        raise SystemExit(f"expected module:attribute, e.g. myflows.audit:flow (got {spec!r})")
    sys.path.insert(0, str(Path.cwd()))
    module = importlib.import_module(module_name)
    flow = getattr(module, attr, None)
    if not isinstance(flow, Flow):
        raise SystemExit(f"{spec} is not an alphalayer.Flow (got {type(flow).__name__})")
    return flow


def cmd_run(args: argparse.Namespace) -> None:
    flow = _load_flow(args.flow)
    seed = [Artifact.load(Path(p)) for p in (args.seed or [])]
    flow.run(*seed, resume=args.resume)
    results = flow.artifacts()
    print(f"{flow.name}: {len(results)} stage(s) complete")
    for artifact in results:
        where = artifact.path if artifact.path else "(in-memory only)"
        print(f"  [{artifact.stage}] {artifact.layer} -> {artifact.schema}  {where}")


def cmd_inspect(args: argparse.Namespace) -> None:
    run_dir = Path(args.flow_dir)
    if not run_dir.is_dir():
        raise SystemExit(f"no such directory: {run_dir}")
    files = sorted(run_dir.glob("*.md"))
    if not files:
        print(f"(no artifacts in {run_dir})")
        return
    for path in files:
        artifact = Artifact.load(path)
        print(
            f"[{artifact.stage}] {artifact.layer} -> schema={artifact.schema} "
            f"upstream={artifact.upstream} ({path.name})"
        )


def cmd_loopx_tick(args: argparse.Namespace) -> None:
    flow = _load_flow(args.flow)
    seed = [Artifact.load(Path(p)) for p in (args.seed or [])]
    runner = LoopXRunner(flow, goal_id=args.goal_id, agent_id=args.agent_id)
    result = runner.tick(*seed)

    if not result.ran:
        print(f"{flow.name}: not runnable ({result.reason or 'should-run said no'})")
        return

    if result.artifact is None:
        print(f"{flow.name}: already complete, no stage executed")
    else:
        where = result.artifact.path if result.artifact.path else "(in-memory only)"
        print(
            f"{flow.name}: [{result.artifact.stage}] {result.artifact.layer} -> "
            f"{result.artifact.schema}  {where}"
        )
    if result.flow_complete:
        print(f"{flow.name}: flow complete")
    if result.scheduler_hint:
        print(f"{flow.name}: scheduler hint -> {result.scheduler_hint}")


_LAYER_STUB = '''"""{name} — an AlphaLayer Layer."""
from __future__ import annotations

from alphalayer import Artifact, Layer


class {class_name}(Layer):
    consumes_schema = "{consumes}"
    produces_schema = "{produces}"

    def transform(self, *inputs: Artifact) -> Artifact:
        upstream = inputs[-1] if inputs else None
        content = ""  # TODO: transform upstream.content into this layer's output
        return Artifact(layer=self.name, schema=self.produces_schema, content=content)
'''

_FLOW_STUB = '''"""{name} — an AlphaLayer Flow."""
from __future__ import annotations

from alphalayer import Flow

# TODO: import your Skills/Layers and chain them, e.g.:
#   from .my_layer import MyLayer
#   flow = Flow("{name}") | SomeSkill() | MyLayer()

flow = Flow("{name}")
'''


def _class_name(name: str) -> str:
    return "".join(part.capitalize() for part in name.replace("-", "_").split("_") if part)


def cmd_new_layer(args: argparse.Namespace) -> None:
    path = Path(f"{args.name}.py")
    if path.exists() and not args.force:
        raise SystemExit(f"{path} already exists (pass --force to overwrite)")
    path.write_text(
        _LAYER_STUB.format(
            name=args.name,
            class_name=_class_name(args.name),
            consumes=args.consumes or "",
            produces=args.produces or "",
        ),
        encoding="utf-8",
    )
    print(f"wrote {path}")


def cmd_new_flow(args: argparse.Namespace) -> None:
    path = Path(f"{args.name.replace('-', '_')}_flow.py")
    if path.exists() and not args.force:
        raise SystemExit(f"{path} already exists (pass --force to overwrite)")
    path.write_text(_FLOW_STUB.format(name=args.name), encoding="utf-8")
    print(f"wrote {path}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="alphalayer", description="Pipe skills into Layers into Flows."
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_run = sub.add_parser("run", help="run a Flow")
    p_run.add_argument("flow", help="module:attribute pointing at a Flow instance")
    p_run.add_argument("--seed", action="append", help="path to a seed Artifact (repeatable)")
    p_run.add_argument(
        "--resume", action="store_true", help="skip stages whose artifact already exists on disk"
    )
    p_run.set_defaults(func=cmd_run)

    p_inspect = sub.add_parser("inspect", help="list a Flow run's artifacts")
    p_inspect.add_argument("flow_dir", help="path to a Flow's artifact directory")
    p_inspect.set_defaults(func=cmd_inspect)

    p_tick = sub.add_parser("loopx-tick", help="advance a Flow one stage via a LoopX tick")
    p_tick.add_argument("flow", help="module:attribute pointing at a Flow instance")
    p_tick.add_argument("--goal-id", required=True, help="the LoopX goal id to tick against")
    p_tick.add_argument("--agent-id", default="alphalayer", help="the LoopX agent id to tick as")
    p_tick.add_argument("--seed", action="append", help="path to a seed Artifact (repeatable)")
    p_tick.set_defaults(func=cmd_loopx_tick)

    p_layer = sub.add_parser("new-layer", help="scaffold a new Layer module")
    p_layer.add_argument("name")
    p_layer.add_argument("--consumes", help="schema tag this Layer expects")
    p_layer.add_argument("--produces", help="schema tag this Layer emits")
    p_layer.add_argument("--force", action="store_true")
    p_layer.set_defaults(func=cmd_new_layer)

    p_flow = sub.add_parser("new-flow", help="scaffold a new Flow module")
    p_flow.add_argument("name")
    p_flow.add_argument("--force", action="store_true")
    p_flow.set_defaults(func=cmd_new_flow)

    return parser


def main(argv: list[str] | None = None) -> None:
    parser = build_parser()
    args = parser.parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    main()
