# AlphaLayer ↔ LoopX Integration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let an AlphaLayer `Flow` be advanced one bounded stage per external "tick,"
gated by a LoopX goal — implementing GOALS.md's Goal 1 / `docs/superpowers/specs/
2026-08-06-loopx-integration-design.md`.

**Architecture:** Two additive pieces over the existing `Flow`/`Artifact` classes: (1)
`Flow.step()`, a stateless single-stage-advance method built on a small `_run_one_stage`
helper extracted from `run()`'s existing per-stage body (pure refactor — `run()`'s
behavior is unchanged); (2) `LoopXRunner`, a new stdlib-only class in `loopx.py` that
shells out to the `loopx` CLI binary to implement LoopX's documented "Direct CLI
orchestration" tick sequence (`should-run` → claim → `step()` → writeback → spend-slot →
scheduler hint), exposed via a new `alphalayer loopx-tick` CLI subcommand.

**Tech Stack:** Python 3.10+, stdlib only (`subprocess`, `json`, `shutil`) — no new pip
dependency. Tests use a fake `loopx` executable placed on `PATH` via a pytest fixture, so
the suite never needs a real LoopX install or goal state.

**Scope note:** This plan covers Goal 1's sub-goals 1a–1c (implementation + unit tests) —
software that's fully testable in isolation. Sub-goals 1d (reconcile the provisional
`loopx` CLI flag/JSON-field names below against a live `loopx --help`) and 1e
(end-to-end smoke against a real LoopX goal) require live LoopX infrastructure this repo
doesn't have and are explicitly follow-on work after this plan lands — tracked in
`GOALS.md`, not repeated here.

---

## File Structure

- **Modify:** `src/alphalayer/flow.py` — extract `_run_one_stage`; add `step()`.
- **Modify:** `src/alphalayer/exceptions.py` — add `LoopXNotInstalledError`.
- **Create:** `src/alphalayer/loopx.py` — `TickResult`, `_run_loopx`, `LoopXRunner`.
- **Modify:** `src/alphalayer/__init__.py` — export the three new public names.
- **Modify:** `src/alphalayer/cli.py` — add the `loopx-tick` subcommand.
- **Modify:** `README.md` — document the new CLI command.
- **Create:** `tests/conftest.py` — the `fake_loopx` fixture shared by `test_loopx.py` and
  `test_cli.py`.
- **Modify:** `tests/test_flow.py` — `step()` test cases.
- **Create:** `tests/test_loopx.py` — `LoopXRunner` test cases.
- **Modify:** `tests/test_cli.py` — `loopx-tick` test case.

All commands below assume the repo's existing venv: `.venv/bin/pytest`,
`.venv/bin/ruff`, `.venv/bin/mypy` (already set up; `pip install -e ".[dev]"` has been
run and 34 tests currently pass on `main`/this branch).

---

### Task 1: `Flow.step()` — single-stage advance

**Files:**
- Modify: `src/alphalayer/flow.py`
- Test: `tests/test_flow.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_flow.py` (reuses the existing `Seed`/`Increment` fixtures already
defined at the top of that file):

```python
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
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv/bin/pytest tests/test_flow.py -k step -v`
Expected: FAIL — `AttributeError: 'Flow' object has no attribute 'step'` (or similar) for
each new test.

- [ ] **Step 3: Extract `_run_one_stage` and add `step()`**

In `src/alphalayer/flow.py`, replace the body of `run()` with a version that delegates
per-stage execution to a new private helper, and add `step()` right after it. The full
new contents of the `Flow` class from `run_dir` onward (replacing the current `run_dir`
property through the end of `run()`):

```python
    @property
    def run_dir(self) -> Path:
        return self.artifact_dir / self.name

    def _run_one_stage(self, index: int, stage: Stage, produced: list[Artifact]) -> Artifact:
        """Execute a single stage against everything produced so far, stamp its
        provenance, save it to disk, and return it. Shared by `run()`'s all-stages loop
        and `step()`'s single-stage advance — the two must stay behaviorally identical
        for any one stage."""
        stage_name = getattr(stage, "name", type(stage).__name__)
        out_path = self.run_dir / f"{index:02d}-{stage_name}.md"
        artifact = stage.run(*produced)
        artifact.flow = self.name
        artifact.stage = index
        artifact.layer = stage_name
        if produced and artifact.upstream is None:
            last = produced[-1]
            artifact.upstream = str(last.path) if last.path else last.layer
        artifact.save(out_path)
        return artifact

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

            artifact = self._run_one_stage(index, stage, produced)
            produced.append(artifact)

        self.last_run = produced[seed_count:]
        return self.last_run[-1]

    def step(self, *inputs: Artifact, resume: bool = True) -> Artifact | None:
        """Execute exactly the next stage whose on-disk artifact doesn't already exist,
        and return it. Returns `None` once every stage is resolved. Stateless across
        calls: re-derives "what's next" purely from disk each time, so a fresh process
        picking this Flow up mid-run (the per-tick case — see `LoopXRunner`) needs no
        in-memory state carried over from a prior call.

        Meant to be called with `resume=True` (the default) for real, cross-process
        ticking. `resume=False` always (re-)executes the first stage in the list rather
        than advancing past it on repeated calls — it exists for signature symmetry with
        `run()`, not for stepping through a Flow.
        """
        if not self.stages:
            raise ValueError(f"Flow {self.name!r} has no stages — nothing to run")

        produced: list[Artifact] = list(inputs)
        for index, stage in enumerate(self.stages):
            stage_name = getattr(stage, "name", type(stage).__name__)
            out_path = self.run_dir / f"{index:02d}-{stage_name}.md"

            if resume and out_path.exists():
                produced.append(Artifact.load(out_path))
                continue

            return self._run_one_stage(index, stage, produced)

        return None
