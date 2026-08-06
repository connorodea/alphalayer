"""AlphaLayer's exception hierarchy — one root, one per failure mode a caller might want to
catch specifically (an ambiguous discovery vs. a missing artifact vs. a schema mismatch are
different problems with different fixes)."""

from __future__ import annotations


class AlphaLayerError(Exception):
    """Base class for every error this library raises on purpose."""


class ArtifactNotFoundError(AlphaLayerError):
    """No artifact matched what was asked for — in context, at an explicit path, or in a
    Flow's run directory."""


class AmbiguousArtifactError(AlphaLayerError):
    """More than one plausible artifact matched — the caller must disambiguate rather than
    have this library silently guess."""


class SchemaMismatchError(AlphaLayerError):
    """A Layer's declared `consumes_schema` wasn't present among the artifacts handed to it."""
