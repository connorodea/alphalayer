"""Layer: a Skill whose entire job is piping. It declares the schema it expects and the
schema it produces; `Flow` (and the base `Skill.run` contract) can then check adjacent
stages actually line up. A Layer does no original research or judgment beyond transforming
its input — if a "Layer" needs to do substantial original work, it should be a plain Skill.
"""

from __future__ import annotations

from collections.abc import Callable

from .artifact import Artifact
from .exceptions import SchemaMismatchError
from .skill import Skill


class Layer(Skill):
    """Set `consumes_schema`/`produces_schema` as class attributes (or per-instance in
    `__init__`) and implement `transform`, not `run` — `run` enforces the schema contract
    and then delegates to `transform`."""

    consumes_schema: str = ""
    produces_schema: str = ""

    def __init__(self, name: str | None = None, *, strict: bool = True) -> None:
        super().__init__(name=name)
        self.strict = strict

    def run(self, *inputs: Artifact) -> Artifact:
        if self.strict and self.consumes_schema and inputs and not any(
            a.schema == self.consumes_schema for a in inputs
        ):
            seen = ", ".join(sorted({a.schema for a in inputs})) or "(none)"
            raise SchemaMismatchError(
                f"{self.name} consumes schema {self.consumes_schema!r}; none of the "
                f"inputs matched (saw: {seen}). Pass strict=False to bypass."
            )
        result = self.transform(*inputs)
        if self.produces_schema:
            result.schema = self.produces_schema
        return result

    def transform(self, *inputs: Artifact) -> Artifact:
        raise NotImplementedError("Layer subclasses implement transform(), not run()")


def layer(
    fn: Callable[..., Artifact] | None = None,
    *,
    name: str | None = None,
    consumes: str = "",
    produces: str = "",
    strict: bool = True,
) -> Layer | Callable[[Callable[..., Artifact]], Layer]:
    """Decorator turning a plain function `(*Artifact) -> Artifact` into a Layer:

        @layer(consumes="audit-v1", produces="tasks-v1")
        def audit_to_tasks(*inputs: Artifact) -> Artifact:
            ...
    """

    def _wrap(func: Callable[..., Artifact]) -> Layer:
        class _FunctionLayer(Layer):
            consumes_schema = consumes
            produces_schema = produces

            def transform(self, *inputs: Artifact) -> Artifact:
                return func(*inputs)

        _FunctionLayer.__name__ = getattr(func, "__name__", "FunctionLayer")
        _FunctionLayer.__doc__ = func.__doc__
        return _FunctionLayer(name=name or getattr(func, "__name__", None), strict=strict)

    return _wrap(fn) if fn is not None else _wrap