```

- [ ] **Step 4: Run the full flow test file to verify everything passes**

Run: `.venv/bin/pytest tests/test_flow.py -v`
Expected: PASS — all 4 new tests plus the 4 pre-existing ones (8 total).

- [ ] **Step 5: Commit**

```bash
git add src/alphalayer/flow.py tests/test_flow.py
git commit -m "feat: add Flow.step() for single-stage, cross-process advancement" \
  --author="Connor O'Dea <102129457+connorodea@users.noreply.github.com>"
```

---

### Task 2: `fake_loopx` test fixture

**Files:**
- Create: `tests/conftest.py`

No production code in this task — it's shared test infrastructure for Task 3, verified by
a smoke test of the fixture itself.

- [ ] **Step 1: Write `tests/conftest.py`**

```python
"""Shared pytest fixtures for AlphaLayer's test suite."""

from __future__ import annotations

import os
import stat

import pytest

_FAKE_LOOPX = '''#!/usr/bin/env python3
import json
import os
import sys

args = sys.argv[1:]
if args[:2] == ["--format", "json"]:
    args = args[2:]

log_path = os.environ.get("FAKE_LOOPX_LOG")
if log_path:
    with open(log_path, "a") as f:
        f.write(" ".join(args) + "\\n")

fail_on = os.environ.get("FAKE_LOOPX_FAIL_ON")
if fail_on and fail_on in args:
    print("simulated failure", file=sys.stderr)
    sys.exit(1)

if args[:2] == ["quota", "should-run"]:
    print(json.dumps({
        "should_run": os.environ.get("FAKE_LOOPX_SHOULD_RUN", "true") == "true",
        "reason": os.environ.get("FAKE_LOOPX_REASON"),
        "todo_id": os.environ.get("FAKE_LOOPX_TODO_ID", "todo-1"),
        "scheduler_hint": {"next_wake_seconds": 300},
    }))
else:
    print(json.dumps({"ok": True}))
'''


@pytest.fixture
def fake_loopx(tmp_path, monkeypatch):
    """Puts a fake `loopx` executable on PATH that echoes canned JSON packets, so
    LoopXRunner/CLI tests never need a real LoopX install or goal state. Every
    invocation's arguments (minus `--format json`) are appended, one per line, to the
    file this fixture returns — assert against it to verify which loopx subcommands ran,
    in what order.

    Control the fake's should-run answer via env vars before calling the code under
    test: FAKE_LOOPX_SHOULD_RUN ("true"/"false"), FAKE_LOOPX_REASON, FAKE_LOOPX_TODO_ID,
    FAKE_LOOPX_FAIL_ON (a subcommand name, e.g. "claim", to make that call exit 1).
    """
    bin_dir = tmp_path / "fakebin"
    bin_dir.mkdir()
    script = bin_dir / "loopx"
    script.write_text(_FAKE_LOOPX)
    script.chmod(script.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)

    log_path = tmp_path / "loopx-calls.log"
    log_path.write_text("")
    monkeypatch.setenv("PATH", f"{bin_dir}{os.pathsep}{os.environ.get('PATH', '')}")
    monkeypatch.setenv("FAKE_LOOPX_LOG", str(log_path))
    return log_path
