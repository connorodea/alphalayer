"""Skill: the atomic tier. Does one job, produces an Artifact, doesn't know or care what
happens to it next."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Callable
from typing import TYPE_CHECKING

from .artifact import Artifact

if TYPE_CHECKING:
    from .flow import Flow


class Skill(ABC):
    """An atomic capability. Subclass and implement `run`; `name` defaults to the class
    name and is what lands in a produced Artifact's `layer` field once a Flow runs it —
    override it in `__init__` if you want a shorter or more stable identifier."""

    def __init__(self, name: str | None = None) -> None:
        self.name = name or type(self).__name__

    @abstractmethod
    def run(self, *inputs: Artifact) -> Artifact:
        """Do the work. Return a fresh Artifact — never mutate an input Artifact in place,
        since the same input may still be needed by a sibling stage or by the caller."""

    def __or__(self, other: Skill) -> Flow:
        from .flow import Flow  # imported lazily to avoid a skill<->flow circular import

        return Flow(name=f"{self.name}->{other.name}").then(self).then(other)

    def __repr__(self) -> str:
        return f"{type(self).__name__}(name={self.name!r})"


def skill(
    fn: Callable[..., Artifact] | None = None, *, name: str | None = None
) -> Skill | Callable[[Callable[..., Artifact]], Skill]:
    """Decorator turning a plain function `(*Artifact) -> Artifact` into a Skill, for quick
    pure-Python capabilities that don't need a class:

        @skill
        def greet(*inputs: Artifact) -> Artifact:
            return Artifact(layer="greet", schema="greeting-v1", content="hello")
    """

    def _wrap(func: Callable[..., Artifact]) -> Skill:
        class _FunctionSkill(Skill):
            def run(self, *inputs: Artifact) -> Artifact:
                return func(*inputs)

        _FunctionSkill.__name__ = getattr(func, "__name__", "FunctionSkill")
        _FunctionSkill.__doc__ = func.__doc__
        return _FunctionSkill(name=name or getattr(func, "__name__", None))

    return _wrap(fn) if fn is not None else _wrap
