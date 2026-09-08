from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from qyunslation.structure import ManifestStore, PdfStructureScanner
from qyunslation.structure.interfaces import ManifestConsumer, StructureScanner
from qyunslation.structure.manifest_store import default_cache_root

ROOT = Path(__file__).resolve().parents[2]
LJAE = ROOT / "tests/fixtures/structure/reference/ljae439.pdf"


@pytest.fixture(scope="module")
def manifest():
    return PdfStructureScanner().scan(LJAE)


def test_round_trip_preserves_every_field(tmp_path, manifest):
    store = ManifestStore(tmp_path)

    assert store.put(manifest) is not None
    loaded = store.get(manifest.document.source_sha256)

    assert loaded is not None
    assert loaded.model_dump_json() == manifest.model_dump_json()


def test_store_satisfies_manifest_consumer_protocol(tmp_path, manifest):
    store = ManifestStore(tmp_path)

    assert isinstance(store, ManifestConsumer)
    store.consume(manifest)

    assert store.get(manifest.document.source_sha256) is not None


def test_scanner_satisfies_structure_scanner_protocol():
    assert isinstance(PdfStructureScanner(), StructureScanner)


def test_miss_returns_none_for_unknown_and_malformed_keys(tmp_path):
    store = ManifestStore(tmp_path)

    assert store.get("0" * 64) is None
    assert store.get("not-a-hash") is None
    assert store.get("") is None


def test_schema_major_mismatch_is_treated_as_miss(tmp_path, manifest):
    store = ManifestStore(tmp_path)
    store.put(manifest)
    target = store.path_for(manifest.document.source_sha256)

    payload = json.loads(target.read_text(encoding="utf-8"))
    payload["schema_version"] = "2.0.0"
    target.write_text(json.dumps(payload), encoding="utf-8")

    assert store.get(manifest.document.source_sha256) is None


def test_corrupt_payload_is_treated_as_miss(tmp_path, manifest):
    store = ManifestStore(tmp_path)
    store.put(manifest)
    target = store.path_for(manifest.document.source_sha256)

    target.write_text("{ this is not json", encoding="utf-8")

    assert store.get(manifest.document.source_sha256) is None


def test_key_mismatch_between_filename_and_payload_is_a_miss(tmp_path, manifest):
    store = ManifestStore(tmp_path)
    store.put(manifest)
    target = store.path_for(manifest.document.source_sha256)

    other = target.with_name(f"{'a' * 64}.manifest.json")
    other.write_text(target.read_text(encoding="utf-8"), encoding="utf-8")

    assert store.get("a" * 64) is None


def test_unwritable_root_degrades_instead_of_raising(tmp_path, manifest):
    blocked = tmp_path / "blocked"
    blocked.mkdir()
    blocked.chmod(0o500)
    store = ManifestStore(blocked / "nested")
    try:
        assert store.put(manifest) is None
        assert store.get(manifest.document.source_sha256) is None
    finally:
        blocked.chmod(0o700)


def test_put_leaves_no_temporary_files(tmp_path, manifest):
    store = ManifestStore(tmp_path)
    target = store.put(manifest)

    assert target is not None
    leftovers = [p.name for p in target.parent.iterdir() if p.name.startswith(".manifest-")]
    assert leftovers == []


def test_overwrite_is_atomic_and_keeps_latest(tmp_path, manifest):
    store = ManifestStore(tmp_path)
    store.put(manifest)
    store.put(manifest)

    target = store.path_for(manifest.document.source_sha256)
    files = sorted(p.name for p in target.parent.iterdir())

    assert files == [target.name]
    assert store.get(manifest.document.source_sha256) is not None


def test_invalidate_removes_the_entry(tmp_path, manifest):
    store = ManifestStore(tmp_path)
    store.put(manifest)

    assert store.invalidate(manifest.document.source_sha256) is True
    assert store.get(manifest.document.source_sha256) is None
    assert store.invalidate(manifest.document.source_sha256) is False


def test_cache_root_honours_environment_override(monkeypatch, tmp_path):
    monkeypatch.setenv("QYUNSLATION_MANIFEST_CACHE", str(tmp_path / "custom"))

    assert default_cache_root() == tmp_path / "custom"


def test_cache_root_falls_back_to_xdg(monkeypatch, tmp_path):
    monkeypatch.delenv("QYUNSLATION_MANIFEST_CACHE", raising=False)
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path))

    assert default_cache_root() == tmp_path / "qyunslation" / "manifests"


def test_path_is_partitioned_by_schema_major(tmp_path, manifest):
    store = ManifestStore(tmp_path)
    target = store.path_for(manifest.document.source_sha256)

    assert target.parent.name.startswith("v")
    assert target.name.endswith(".manifest.json")


def test_production_package_does_not_hardcode_a_developer_path():
    source = (
        ROOT / "qyunslation/structure/manifest_store.py"
    ).read_text(encoding="utf-8")

    assert "/home/dev" not in source
    assert os.sep + "pdf2zh" not in source