```

- [ ] **Step 2: Smoke-test the fixture directly**

Add a temporary throwaway test to confirm the fixture works before building `LoopXRunner`
against it — create `tests/test_conftest_smoke.py`:

```python
from __future__ import annotations

import json
import shutil
import subprocess


def test_fake_loopx_responds_to_should_run(fake_loopx, monkeypatch) -> None:
    monkeypatch.setenv("FAKE_LOOPX_SHOULD_RUN", "false")
    monkeypatch.setenv("FAKE_LOOPX_REASON", "quiet")
    assert shutil.which("loopx") is not None
    result = subprocess.run(
        ["loopx", "--format", "json", "quota", "should-run", "--goal-id", "g1"],
        capture_output=True, text=True,
    )
    assert result.returncode == 0
    packet = json.loads(result.stdout)
    assert packet == {
        "should_run": False, "reason": "quiet", "todo_id": "todo-1",
        "scheduler_hint": {"next_wake_seconds": 300},
    }
    assert fake_loopx.read_text().strip() == "quota should-run --goal-id g1"
```

Run: `.venv/bin/pytest tests/test_conftest_smoke.py -v`
Expected: PASS.

- [ ] **Step 3: Delete the throwaway smoke test**

It did its job (proving the fixture works); `test_loopx.py` in Task 3 is the real,
permanent coverage of this fixture's usage.

```bash
rm tests/test_conftest_smoke.py
```

- [ ] **Step 4: Commit**

```bash
git add tests/conftest.py
git commit -m "test: add fake_loopx fixture for LoopXRunner tests" \
  --author="Connor O'Dea <102129457+connorodea@users.noreply.github.com>"
```

---

### Task 3: `LoopXRunner`

**Files:**
- Modify: `src/alphalayer/exceptions.py`
- Create: `src/alphalayer/loopx.py`
- Test: `tests/test_loopx.py`

- [ ] **Step 1: Add `LoopXNotInstalledError`**

Append to `src/alphalayer/exceptions.py`:

```python
class LoopXNotInstalledError(AlphaLayerError):
    """The `loopx` binary isn't on PATH — LoopXRunner needs it to tick a Flow forward
    against a real LoopX goal."""
```

- [ ] **Step 2: Write the failing tests**

Create `tests/test_loopx.py`:

```python
from __future__ import annotations

import pytest

from alphalayer import Artifact, Flow, Skill
from alphalayer.exceptions import LoopXNotInstalledError
from alphalayer.loopx import LoopXRunner


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
```

- [ ] **Step 3: Run the tests to verify they fail**

Run: `.venv/bin/pytest tests/test_loopx.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'alphalayer.loopx'`.

- [ ] **Step 4: Write `src/alphalayer/loopx.py`**

```python
"""LoopXRunner: drive an AlphaLayer Flow one bounded stage per external "tick," gated by
LoopX's local control plane (https://github.com/connorodea/loopx). Implements LoopX's
documented "Direct CLI orchestration" contract — should-run, claim, execute one bounded
action, validate, writeback, spend quota — over the `loopx` binary via subprocess, so
this module needs no dependency beyond the stdlib.

The exact `loopx` CLI flag/JSON-field names below are provisional, written against a
cloned snapshot of the LoopX docs rather than a live install — reconcile against
`loopx --help` before relying on this against a real goal (see docs/superpowers/specs/
2026-08-06-loopx-integration-design.md's "Open implementation questions").
"""

from __future__ import annotations

import json
import shutil
import subprocess
import time
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from .artifact import Artifact
from .exceptions import LoopXNotInstalledError
from .flow import Flow


@dataclass
class TickResult:
    """The outcome of one `LoopXRunner.tick()` call."""

    ran: bool
    artifact: Artifact | None
    flow_complete: bool
    reason: str | None = None
    scheduler_hint: dict[str, Any] | None = None


def _run_loopx(*args: str) -> dict[str, Any]:
    """Run `loopx --format json <args>`, returning the parsed JSON response. Raises
    `LoopXNotInstalledError` if the binary isn't on PATH, and `RuntimeError` for any
    other failure (non-zero exit or unparseable output) — infrastructure failures are
    meant to be loud, never a silent no-op."""
    if shutil.which("loopx") is None:
        raise LoopXNotInstalledError(
            "the `loopx` binary was not found on PATH — install it per "
            "https://github.com/connorodea/loopx#try-loopx"
        )
    result = subprocess.run(
        ["loopx", "--format", "json", *args],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"loopx {' '.join(args)} exited {result.returncode}: {result.stderr.strip()}"
        )
    try:
        return dict(json.loads(result.stdout))
    except json.JSONDecodeError as exc:
        raise RuntimeError(
            f"loopx {' '.join(args)} did not return valid JSON: {result.stdout!r}"
        ) from exc


