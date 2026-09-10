# SPDX-License-Identifier: MPL-2.0
"""PLAN-030ic：运行时依赖探针与上传前 fail-fast。"""
from __future__ import annotations

import importlib.util
import os
import shutil
import sys
import urllib.error
import urllib.request
from collections.abc import Callable, Mapping
from pathlib import Path

from pydantic import ConfigDict, Field

from .capabilities import source_format_for_extension
from .models import ContractModel, SourceFormat
from .runtime import probe_runtime_capabilities
from .version_contract import check_locked_packages, load_contract, pdf2zh_site_packages


class ProbeResult(ContractModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    name: str
    ok: bool
    reason: str = Field(min_length=1)
    versions: dict[str, str] = Field(default_factory=dict)


class EnvironmentProbeReport(ContractModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    ok: bool
    probes: tuple[ProbeResult, ...]
    version_contract_ok: bool


def _sidecar_url(environment: Mapping[str, str] | None = None) -> str:
    env = os.environ if environment is None else environment
    contract = load_contract()
    sidecar = contract.get("sidecar") or {}
    return (
        env.get(str(sidecar.get("url_env") or "QYUNSLATION_SIDECAR_URL"), "").strip()
        or str(sidecar.get("default_url") or "http://127.0.0.1:8010")
    ).rstrip("/")


def probe_office(
    *,
    command_finder: Callable[[str], str | None] = shutil.which,
) -> ProbeResult:
    contract = load_contract()
    office = contract.get("office") or {}
    commands = tuple(office.get("commands") or ("soffice", "libreoffice"))
    needle = str(office.get("version_stdout_contains") or "LibreOffice")
    executable = None
    for name in commands:
        if path := command_finder(name):
            executable = path
            break
    if not executable:
        return ProbeResult(
            name="office",
            ok=False,
            reason="Office converter executable not found",
            versions={"executable": "missing"},
        )
    import subprocess

    proc = subprocess.run(
        [executable, "--version"],
        capture_output=True,
        text=True,
        check=False,
    )
    stdout = (proc.stdout or proc.stderr or "").strip()
    ok = proc.returncode == 0 and needle in stdout
    return ProbeResult(
        name="office",
        ok=ok,
        reason=stdout.splitlines()[0] if stdout else "soffice --version failed",
        versions={"executable": executable, "version_line": stdout.splitlines()[0] if stdout else ""},
    )


def probe_sidecar(
    *,
    environment: Mapping[str, str] | None = None,
    opener: Callable[[str], object] | None = None,
) -> ProbeResult:
    url = _sidecar_url(environment)
    if opener is None:
        def _default_opener(target: str) -> object:
            return urllib.request.urlopen(target, timeout=3)

        opener = _default_opener
    try:
        with opener(f"{url}/") as response:  # type: ignore[union-attr]
            status = getattr(response, "status", None) or getattr(response, "getcode", lambda: 0)()
        ok = int(status) < 500
        return ProbeResult(
            name="sidecar",
            ok=ok,
            reason=f"HTTP {status}",
            versions={"url": url},
        )
    except urllib.error.URLError as exc:
        return ProbeResult(name="sidecar", ok=False, reason=str(exc.reason or exc), versions={"url": url})
    except Exception as exc:
        return ProbeResult(name="sidecar", ok=False, reason=str(exc), versions={"url": url})


def probe_babeldoc_layout(*, site_packages: os.PathLike[str] | None = None) -> ProbeResult:
    import subprocess

    contract = load_contract()
    module_name = str(contract.get("babeldoc_layout_module") or "babeldoc")
    site = Path(site_packages) if site_packages is not None else pdf2zh_site_packages()
    from .version_contract import package_version

    version_text = package_version("babeldoc", context="pdf2zh")
    if not version_text:
        return ProbeResult(
            name="babeldoc_layout",
            ok=False,
            reason="babeldoc not installed in pdf2zh venv",
            versions={"site": str(site)},
        )
    code = (
        "import importlib, sys; "
        f"sys.path.insert(0, {str(site)!r}); "
        f"importlib.import_module({module_name!r}); "
        "print('ok')"
    )
    proc = subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True,
        text=True,
        check=False,
    )
    ok = proc.returncode == 0
    reason = (proc.stderr or proc.stdout or "import failed").strip().splitlines()[-1]
    return ProbeResult(
        name="babeldoc_layout",
        ok=ok,
        reason="import ok" if ok else reason,
        versions={"babeldoc": version_text, "module": module_name},
    )


def probe_image_decoders(
    *,
    module_available: Callable[[str], bool] | None = None,
) -> ProbeResult:
    if module_available is None:
        module_available = lambda name: importlib.util.find_spec(name) is not None
    contract = load_contract()
    required = tuple(contract.get("image_core_extensions") or ())
    if not module_available("PIL"):
        return ProbeResult(
            name="image_decoders",
            ok=False,
            reason="Pillow not installed",
            versions={"Pillow": "missing"},
        )
    from PIL import Image

    Image.init()
    registered = {ext.lower() for ext in Image.registered_extensions()}
    missing = [ext for ext in required if ext.lower() not in registered]
    try:
        from importlib.metadata import version as pkg_version

        pillow_version = pkg_version("pillow")
    except Exception:
        pillow_version = "unknown"
    if missing:
        return ProbeResult(
            name="image_decoders",
            ok=False,
            reason=f"missing codecs: {', '.join(missing)}",
            versions={"Pillow": pillow_version},
        )
    return ProbeResult(
        name="image_decoders",
        ok=True,
        reason="core image codecs available",
        versions={"Pillow": pillow_version},
    )


def probe_version_contract(*, context: str | None = None) -> ProbeResult:
    checks = check_locked_packages(context=context)
    versions = {name: info["installed"] for name, ok, _, info in checks for _ in [0] if True}
    versions.update({f"{name}_minimum": info["minimum"] for name, _, _, info in checks})
    failed = [name for name, ok, reason, _ in checks if not ok]
    if failed:
        detail = "; ".join(
            reason for name, ok, reason, _ in checks if not ok
        )
        return ProbeResult(
            name="version_contract",
            ok=False,
            reason=detail or f"failed: {', '.join(failed)}",
            versions=versions,
        )
    return ProbeResult(name="version_contract", ok=True, reason="all packages satisfy lock", versions=versions)


def run_environment_probes(
    *,
    include_sidecar: bool = True,
    include_babeldoc: bool = True,
    version_context: str | None = None,
    environment: Mapping[str, str] | None = None,
) -> EnvironmentProbeReport:
    snapshot = probe_runtime_capabilities()
    probes = [
        probe_version_contract(context=version_context),
        probe_office(),
        probe_image_decoders(),
        ProbeResult(
            name="runtime_features",
            ok=bool(snapshot.available_features),
            reason="runtime feature inventory",
            versions={"available_count": str(len(snapshot.available_features))},
        ),
    ]
    if include_babeldoc:
        probes.insert(2, probe_babeldoc_layout())
    if include_sidecar:
        probes.append(probe_sidecar(environment=environment))
    version_ok = probes[0].ok
    ok = all(item.ok for item in probes if item.name != "sidecar") and version_ok
    # sidecar failure is only fatal when explicitly required by caller
    return EnvironmentProbeReport(ok=ok, probes=tuple(probes), version_contract_ok=version_ok)


def _format_requires_office(source_format: SourceFormat) -> bool:
    return source_format in {SourceFormat.DOC, SourceFormat.PPT, SourceFormat.PPTX}


def assert_environment_for_upload(
    source_format: SourceFormat,
    *,
    environment: Mapping[str, str] | None = None,
) -> None:
    """Fail closed before task creation when hard dependencies are missing."""

    if source_format is SourceFormat.UNKNOWN:
        return
    report = run_environment_probes(
        include_sidecar=False,
        include_babeldoc=False,
        version_context="qyunslation",
        environment=environment,
    )
    failures: list[str] = []
    if not report.version_contract_ok:
        failures.append("版本契约未满足")
    image_formats = {
        SourceFormat.PNG,
        SourceFormat.JPEG,
        SourceFormat.WEBP,
        SourceFormat.BMP,
        SourceFormat.TIFF,
    }
    for probe in report.probes:
        if probe.name == "version_contract":
            continue
        if probe.name == "sidecar":
            continue
        if probe.name == "office" and not _format_requires_office(source_format):
            continue
        if probe.name == "image_decoders" and source_format not in image_formats:
            continue
        if not probe.ok:
            failures.append(f"{probe.name}: {probe.reason}")
    if failures:
        from .ingest import InputPreparationError

        raise InputPreparationError(
            "RUNTIME_ENVIRONMENT_UNAVAILABLE",
            "；".join(failures),
            http_status=503,
        )


def assert_environment_for_filename(
    filename: str | None,
    *,
    environment: Mapping[str, str] | None = None,
) -> None:
    ext = (Path(filename).suffix if filename else "").lower()
    source_format = source_format_for_extension(ext) if ext else SourceFormat.UNKNOWN
    assert_environment_for_upload(source_format, environment=environment)
