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