class LoopXRunner:
    """Ticks a Flow forward one stage at a time, gated by a LoopX goal. One `tick()` call
    is LoopX's "one bounded action" — call it once per external wake (a Claude Code
    `/loop` iteration, a cron job, a Codexia automation task); `LoopXRunner` does not own
    scheduling itself.
    """

    def __init__(
        self,
        flow: Flow,
        *,
        goal_id: str,
        agent_id: str = "alphalayer",
        available_capabilities: Sequence[str] = ("shell",),
    ) -> None:
        self.flow = flow
        self.goal_id = goal_id
        self.agent_id = agent_id
        self.available_capabilities = tuple(available_capabilities)

    def _should_run_args(self) -> list[str]:
        args = ["quota", "should-run", "--goal-id", self.goal_id, "--agent-id", self.agent_id]
        for capability in self.available_capabilities:
            args += ["--available-capability", capability]
        return args

    def tick(self, *inputs: Artifact) -> TickResult:
        packet = _run_loopx(*self._should_run_args())
        if not packet.get("should_run", False):
            return TickResult(
                ran=False,
                artifact=None,
                flow_complete=False,
                reason=packet.get("reason"),
                scheduler_hint=packet.get("scheduler_hint"),
            )

        todo_id = packet.get("todo_id")
        scheduler_hint = packet.get("scheduler_hint")
        if todo_id:
            _run_loopx("todo", "claim", "--goal-id", self.goal_id, "--todo-id", str(todo_id))

        artifact = self.flow.step(*inputs, resume=True)

        if artifact is None:
            if todo_id:
                _run_loopx("todo", "complete", "--goal-id", self.goal_id, "--todo-id", str(todo_id))
            _run_loopx("refresh-state", "--goal-id", self.goal_id)
            _run_loopx("quota", "spend-slot", "--goal-id", self.goal_id, "--agent-id", self.agent_id)
            return TickResult(ran=True, artifact=None, flow_complete=True, scheduler_hint=scheduler_hint)

        is_last_stage = artifact.stage is not None and artifact.stage == len(self.flow.stages) - 1
        evidence = f"{artifact.schema}@stage{artifact.stage} -> {artifact.path}"
        if todo_id:
            if is_last_stage:
                _run_loopx(
                    "todo", "complete", "--goal-id", self.goal_id, "--todo-id", str(todo_id),
                    "--evidence", evidence,
                )
            else:
                _run_loopx(
                    "todo", "update", "--goal-id", self.goal_id, "--todo-id", str(todo_id),
                    "--evidence", evidence,
                )
        _run_loopx("refresh-state", "--goal-id", self.goal_id)
        _run_loopx("quota", "spend-slot", "--goal-id", self.goal_id, "--agent-id", self.agent_id)

        return TickResult(
            ran=True,
            artifact=artifact,
            flow_complete=is_last_stage,
            scheduler_hint=scheduler_hint,
        )

    def run_to_completion(
        self, *inputs: Artifact, poll_interval: float | None = None
    ) -> list[TickResult]:
        """Convenience loop for a simple/dev host: tick repeatedly until the Flow
        completes or LoopX says not to run. NOT the recommended integration surface for a
        real host — LoopX's own design principle is that the *runner* owns wakeups, so a
        production host should call `tick()` once per external wake (see the
        `alphalayer loopx-tick` CLI command) rather than looping inside this process.
        """
        results: list[TickResult] = []
        while True:
            result = self.tick(*inputs)
            results.append(result)
            if not result.ran or result.flow_complete:
                break
            if poll_interval:
                time.sleep(poll_interval)
        return results
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `.venv/bin/pytest tests/test_loopx.py -v`
Expected: PASS — all 6 tests.

- [ ] **Step 6: Commit**

```bash
git add src/alphalayer/exceptions.py src/alphalayer/loopx.py tests/test_loopx.py
git commit -m "feat: add LoopXRunner — tick a Flow forward gated by a LoopX goal" \
  --author="Connor O'Dea <102129457+connorodea@users.noreply.github.com>"
```

---

### Task 4: Export from the public API

