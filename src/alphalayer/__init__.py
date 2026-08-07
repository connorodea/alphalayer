"""AlphaLayer — a compositing framework for AI skills.

Three tiers, borrowed from video/image compositing:

- **Skill** — an atomic capability. Does one job, produces an `Artifact`.
- **Layer** — a `Skill` whose entire job is piping: declares the schema it consumes and
  produces, transforming upstream output rather than doing original work.
- **Flow** — a named, ordered chain of Skills/Layers, composable with `|`:

    from alphalayer import Flow
    flow = Flow("my-pipeline") | SomeSkill() | SomeLayer() | AnotherLayer()
    result = flow.run()

Every artifact a Skill/Layer produces carries a small provenance header (which flow, which
stage, what schema, what it was built from) so the next stage — in this process, or a fresh
one picking the same Flow back up later — can find and trust its input without being told
where it lives. See `Artifact.discover` and `Flow.run(resume=True)`.
"""

from __future__ import annotations

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
