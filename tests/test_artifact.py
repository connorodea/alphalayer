from __future__ import annotations

import pytest

from alphalayer import AmbiguousArtifactError, Artifact, ArtifactNotFoundError


def test_round_trips_through_text() -> None:
    original = Artifact(
        layer="my-layer", schema="thing-v1", content="hello\nworld\n",
        flow="my-flow", stage=2, upstream="00-earlier.md",
    )
    restored = Artifact.from_text(original.to_text())
    assert restored.layer == "my-layer"
    assert restored.schema == "thing-v1"
    assert restored.content == "hello\nworld\n"
    assert restored.flow == "my-flow"
    assert restored.stage == 2
    assert restored.upstream == "00-earlier.md"


def test_none_fields_round_trip_as_none() -> None:
    art = Artifact(layer="l", schema="s", content="c")
    restored = Artifact.from_text(art.to_text())
    assert restored.flow is None
    assert restored.stage is None
    assert restored.upstream is None


def test_from_text_rejects_missing_header() -> None:
    with pytest.raises(ValueError):
        Artifact.from_text("just some content, no header\n")


def test_save_and_load_round_trip(tmp_path) -> None:
    art = Artifact(layer="l", schema="s", content="body")
    target = tmp_path / "out.md"
    art.save(target)
    assert art.path == target
    loaded = Artifact.load(target)
    assert loaded.content == "body"
    assert loaded.path == target


def test_load_missing_file_raises(tmp_path) -> None:
    with pytest.raises(ArtifactNotFoundError):
        Artifact.load(tmp_path / "does-not-exist.md")


def test_discover_prefers_explicit_path(tmp_path) -> None:
    art = Artifact(layer="l", schema="s", content="c")
    target = tmp_path / "x.md"
    art.save(target)
    found = Artifact.discover("s", explicit_path=target)
    assert found.path == target


def test_discover_finds_unique_match_in_context() -> None:
    a = Artifact(layer="a", schema="alpha", content="a")
    b = Artifact(layer="b", schema="beta", content="b")
    found = Artifact.discover("beta", context=[a, b])
    assert found is b


def test_discover_raises_on_ambiguous_context() -> None:
    a = Artifact(layer="a", schema="alpha", content="a")
    b = Artifact(layer="b", schema="alpha", content="b")
    with pytest.raises(AmbiguousArtifactError):
        Artifact.discover("alpha", context=[a, b])


def test_discover_searches_flow_dir_for_highest_stage(tmp_path) -> None:
    Artifact(layer="l", schema="s", stage=0, content="first").save(tmp_path / "00-l.md")
    Artifact(layer="l", schema="s", stage=1, content="second").save(tmp_path / "01-l.md")
    found = Artifact.discover("s", flow_dir=tmp_path)
    assert found.content == "second"


def test_discover_raises_when_nothing_matches(tmp_path) -> None:
    with pytest.raises(ArtifactNotFoundError):
        Artifact.discover("missing-schema", flow_dir=tmp_path)


def test_discover_skips_malformed_files_in_flow_dir(tmp_path) -> None:
    (tmp_path / "not-an-artifact.md").write_text("no header block here\n")
    Artifact(layer="l", schema="s", stage=0, content="ok").save(tmp_path / "00-l.md")
    found = Artifact.discover("s", flow_dir=tmp_path)
    assert found.content == "ok"


def test_header_parsing_skips_blank_and_colon_free_lines() -> None:
    text = "---\nflow: f\n\nnot-a-field-line\nstage: 0\nlayer: l\nschema: s\nupstream: none\n---\nbody\n"
    art = Artifact.from_text(text)
    assert art.flow == "f"
    assert art.stage == 0
    assert art.content == "body\n"


def test_repr_includes_path_when_saved(tmp_path) -> None:
    art = Artifact(layer="l", schema="s", content="c")
    assert " @ " not in repr(art)
    art.save(tmp_path / "x.md")
    assert " @ " in repr(art)