**Files:**
- Modify: `src/alphalayer/__init__.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_backends.py` — no, this belongs on its own; append to
`tests/test_flow.py` instead is also wrong (different concern). Create a minimal check
inline as part of this task by adding to `tests/test_loopx.py`:

```python
def test_public_api_exports_loopx_names() -> None:
    import alphalayer

    assert alphalayer.LoopXRunner is LoopXRunner
    assert alphalayer.TickResult is TickResult
    assert alphalayer.LoopXNotInstalledError is LoopXNotInstalledError
```

Add `TickResult` and `LoopXNotInstalledError` to the existing `from alphalayer...`
imports at the top of `tests/test_loopx.py` (the file already imports `LoopXRunner` from
`alphalayer.loopx` and `LoopXNotInstalledError` from `alphalayer.exceptions` — change
both to import from the top-level `alphalayer` package instead, and add `TickResult`):

```python
from alphalayer import Artifact, Flow, LoopXNotInstalledError, LoopXRunner, Skill, TickResult
```

(Remove the now-redundant `from alphalayer.loopx import LoopXRunner` and
`from alphalayer.exceptions import LoopXNotInstalledError` lines.)

- [ ] **Step 2: Run the test to verify it fails**

Run: `.venv/bin/pytest tests/test_loopx.py -v`
Expected: FAIL — `ImportError: cannot import name 'LoopXRunner' from 'alphalayer'`.

- [ ] **Step 3: Update `src/alphalayer/__init__.py`**

Replace the existing imports and `__all__` list with:

```python
from .artifact import Artifact
from .backends import AnthropicBackend, Backend, LLMSkill, OpenAIBackend
from .exceptions import (
    AlphaLayerError,
    AmbiguousArtifactError,
    ArtifactNotFoundError,
    LoopXNotInstalledError,
    SchemaMismatchError,
)
from .flow import Flow
from .layer import Layer, layer
from .loopx import LoopXRunner, TickResult
from .skill import Skill, skill

__version__ = "0.1.0"

__all__ = [
    "AlphaLayerError",
    "AmbiguousArtifactError",
    "AnthropicBackend",
    "Artifact",
    "ArtifactNotFoundError",
    "Backend",
    "Flow",
    "LLMSkill",
    "Layer",
    "LoopXNotInstalledError",
    "LoopXRunner",
    "OpenAIBackend",
    "SchemaMismatchError",
    "Skill",
    "TickResult",
    "__version__",
    "layer",
    "skill",
]
```

- [ ] **Step 4: Run the full test suite to verify everything passes**

Run: `.venv/bin/pytest -v`
Expected: PASS — all tests (34 pre-existing + new ones from Tasks 1, 3, and this task).

- [ ] **Step 5: Commit**

```bash
git add src/alphalayer/__init__.py tests/test_loopx.py
git commit -m "feat: export LoopXRunner, TickResult, LoopXNotInstalledError from top-level package" \
  --author="Connor O'Dea <102129457+connorodea@users.noreply.github.com>"
```

---

### Task 5: `alphalayer loopx-tick` CLI subcommand

**Files:**
- Modify: `src/alphalayer/cli.py`
- Test: `tests/test_cli.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_cli.py`:

```python
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
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv/bin/pytest tests/test_cli.py -k loopx_tick -v`
Expected: FAIL — `SystemExit: 2` / `argument command: invalid choice: 'loopx-tick'`.

- [ ] **Step 3: Add the subcommand to `src/alphalayer/cli.py`**

Add the import (with the other `from .` imports at the top of the file):

```python
from .loopx import LoopXRunner
```

Add the command function (place it after `cmd_inspect` and before `_LAYER_STUB`):

```python
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
```

Register the subparser in `build_parser()` — add this block right after the `p_inspect`
block and before the `p_layer` block:

```python
    p_tick = sub.add_parser("loopx-tick", help="advance a Flow one stage via a LoopX tick")
    p_tick.add_argument("flow", help="module:attribute pointing at a Flow instance")
    p_tick.add_argument("--goal-id", required=True, help="the LoopX goal id to tick against")
    p_tick.add_argument("--agent-id", default="alphalayer", help="the LoopX agent id to tick as")
    p_tick.add_argument("--seed", action="append", help="path to a seed Artifact (repeatable)")
    p_tick.set_defaults(func=cmd_loopx_tick)
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `.venv/bin/pytest tests/test_cli.py -v`
Expected: PASS — all CLI tests, including the 2 new ones.

- [ ] **Step 5: Commit**

```bash
git add src/alphalayer/cli.py tests/test_cli.py
git commit -m "feat: add alphalayer loopx-tick CLI subcommand" \
  --author="Connor O'Dea <102129457+connorodea@users.noreply.github.com>"
