from __future__ import annotations

from alphalayer import Artifact, LLMSkill


class FakeBackend:
    """A stand-in Backend so LLMSkill's own logic is testable without a real API call —
    the same injectable-transport pattern real backends (Anthropic/OpenAI) are wrapped
    behind, so nothing here needs network access or credentials."""

    def __init__(self) -> None:
        self.calls: list[dict] = []

    def complete(self, *, system: str, prompt: str, max_tokens: int = 4096) -> str:
        self.calls.append({"system": system, "prompt": prompt, "max_tokens": max_tokens})
        return f"response to: {prompt}"


def test_llm_skill_calls_backend_and_wraps_the_response() -> None:
    backend = FakeBackend()
    skill = LLMSkill(backend, system_prompt="be helpful", produces_schema="reply-v1", name="chat")
    result = skill.run(Artifact(layer="seed", schema="question-v1", content="what's 2+2?"))

    assert result.schema == "reply-v1"
    assert result.layer == "chat"
    assert result.content == "response to: what's 2+2?"
    assert backend.calls[0]["system"] == "be helpful"


def test_llm_skill_joins_multiple_inputs() -> None:
    backend = FakeBackend()
    skill = LLMSkill(backend, system_prompt="s", produces_schema="out-v1")
    a = Artifact(layer="a", schema="x", content="first")
    b = Artifact(layer="b", schema="y", content="second")
    skill.run(a, b)
    assert "first" in backend.calls[0]["prompt"]
    assert "second" in backend.calls[0]["prompt"]


def test_llm_skill_handles_no_inputs() -> None:
    backend = FakeBackend()
    skill = LLMSkill(backend, system_prompt="s", produces_schema="out-v1")
    result = skill.run()
    assert result.content == "response to: "


def test_from_skill_md_loads_the_file_as_the_system_prompt(tmp_path) -> None:
    skill_dir = tmp_path / "my-skill"
    skill_dir.mkdir()
    skill_md = skill_dir / "SKILL.md"
    skill_md.write_text("# My Skill\n\nDo the thing.\n")

    backend = FakeBackend()
    skill = LLMSkill.from_skill_md(skill_md, backend, produces_schema="thing-v1")

    assert skill.name == "my-skill"
    assert "Do the thing." in skill.system_prompt
    result = skill.run(Artifact(layer="seed", schema="in-v1", content="go"))
    assert result.schema == "thing-v1"
