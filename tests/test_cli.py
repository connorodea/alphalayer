from __future__ import annotations

from pathlib import Path

from alphalayer.cli import build_parser, main


def test_new_layer_scaffolds_a_module(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    main(["new-layer", "my-thing", "--consumes", "in-v1", "--produces", "out-v1"])
    generated = Path("my-thing.py")
    assert generated.exists()
    text = generated.read_text()
    assert "class MyThing(Layer):" in text
    assert 'consumes_schema = "in-v1"' in text
    assert 'produces_schema = "out-v1"' in text


def test_new_layer_refuses_to_clobber_without_force(tmp_path, monkeypatch, capsys) -> None:
    monkeypatch.chdir(tmp_path)
    main(["new-layer", "x"])
    try:
        main(["new-layer", "x"])
        assert False, "expected SystemExit"
    except SystemExit as exc:
        assert "already exists" in str(exc)


def test_new_flow_scaffolds_a_module(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    main(["new-flow", "my-pipeline"])
    generated = Path("my_pipeline_flow.py")
    assert generated.exists()
    assert 'Flow("my-pipeline")' in generated.read_text()


def test_run_and_inspect_round_trip(tmp_path, monkeypatch, capsys) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / "myflows.py").write_text(
        "from alphalayer import Artifact, Skill, Flow\n"
        "class Seed(Skill):\n"
        "    def run(self, *inputs):\n"
        "        return Artifact(layer=self.name, schema='raw-v1', content='hi')\n"
        "flow = Flow('cli-test') | Seed()\n"
    )
    main(["run", "myflows:flow"])
    out = capsys.readouterr().out
    assert "1 stage(s) complete" in out

    main(["inspect", "docs/flows/cli-test"])
    out = capsys.readouterr().out
    assert "schema=raw-v1" in out


def test_parser_requires_a_subcommand() -> None:
    parser = build_parser()
    assert parser.prog == "alphalayer"


def test_loopx_tick_runs_one_stage(tmp_path, monkeypatch, capsys, fake_loopx) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("FAKE_LOOPX_TODO_ID", "todo-1")
    (tmp_path / "myflows.py").write_text(
        "from alphalayer import Artifact, Skill, Flow\n"
        "class Seed(Skill):\n"
        "    def run(self, *inputs):\n"
        "        return Artifact(layer=self.name, schema='raw-v1', content='hi')\n"
        "flow = Flow('tick-test') | Seed()\n"
    )

    main(["loopx-tick", "myflows:flow", "--goal-id", "g1"])

    out = capsys.readouterr().out
    assert "[0] Seed -> raw-v1" in out
    assert "flow complete" in out


def test_loopx_tick_reports_when_not_runnable(tmp_path, monkeypatch, capsys, fake_loopx) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("FAKE_LOOPX_SHOULD_RUN", "false")
    monkeypatch.setenv("FAKE_LOOPX_REASON", "quiet")
    (tmp_path / "myflows.py").write_text(
        "from alphalayer import Artifact, Skill, Flow\n"
        "class Seed(Skill):\n"
        "    def run(self, *inputs):\n"
        "        return Artifact(layer=self.name, schema='raw-v1', content='hi')\n"
        "flow = Flow('tick-test-2') | Seed()\n"
    )

    main(["loopx-tick", "myflows:flow", "--goal-id", "g1"])

    out = capsys.readouterr().out
    assert "not runnable (quiet)" in out
