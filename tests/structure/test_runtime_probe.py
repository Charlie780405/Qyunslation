from __future__ import annotations

from qyunslation.structure.models import SourceFormat
from qyunslation.structure.runtime_probe import (
    EnvironmentProbeReport,
    ProbeResult,
    assert_environment_for_upload,
    probe_office,
    probe_version_contract,
    run_environment_probes,
)
from qyunslation.structure.version_contract import parse_semver, version_gte


def test_semver_comparison():
    assert version_gte("1.28.2", "1.25.0")
    assert not version_gte("1.24.9", "1.25.0")
    assert parse_semver("2.9.0") == (2, 9, 0)


def test_probe_office_missing_executable():
    result = probe_office(command_finder=lambda _name: None)
    assert isinstance(result, ProbeResult)
    assert result.name == "office"
    assert result.ok is False


def test_version_contract_probe_runs():
    result = probe_version_contract()
    assert result.name == "version_contract"
    assert "minimum" in "".join(result.versions.values()) or result.versions


def test_environment_report_has_core_probes():
    report = run_environment_probes(include_sidecar=False, include_babeldoc=True)
    names = {item.name for item in report.probes}
    assert {"version_contract", "office", "babeldoc_layout", "image_decoders"} <= names


def test_assert_environment_skips_unknown_format():
    assert_environment_for_upload(SourceFormat.UNKNOWN)


def test_upload_probe_uses_qyunslation_version_context():
    report = run_environment_probes(
        include_sidecar=False,
        include_babeldoc=False,
        version_context="qyunslation",
    )
    names = {item.name for item in report.probes}
    assert "babeldoc_layout" not in names


def test_image_upload_requires_decoders(monkeypatch):
    monkeypatch.setattr(
        "qyunslation.structure.runtime_probe.run_environment_probes",
        lambda **_: EnvironmentProbeReport(
            ok=False,
            probes=(
                ProbeResult(name="version_contract", ok=True, reason="ok"),
                ProbeResult(name="image_decoders", ok=False, reason="missing"),
            ),
            version_contract_ok=True,
        ),
    )
    from qyunslation.structure.ingest import InputPreparationError

    try:
        assert_environment_for_upload(SourceFormat.PNG)
    except InputPreparationError as exc:
        assert exc.code == "RUNTIME_ENVIRONMENT_UNAVAILABLE"
    else:
        raise AssertionError("expected fail-closed for missing image decoders")
