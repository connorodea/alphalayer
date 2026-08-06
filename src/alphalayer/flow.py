"""Flow: a named, ordered sequence of Skills/Layers ("stages"), which can itself nest
another Flow as a single stage. Running a Flow writes every stage's output to
`<artifact_dir>/<flow-name>/<NN>-<stage-name>.md` per the Artifact Contract, so a Flow
picked back up in a later process (a fresh script run, days later) can resume from disk
rather than replaying stages that already succeeded.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Union

from .artifact import Artifact
from .skill import Skill

Stage = Union[Skill, "Flow"]


@dataclass
class Flow:
    name: str
    stages: list[Stage] = field(default_factory=list)
    artifact_dir: Path = field(default_factory=lambda: Path("docs/flows"))
    last_run: list[Artifact] = field(default_factory=list, init=False, repr=False)

    def then(self, stage: Stage) -> Flow:
        """Append a stage and return self, for chaining: `flow.then(a).then(b)`."""
        self.stages.append(stage)
        return self

    def __or__(self, other: Stage) -> Flow:
        """The piping operator: `flow | stage` appends `stage` and returns the Flow, so a
        whole pipeline reads as `Flow("name") | SkillA() | LayerB() | LayerC()`."""
        return self.then(other)

    @property
    def run_dir(self) -> Path:
        return self.artifact_dir / self.name

    def run(self, *inputs: Artifact, resume: bool = False) -> Artifact:
        """Run every stage in order, passing each stage every artifact produced so far
        (including any seed `inputs`) — a stage that only cares about the latest one can
        just read `inputs[-1]`; one that needs a specific upstream schema among several can
        call `Artifact.discover(schema=..., context=inputs)` itself. Returns the LAST
        stage's artifact (so a Flow nests as a single stage inside a bigger Flow the same
        way any other Skill does); use `.artifacts()` afterward for the full stage-by-stage
        list. With `resume=True`, a stage whose output file already exists on disk is
        loaded instead of re-run.
        """
        if not self.stages:
            raise ValueError(f"Flow {self.name!r} has no stages — nothing to run")

        produced: list[Artifact] = list(inputs)
        seed_count = len(produced)
        for index, stage in enumerate(self.stages):
            stage_name = getattr(stage, "name", type(stage).__name__)
            out_path = self.run_dir / f"{index:02d}-{stage_name}.md"

            if resume and out_path.exists():
                artifact = Artifact.load(out_path)
                produced.append(artifact)
                continue

            artifact = stage.run(*produced)
            artifact.flow = self.name
            artifact.stage = index
            artifact.layer = stage_name
            if produced and artifact.upstream is None:
                last = produced[-1]
                artifact.upstream = str(last.path) if last.path else last.layer
            artifact.save(out_path)
            produced.append(artifact)

        self.last_run = produced[seed_count:]
        return self.last_run[-1]

    def artifacts(self) -> list[Artifact]:
        """Every stage's output from the most recent `run()` call, in stage order."""
        return list(self.last_run)

    def __repr__(self) -> str:
        chain = " | ".join(getattr(s, "name", type(s).__name__) for s in self.stages)
        return f"Flow({self.name!r}: {chain})"
