from __future__ import annotations

from alphalayer import Artifact, Flow, Layer, Skill


class Seed(Skill):
    def run(self, *inputs: Artifact) -> Artifact:
        return Artifact(layer=self.name, schema="raw-v1", content="1")


class Increment(Layer):
    consumes_schema = "raw-v1"
    produces_schema = "raw-v1"

    def transform(self, *inputs: Artifact) -> Artifact:
        return Artifact(layer=self.name, schema=self.produces_schema, content=str(int(inputs[-1].content) + 1))


def test_flow_writes_numbered_artifacts_to_disk(tmp_path) -> None:
    flow = Flow("counting", artifact_dir=tmp_path) | Seed() | Increment(name="inc-a") | Increment(name="inc-b")
    result = flow.run()
    assert result.content == "3"  # Seed=1 -> inc-a=2 -> inc-b=3

    written = sorted(p.name for p in (tmp_path / "counting").glob("*.md"))
    assert written == ["00-Seed.md", "01-inc-a.md", "02-inc-b.md"]

    stage2 = Artifact.load(tmp_path / "counting" / "02-inc-b.md")
    assert stage2.flow == "counting"
    assert stage2.stage == 2
    assert stage2.upstream is not None


def test_flow_resume_loads_completed_stages_and_computes_the_rest(tmp_path) -> None:
    # Simulate a partial/crashed run: only stage 0 ever completed.
    partial = Flow("resumable", artifact_dir=tmp_path).then(Seed())
    partial.run()

    # Tamper with the persisted stage-0 output on disk, so the next assertion can only
    # pass if stage 1 is computed from THIS value rather than from a fresh Seed() run.
    stage0_path = tmp_path / "resumable" / "00-Seed.md"
    tampered = Artifact.load(stage0_path)
    tampered.content = "99"
    tampered.save(stage0_path)

    full = Flow("resumable", artifact_dir=tmp_path).then(Seed()).then(Increment(name="inc"))
    result = full.run(resume=True)
    assert result.content == "100"  # 99 (resumed from disk) + 1 (freshly computed), not 1 + 1


def test_nested_flow_as_a_single_stage(tmp_path) -> None:
    inner = Flow("inner", artifact_dir=tmp_path) | Seed() | Increment(name="inc")
    outer = Flow("outer", artifact_dir=tmp_path).then(inner).then(Increment(name="inc-outer"))
    result = outer.run()
    assert result.content == "3"  # Seed=1 -> inner Increment=2 -> outer Increment=3


def test_flow_then_and_pipe_operator_are_equivalent() -> None:
    a = Flow("a") | Seed() | Increment(name="x")
    b = Flow("b").then(Seed()).then(Increment(name="x"))
    assert [type(s) for s in a.stages] == [type(s) for s in b.stages]
