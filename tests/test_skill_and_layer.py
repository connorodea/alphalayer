from __future__ import annotations

import pytest

from alphalayer import Artifact, Layer, SchemaMismatchError, Skill, layer, skill


class Uppercase(Skill):
    def run(self, *inputs: Artifact) -> Artifact:
        text = inputs[0].content if inputs else ""
        return Artifact(layer=self.name, schema="upper-v1", content=text.upper())


class AddExclaim(Layer):
    consumes_schema = "upper-v1"
    produces_schema = "excited-v1"

    def transform(self, *inputs: Artifact) -> Artifact:
        return Artifact(layer=self.name, schema=self.produces_schema, content=inputs[-1].content + "!")


def test_skill_name_defaults_to_class_name() -> None:
    assert Uppercase().name == "Uppercase"


def test_skill_name_override() -> None:
    assert Uppercase(name="shout").name == "shout"


def test_layer_enforces_consumes_schema() -> None:
    bad_input = Artifact(layer="x", schema="wrong-schema", content="hi")
    with pytest.raises(SchemaMismatchError):
        AddExclaim().run(bad_input)


def test_layer_strict_false_bypasses_check() -> None:
    bad_input = Artifact(layer="x", schema="wrong-schema", content="hi")
    result = AddExclaim(strict=False).run(bad_input)
    assert result.content == "hi!"


def test_layer_stamps_produces_schema_even_if_transform_forgets() -> None:
    class Careless(Layer):
        consumes_schema = "upper-v1"
        produces_schema = "careless-v1"

        def transform(self, *inputs: Artifact) -> Artifact:
            return Artifact(layer=self.name, schema="wrong", content="x")

    good_input = Artifact(layer="x", schema="upper-v1", content="hi")
    result = Careless().run(good_input)
    assert result.schema == "careless-v1"


def test_skill_decorator() -> None:
    @skill
    def echo(*inputs: Artifact) -> Artifact:
        return Artifact(layer="echo", schema="echo-v1", content="echoed")

    assert isinstance(echo, Skill)
    assert echo.name == "echo"
    assert echo.run().content == "echoed"


def test_layer_decorator_enforces_schema() -> None:
    @layer(consumes="in-v1", produces="out-v1")
    def double(*inputs: Artifact) -> Artifact:
        return Artifact(layer="double", schema="out-v1", content=inputs[-1].content * 2)

    assert isinstance(double, Layer)
    with pytest.raises(SchemaMismatchError):
        double.run(Artifact(layer="x", schema="not-in-v1", content="ab"))
    result = double.run(Artifact(layer="x", schema="in-v1", content="ab"))
    assert result.content == "abab"


def test_skill_pipe_operator_builds_a_two_stage_flow() -> None:
    flow = Uppercase() | AddExclaim()
    result = flow.run(Artifact(layer="seed", schema="raw-v1", content="hi"))
    assert result.content == "HI!"
    assert [a.layer for a in flow.artifacts()] == ["Uppercase", "AddExclaim"]
