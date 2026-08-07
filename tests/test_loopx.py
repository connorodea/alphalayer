from __future__ import annotations

import pytest

from alphalayer import Artifact, Flow, LoopXNotInstalledError, LoopXRunner, Skill, TickResult


class Seed(Skill):
    def run(self, *inputs: Artifact) -> Artifact:
        return Artifact(layer=self.name, schema="raw-v1", content="1")


class NoOp(Skill):
    def run(self, *inputs: Artifact) -> Artifact:
        return Artifact(layer=self.name, schema="raw-v1", content=inputs[-1].content)


def test_tick_short_circuits_when_should_run_is_false(fake_loopx, monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("FAKE_LOOPX_SHOULD_RUN", "false")
    monkeypatch.setenv("FAKE_LOOPX_REASON", "quota exhausted")
    flow = Flow("t1", artifact_dir=tmp_path) | Seed()
    runner = LoopXRunner(flow, goal_id="g1")

    result = runner.tick()

    assert result.ran is False
    assert result.artifact is None
    assert result.flow_complete is False
    assert result.reason == "quota exhausted"
    assert "claim" not in fake_loopx.read_text()


def test_tick_runs_one_stage_and_updates_when_more_remain(fake_loopx, monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("FAKE_LOOPX_TODO_ID", "todo-42")
    flow = Flow("t2", artifact_dir=tmp_path) | Seed() | NoOp(name="noop")
    runner = LoopXRunner(flow, goal_id="g1")

    result = runner.tick()

    assert result.ran is True
    assert result.artifact is not None
    assert result.artifact.content == "1"
    assert result.artifact.stage == 0
    assert result.flow_complete is False
    assert result.scheduler_hint == {"next_wake_seconds": 300}

    calls = fake_loopx.read_text()
    assert "quota should-run --goal-id g1" in calls
    assert "todo claim --goal-id g1 --todo-id todo-42" in calls
    assert "todo update --goal-id g1 --todo-id todo-42 --evidence" in calls
    assert "todo complete" not in calls
    assert "refresh-state --goal-id g1" in calls
    assert "quota spend-slot --goal-id g1 --agent-id alphalayer" in calls


def test_tick_completes_todo_on_the_last_stage(fake_loopx, monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("FAKE_LOOPX_TODO_ID", "todo-42")
    flow = Flow("t3", artifact_dir=tmp_path) | Seed()
    runner = LoopXRunner(flow, goal_id="g1")

    result = runner.tick()

    assert result.flow_complete is True
    calls = fake_loopx.read_text()
    assert "todo complete --goal-id g1 --todo-id todo-42 --evidence" in calls
    assert "todo update" not in calls


def test_tick_on_an_already_complete_flow_runs_no_stage(fake_loopx, monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("FAKE_LOOPX_TODO_ID", "todo-42")
    flow = Flow("t4", artifact_dir=tmp_path) | Seed()
    flow.run()  # complete it directly, bypassing LoopXRunner
    runner = LoopXRunner(flow, goal_id="g1")

    result = runner.tick()

    assert result.ran is True
    assert result.artifact is None
    assert result.flow_complete is True
    calls = fake_loopx.read_text()
    assert "todo complete --goal-id g1 --todo-id todo-42" in calls
    assert "--evidence" not in calls.split("todo complete")[1].split("\n")[0]


def test_tick_raises_when_loopx_is_not_installed(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("PATH", str(tmp_path))  # empty dir, no loopx binary
    flow = Flow("t5", artifact_dir=tmp_path) | Seed()
    runner = LoopXRunner(flow, goal_id="g1")

    with pytest.raises(LoopXNotInstalledError):
        runner.tick()


def test_tick_raises_on_nonzero_exit_from_loopx(fake_loopx, monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("FAKE_LOOPX_FAIL_ON", "should-run")
    flow = Flow("t6", artifact_dir=tmp_path) | Seed()
    runner = LoopXRunner(flow, goal_id="g1")

    with pytest.raises(RuntimeError, match="should-run"):
        runner.tick()


def test_public_api_exports_loopx_names() -> None:
    import alphalayer

    assert alphalayer.LoopXRunner is LoopXRunner
    assert alphalayer.TickResult is TickResult
    assert alphalayer.LoopXNotInstalledError is LoopXNotInstalledError
