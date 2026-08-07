"""Optional LLM backends for `LLMSkill` — the bridge between a skill authored for
interactive Claude Code use (a SKILL.md file) and a headless, scripted run. Nothing in this
module is imported eagerly by anything that needs the vendor SDK to be installed; each
Backend only imports its SDK inside `__init__`, so `pip install alphalayer` alone never
requires `anthropic`/`openai` — only `pip install alphalayer[anthropic]` etc. does.
"""

from __future__ import annotations

from pathlib import Path
from typing import Protocol

from .artifact import Artifact
from .skill import Skill


class Backend(Protocol):
    """A pluggable text-completion backend an LLM-driven Skill can call."""

    def complete(self, *, system: str, prompt: str, max_tokens: int = 4096) -> str: ...


class AnthropicBackend:
    """Wraps the `anthropic` SDK. Requires `pip install alphalayer[anthropic]`."""

    def __init__(self, *, model: str = "claude-opus-4-8", api_key: str | None = None) -> None:
        try:
            import anthropic  # type: ignore[import-not-found]
        except ImportError as exc:  # pragma: no cover - exercised only without the extra
            raise ImportError(
                "AnthropicBackend requires the anthropic package: "
                "pip install alphalayer[anthropic]"
            ) from exc
        self._client = anthropic.Anthropic(api_key=api_key)
        self.model = model

    def complete(self, *, system: str, prompt: str, max_tokens: int = 4096) -> str:
        response = self._client.messages.create(
            model=self.model,
            max_tokens=max_tokens,
            system=system,
            messages=[{"role": "user", "content": prompt}],
        )
        return "".join(block.text for block in response.content if block.type == "text")


class OpenAIBackend:
    """Wraps the `openai` SDK's Responses API. Requires `pip install alphalayer[openai]`."""

    def __init__(self, *, model: str = "gpt-5", api_key: str | None = None) -> None:
        try:
            import openai  # type: ignore[import-not-found]
        except ImportError as exc:  # pragma: no cover - exercised only without the extra
            raise ImportError(
                "OpenAIBackend requires the openai package: pip install alphalayer[openai]"
            ) from exc
        self._client = openai.OpenAI(api_key=api_key)
        self.model = model

    def complete(self, *, system: str, prompt: str, max_tokens: int = 4096) -> str:
        response = self._client.responses.create(
            model=self.model,
            instructions=system,
            input=prompt,
            max_output_tokens=max_tokens,
        )
        return str(response.output_text)


class LLMSkill(Skill):
    """A Skill whose `run` delegates to a Backend — give it a system prompt and it turns a
    Backend's response into an Artifact. Concatenates any input artifacts' content as the
    user turn, joined by a separator, so it composes into a Flow like any other Skill.
    """

    def __init__(
        self,
        backend: Backend,
        *,
        system_prompt: str,
        produces_schema: str,
        name: str | None = None,
        max_tokens: int = 4096,
    ) -> None:
        super().__init__(name=name)
        self.backend = backend
        self.system_prompt = system_prompt
        self.produces_schema = produces_schema
        self.max_tokens = max_tokens

    @classmethod
    def from_skill_md(
        cls,
        path: Path | str,
        backend: Backend,
        *,
        produces_schema: str,
        name: str | None = None,
        max_tokens: int = 4096,
    ) -> LLMSkill:
        """Load an existing Claude Code SKILL.md as the system prompt — run a skill that
        was authored for interactive use headlessly, unattended, via the API instead."""
        skill_path = Path(path)
        text = skill_path.read_text(encoding="utf-8")
        return cls(
            backend,
            system_prompt=text,
            produces_schema=produces_schema,
            name=name or skill_path.parent.name or skill_path.stem,
            max_tokens=max_tokens,
        )

    def run(self, *inputs: Artifact) -> Artifact:
        prompt = "\n\n---\n\n".join(a.content for a in inputs) if inputs else ""
        content = self.backend.complete(
            system=self.system_prompt, prompt=prompt, max_tokens=self.max_tokens
        )
        return Artifact(layer=self.name, schema=self.produces_schema, content=content)
