#!/usr/bin/env python3
# SPDX-License-Identifier: MPL-2.0
"""PLAN-071a：探测 pdf2zh_next / BabelDOC 安装中的已知补丁标记。

不修改第三方文件。缺省安装路径时仍输出结构化 JSON，供任务快照登记。
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
DEFAULT_SITE = (
    Path.home()
    / ".local/share/uv/tools/pdf2zh-next/lib/python3.12/site-packages"
)

# (patch_id, apply_script, marker, relative_target_hint)
# target_hint is under site-packages; empty means "any readable target / gui"
KNOWN_PATCHES: list[tuple[str, str, str, str]] = [
    ("throughput-unload", "apply-pdf2zh-throughput.py", "_cancel_active_translation_on_unload", "pdf2zh_next/gui.py"),
    ("throughput-skip", "apply-pdf2zh-throughput.py", "_pdf2zh_skip_already_target_lang", ""),
    ("hpd", "apply-pdf2zh-hpd.py", "from hpd_ocr import ocr_pdf_with_hpd, pdf_needs_hpd", "pdf2zh_next/gui.py"),
    ("docimg-imgtr", "apply-pdf2zh-docimg.py", "_qy_imgtr_post", "pdf2zh_next/gui.py"),
    ("docimg-tbltr", "apply-pdf2zh-docimg.py", "_qy_tbltr", "pdf2zh_next/gui.py"),
    ("docprofile-letter", "apply-pdf2zh-docprofile.py", "_qy_letter_reflow", "pdf2zh_next/gui.py"),
    ("docprofile-graphic", "apply-pdf2zh-docprofile.py", "_qy_graphic_reinsert", "pdf2zh_next/gui.py"),
    ("ocr-base", "apply-pdf2zh-ocr-base.py", "_qy_ocr_base_ops", "pdf2zh_next/gui.py"),
    ("office-route", "apply-pdf2zh-office-route.py", "_qy_office_sidecar", "pdf2zh_next/gui.py"),
    ("042b", "apply-pdf2zh-042b-short-label.py", "_qy_042b_short_label_direct", ""),
    ("045c", "apply-pdf2zh-045c-sanitize.py", "_QY_045C_SANITIZE", ""),
    ("046b", "apply-pdf2zh-046b-para-merge.py", "_QY_046B_PARA_MERGE", ""),
    ("047c", "apply-pdf2zh-047c-no-drop.py", "_QY_047C_NO_DROP", "babeldoc/format/pdf/document_il/backend/pdf_creater.py"),
    ("047d", "apply-pdf2zh-047d-para-layout.py", "_QY_047D_PARA_LAYOUT", ""),
    ("033h", "apply-pdf2zh-fidelity-033h.py", "_QY_033H_PRESERVE", ""),
    ("060-term-bridge", "apply-pdf2zh-060-termbase-workbench.py", "_qy_060_term_bridge_runtime", "pdf2zh_next/gui.py"),
    ("050-workbench", "apply-pdf2zh-050-workbench.py", "_qy_050_workbench_js", "pdf2zh_next/gui.py"),
]


@dataclass
class PatchFinding:
    patch_id: str
    apply_script: str
    marker: str
    present: bool
    target: str | None
    classify_hint: str


def resolve_site(explicit: str | None) -> Path:
    if explicit:
        return Path(explicit).expanduser().resolve()
    env = os.environ.get("QYUNSLATION_PDF2ZH_SITE", "").strip()
    if env:
        return Path(env).expanduser().resolve()
    return DEFAULT_SITE


def _file_sha256(path: Path) -> str | None:
    if not path.is_file():
        return None
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _read_text(path: Path) -> str | None:
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None


def _classify_hint(patch_id: str) -> str:
    if patch_id.startswith(("042", "045", "046", "047", "033", "ocr-base", "throughput")):
        return "D"
    if patch_id.startswith(("050", "060")) and "term" not in patch_id:
        return "B"
    if "term" in patch_id:
        return "A+B"
    return "A"


def scan_tree_for_marker(site: Path, marker: str, hint: str) -> tuple[bool, str | None]:
    if hint:
        candidate = site / hint
        text = _read_text(candidate)
        if text is not None and marker in text:
            return True, str(candidate)
        if text is not None:
            return False, str(candidate)
    # Fallback: scan a small allowlist of likely files
    allow = [
        site / "pdf2zh_next" / "gui.py",
        site / "babeldoc" / "format" / "pdf" / "document_il" / "backend" / "pdf_creater.py",
        site
        / "babeldoc"
        / "format"
        / "pdf"
        / "document_il"
        / "midend"
        / "il_translator_llm_only.py",
    ]
    for path in allow:
        text = _read_text(path)
        if text and marker in text:
            return True, str(path)
    return False, str(allow[0]) if allow[0].exists() else None


def collect_findings(site: Path) -> list[PatchFinding]:
    findings: list[PatchFinding] = []
    for patch_id, script, marker, hint in KNOWN_PATCHES:
        present, target = scan_tree_for_marker(site, marker, hint)
        findings.append(
            PatchFinding(
                patch_id=patch_id,
                apply_script=script,
                marker=marker,
                present=present,
                target=target,
                classify_hint=_classify_hint(patch_id),
            )
        )
    return findings


def build_report(site: Path) -> dict:
    findings = collect_findings(site)
    gui = site / "pdf2zh_next" / "gui.py"
    present = [f for f in findings if f.present]
    missing = [f for f in findings if not f.present]
    payload = {
        "schema": "plan071-patch-fingerprint/v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "site_packages": str(site),
        "site_exists": site.is_dir(),
        "gui_path": str(gui) if gui.exists() else None,
        "gui_sha256": _file_sha256(gui),
        "apply_script_count": len(list(SCRIPTS.glob("apply-pdf2zh-*.py"))),
        "known_patch_count": len(findings),
        "present_count": len(present),
        "missing_count": len(missing),
        "patches": [asdict(f) for f in findings],
        "fingerprint_sha256": None,
    }
    # Stable hash over present markers only (order by patch_id)
    material = "\n".join(
        f"{f.patch_id}:{f.marker}:{f.present}" for f in sorted(findings, key=lambda x: x.patch_id)
    )
    payload["fingerprint_sha256"] = hashlib.sha256(material.encode("utf-8")).hexdigest()
    return payload


def markers_from_apply_scripts() -> dict[str, list[str]]:
    """Helper for tests: parse MARKER = '...' from apply scripts."""
    out: dict[str, list[str]] = {}
    pat = re.compile(
        r"^(?:[A-Z0-9_]*MARKER[A-Z0-9_]*)\s*=\s*[\"']([^\"']+)[\"']",
        re.M,
    )
    for path in sorted(SCRIPTS.glob("apply-pdf2zh-*.py")):
        text = path.read_text(encoding="utf-8", errors="replace")
        found = pat.findall(text)
        if found:
            out[path.name] = found
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "-o",
        "--out",
        type=Path,
        help="Write JSON report to this path (directories created)",
    )
    parser.add_argument(
        "--site",
        type=str,
        default=None,
        help="site-packages root (default: uv tools pdf2zh-next or QYUNSLATION_PDF2ZH_SITE)",
    )
    parser.add_argument(
        "--fail-if-missing-site",
        action="store_true",
        help="Exit 2 when site-packages directory is absent",
    )
    args = parser.parse_args(argv)
    site = resolve_site(args.site)
    report = build_report(site)
    text = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(text, encoding="utf-8")
        print(f"wrote {args.out}")
    else:
        sys.stdout.write(text)
    if args.fail_if_missing_site and not site.is_dir():
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
