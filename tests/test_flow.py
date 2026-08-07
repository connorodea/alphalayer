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


def test_step_advances_one_stage_at_a_time(tmp_path) -> None:
    flow = Flow("ticking", artifact_dir=tmp_path) | Seed() | Increment(name="inc-a") | Increment(name="inc-b")

    first = flow.step()
    assert first is not None
    assert first.content == "1"
    assert first.layer == "Seed"
    assert first.stage == 0

    second = flow.step()
    assert second is not None
    assert second.content == "2"
    assert second.layer == "inc-a"
    assert second.stage == 1

    third = flow.step()
    assert third is not None
    assert third.content == "3"
    assert third.layer == "inc-b"
    assert third.stage == 2

    assert flow.step() is None  # every stage now has an on-disk artifact


def test_step_matches_run_final_state(tmp_path) -> None:
    stepped = Flow("stepped", artifact_dir=tmp_path) | Seed() | Increment(name="inc")
    while stepped.step() is not None:
        pass
    final_via_step = Artifact.load(tmp_path / "stepped" / "01-inc.md")

    ran = Flow("ran", artifact_dir=tmp_path) | Seed() | Increment(name="inc")
    final_via_run = ran.run()

    assert final_via_step.content == final_via_run.content


def test_step_resume_false_always_reexecutes_first_stage(tmp_path) -> None:
    flow = Flow("norezume", artifact_dir=tmp_path) | Seed()
    first = flow.step(resume=False)
    second = flow.step(resume=False)
    assert first is not None and second is not None
    assert first.content == second.content == "1"
    assert first.stage == 0
    assert second.stage == 0


def test_step_raises_on_empty_flow() -> None:
    empty = Flow("empty")
    try:
        empty.step()
        assert False, "expected ValueError"
    except ValueError as exc:
        assert "no stages" in str(exc)