```

---

### Task 6: Document the new command in `README.md`

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Add the new command to the `## CLI` section**

In the existing fenced code block under `## CLI`, add one line after the `inspect` line:

```bash
alphalayer loopx-tick my_flows.digest:flow --goal-id my-goal  # advance one stage, gated by LoopX
```

- [ ] **Step 2: Add a short paragraph after the CLI code block**

Insert directly after that fenced code block, before the `## Design notes` section:

```markdown
`loopx-tick` advances a Flow one stage per call, gated by a
[LoopX](https://github.com/connorodea/loopx) goal — `quota should-run` decides whether to
act, and the tick claims a todo, runs `Flow.step()`, writes back compact evidence, and
spends quota, so a Flow can run unattended across days under an external scheduler (a
cron job, Claude Code's native `/loop`, or any host that wakes this command once per
tick). See `docs/superpowers/specs/2026-08-06-loopx-integration-design.md` and
`VISION.md` for the design and roadmap.
```

- [ ] **Step 3: Verify the file renders sensibly**

Run: `.venv/bin/python -c "import pathlib; print(pathlib.Path('README.md').read_text()[:4000])"`
Expected: the new command line and paragraph appear between the CLI section and Design
notes, with no broken markdown fencing.

- [ ] **Step 4: Commit**

```bash
git add README.md
git commit -m "docs: document alphalayer loopx-tick in the README" \
  --author="Connor O'Dea <102129457+connorodea@users.noreply.github.com>"
```

---

### Task 7: Full verification pass and GOALS.md update

**Files:**
- Modify: `GOALS.md`

- [ ] **Step 1: Run the full test suite**

Run: `.venv/bin/pytest -v`
Expected: PASS — every test in the suite (pre-existing + all added in Tasks 1–5).

- [ ] **Step 2: Run lint and type checks**

Run: `.venv/bin/ruff check src tests`
Expected: no findings (fix inline and re-run if any surface — line length 100 per
`pyproject.toml`'s `[tool.ruff]`).

Run: `.venv/bin/mypy src`
Expected: no findings (`[tool.mypy]` is `strict = true` — pay particular attention to
`_run_loopx`'s `dict[str, Any]` return type and `TickResult`'s optional fields).

- [ ] **Step 3: Update `GOALS.md`**

Check off sub-goals 1a, 1b, and 1c under Goal 1 (`- [ ]` → `- [x]`). Leave 1d and 1e
unchecked — they need a live LoopX install/goal, which is out of this plan's scope (see
this plan's header). Add a changelog line:

```markdown
- 2026-08-06 v2 — Sub-goals 1a–1c shipped (Flow.step(), LoopXRunner, alphalayer
  loopx-tick, all with passing tests). 1d/1e need a live LoopX install and remain open.
```

Also bump the `Plan version` line at the top from `v1` to `v2`.

- [ ] **Step 4: Commit**

```bash
git add GOALS.md
git commit -m "docs: mark Goal 1 sub-goals 1a-1c done in GOALS.md" \
  --author="Connor O'Dea <102129457+connorodea@users.noreply.github.com>"
git push
```

---

## Self-Review Notes

- **Spec coverage:** every architecture element from
  `2026-08-06-loopx-integration-design.md` has a task — `Flow.step()` (Task 1),
  `LoopXRunner`/`TickResult` (Task 3), the CLI subcommand (Task 5), error handling
  (`LoopXNotInstalledError` + `RuntimeError` paths covered by Task 3's tests), evidence
  format (`<schema>@stage<N> -> <path>`, asserted in Task 3's tests). The spec's own
  "Open implementation questions" (exact flag names, `--agent-id` default) are
  deliberately *not* resolved here — they're sub-goal 1d, blocked on a live `loopx`
  install, and are called out in this plan's header and in Task 7.
- **Type consistency:** `TickResult` fields (`ran`, `artifact`, `flow_complete`,
  `reason`, `scheduler_hint`) are identical across Task 3's dataclass, its tests, and
  Task 5's CLI handler. `LoopXRunner.__init__`'s `goal_id`/`agent_id`/
  `available_capabilities` parameters match every call site. `Flow._run_one_stage` is
  used by both `run()` and `step()` with the same signature.
- **No placeholders:** every step above has literal, complete code — no "add tests for
  the above" or "handle errors appropriately" left unexpanded.
