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
        check=False,
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
