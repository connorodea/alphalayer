"""The Artifact Contract, as code: a small header (flow/stage/layer/schema/upstream) plus
content, serialized as a markdown file with a YAML-ish front-matter block. This is the same
contract AlphaLayer's Claude-Code skills follow by hand (see the `alphalayer` Claude skill's
`references/artifact-contract.md`) — this module is the executable version of that spec, so
a Python pipeline and a Claude-driven one can read each other's output interchangeably.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from .exceptions import AmbiguousArtifactError, ArtifactNotFoundError

_FRONT_MATTER_RE = re.compile(r"\A---\n(.*?)\n---\n?", re.DOTALL)


def _render(value: str | int | None) -> str:
    return "none" if value is None else str(value)


def _parse(value: str) -> str | None:
    return None if value in ("none", "None", "") else value


@dataclass
class Artifact:
    """A piece of output produced by a Skill or Layer, carrying enough provenance for the
    next stage to find and trust it without being told where it lives.

    `layer` and `schema` are the two fields every producer must set meaningfully; `flow`,
    `stage`, and `upstream` are normally filled in by `Flow.run()` rather than by hand.
    """

    layer: str
    schema: str
    content: str
    flow: str | None = None
    stage: int | None = None
    upstream: str | None = None
    path: Path | None = field(default=None, compare=False)

    _HEADER_FIELDS = ("flow", "stage", "layer", "schema", "upstream")

    def to_text(self) -> str:
        lines = ["---"]
        for name in self._HEADER_FIELDS:
            lines.append(f"{name}: {_render(getattr(self, name))}")
        lines.append("---")
        return "\n".join(lines) + "\n" + self.content

    @classmethod
    def from_text(cls, text: str, *, path: Path | None = None) -> Artifact:
        match = _FRONT_MATTER_RE.match(text)
        if not match:
            raise ValueError(
                "no AlphaLayer header block found — expected a '---' delimited block "
                "(flow/stage/layer/schema/upstream) at the very top of the file"
            )
        raw: dict[str, str] = {}
        for line in match.group(1).splitlines():
            if not line.strip() or ":" not in line:
                continue
            key, _, value = line.partition(":")
            raw[key.strip()] = value.strip()

        stage_raw = _parse(raw.get("stage", "none"))
        return cls(
            flow=_parse(raw.get("flow", "none")),
            stage=int(stage_raw) if stage_raw is not None else None,
            layer=raw.get("layer", ""),
            schema=raw.get("schema", ""),
            upstream=_parse(raw.get("upstream", "none")),
            content=text[match.end():],
            path=path,
        )

    def save(self, target: Path) -> Path:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(self.to_text(), encoding="utf-8")
        self.path = target
        return target

    @classmethod
    def load(cls, source: Path) -> Artifact:
        if not source.exists():
            raise ArtifactNotFoundError(f"no artifact at {source}")
        return cls.from_text(source.read_text(encoding="utf-8"), path=source)

    @classmethod
    def discover(
        cls,
        schema: str,
        *,
        context: list[Artifact] | None = None,
        explicit_path: Path | str | None = None,
        flow_dir: Path | None = None,
    ) -> Artifact:
        """The Artifact Contract's discovery order, as code: an explicit path wins outright;
        otherwise look in `context` (typically the artifacts a Flow has produced so far);
        otherwise search `flow_dir` on disk for the highest-`stage` file whose schema
        matches. Raises `ArtifactNotFoundError`/`AmbiguousArtifactError` rather than
        guessing — callers decide what to do when discovery doesn't resolve cleanly (a
        script might re-raise to the user; a Claude-driven Layer would ask)."""
        if explicit_path is not None:
            return cls.load(Path(explicit_path))

        if context:
            matches = [a for a in context if a.schema == schema]
            if len(matches) == 1:
                return matches[0]
            if len(matches) > 1:
                raise AmbiguousArtifactError(
                    f"{len(matches)} artifacts in context match schema {schema!r} — "
                    "pass explicit_path to disambiguate"
                )

        if flow_dir is not None and flow_dir.is_dir():
            candidates: list[Artifact] = []
            for candidate_path in sorted(flow_dir.glob("*.md")):
                try:
                    candidate = cls.load(candidate_path)
                except (ValueError, ArtifactNotFoundError):
                    continue
                if candidate.schema == schema:
                    candidates.append(candidate)
            if candidates:
                candidates.sort(key=lambda a: a.stage if a.stage is not None else -1)
                return candidates[-1]

        raise ArtifactNotFoundError(
            f"no artifact matching schema {schema!r} found in context, explicit_path, or {flow_dir}"
        )

    def __repr__(self) -> str:
        loc = f" @ {self.path}" if self.path else ""
        return f"Artifact(layer={self.layer!r}, schema={self.schema!r}, stage={self.stage}{loc})"
