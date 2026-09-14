# SPDX-License-Identifier: MPL-2.0
"""PLAN-051a：金标整本执行器（选条目、sha256 缓存、调生产 CLI）。"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any

from qyunslation.gold.plan034 import (
    GoldEntry,
    gold_root,
    load_catalog,
    resolve_entry,
    verify_entry_hash,
)

OUT_ENV = "QYUNSLATION_PLAN051_OUT"
DEFAULT_OUT = Path("/tmp/plan051-out")
PDF2ZH_CLI_ENV = "QYUNSLATION_PDF2ZH_CLI"
OLLAMA_HOST_ENV = "QYUNSLATION_OLLAMA_HOST"
OLLAMA_MODEL_ENV = "QYUNSLATION_OLLAMA_MODEL"
PDF2ZH_CONFIG_ENV = "QYUNSLATION_PDF2ZH_CONFIG"
INCLUDE_SYNTHETIC_ENV = "QYUNSLATION_PLAN051_INCLUDE_SYNTHETIC"

DEFAULT_MODEL = "qwen3.6:35b-a3b"
DEFAULT_OLLAMA_HOST = "http://100.67.66.123:11434"
DEFAULT_CONFIG = Path("/home/dev/pdf2zh/config.toml")

TranslateFn = Callable[[GoldEntry, Path, Path], dict[str, Any]]


class Plan051Blocked(Exception):
    """缺文件 / CLI / 环境 → 应 exit 2。"""


def plan051_out_root(override: Path | str | None = None) -> Path:
    if override is not None:
        return Path(override)
    env = (os.environ.get(OUT_ENV) or "").strip()
    if env:
        return Path(env)
    return DEFAULT_OUT


def is_real(entry: GoldEntry) -> bool:
    return "real" in entry.tags


def is_synthetic(entry: GoldEntry) -> bool:
    return "synthetic" in entry.tags


def select_entries(
    entries: Sequence[GoldEntry] | None = None,
    *,
    include_synthetic: bool | None = None,
    entry_id: str | None = None,
    limit: int | None = None,
) -> list[GoldEntry]:
    items = list(entries) if entries is not None else load_catalog()
    if include_synthetic is None:
        flag = (os.environ.get(INCLUDE_SYNTHETIC_ENV) or "").strip()
        include_synthetic = flag in {"1", "true", "TRUE", "yes", "YES"}
    if entry_id:
        items = [e for e in items if e.id == entry_id]
        if not items:
            raise Plan051Blocked(f"entry not in catalog: {entry_id}")
    selected: list[GoldEntry] = []
    for e in items:
        if e.status != "ready":
            continue
        if is_real(e) or (include_synthetic and is_synthetic(e)):
            selected.append(e)
    # 有 *-ocr 孪生时跳过扫描原件（C-fda-pind → C-fda-pind-ocr）
    if not entry_id:
        selected = drop_scanned_originals(selected)
    if limit is not None:
        selected = selected[: max(0, int(limit))]
    return selected


def drop_scanned_originals(items: Sequence[GoldEntry]) -> list[GoldEntry]:
    ids = {e.id for e in items}
    return [
        e
        for e in items
        if f"{e.id}-ocr" not in ids or "ocr" in e.tags
    ]


def cache_dir(entry: GoldEntry, *, out_root: Path | None = None) -> Path:
    root = plan051_out_root(out_root)
    sha12 = (entry.sha256 or "unknown")[:12]
    return root / entry.id / sha12


def manifest_path(entry: GoldEntry, *, out_root: Path | None = None) -> Path:
    return cache_dir(entry, out_root=out_root) / "run-manifest.json"


def load_run_manifest(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) else None


def is_cache_hit(entry: GoldEntry, *, out_root: Path | None = None) -> bool:
    man = load_run_manifest(manifest_path(entry, out_root=out_root))
    if not man:
        return False
    if str(man.get("source_sha256") or "").lower() != (entry.sha256 or "").lower():
        return False
    mono = Path(str(man.get("mono") or ""))
    return mono.is_file()


def write_run_manifest(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _git_head(repo: Path | None = None) -> str:
    root = repo or Path(__file__).resolve().parents[2]
    try:
        return (
            subprocess.check_output(
                ["git", "-C", str(root), "rev-parse", "--short", "HEAD"],
                stderr=subprocess.DEVNULL,
            )
            .decode()
            .strip()
        )
    except Exception:
        return "unknown"


def resolve_source(entry: GoldEntry, *, root: Path | str | None = None) -> Path:
    path = resolve_entry(entry, root=root)
    if path is None or not path.is_file():
        raise Plan051Blocked(f"{entry.id}: source missing under GOLD_ROOT")
    if not verify_entry_hash(entry, path):
        raise Plan051Blocked(f"{entry.id}: sha256 mismatch for {path}")
    return path


def _pdf2zh_cli() -> str:
    return (os.environ.get(PDF2ZH_CLI_ENV) or "pdf2zh_next").strip() or "pdf2zh_next"


def _which_or_blocked(cli: str) -> str:
    if Path(cli).is_file() and os.access(cli, os.X_OK):
        return cli
    found = shutil.which(cli)
    if found:
        return found
    raise Plan051Blocked(f"CLI not found: {cli}")


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def pdf2zh_subprocess_env(base: dict[str, str] | None = None) -> dict[str, str]:
    """pdf2zh_next 是独立 uv 解释器，必须带上仓库 PYTHONPATH（与 033n / pdf2zh.service 一致）。"""
    env = dict(base if base is not None else os.environ)
    root = str(_repo_root())
    cur = (env.get("PYTHONPATH") or "").strip()
    parts = [p for p in cur.split(os.pathsep) if p]
    if root not in parts:
        env["PYTHONPATH"] = os.pathsep.join([root, *parts]) if parts else root
    return env


def build_tmp_config(
    *,
    out_dir: Path,
    config_src: Path | None = None,
    skip_scanned: bool = False,
) -> Path:
    src = config_src or Path(os.environ.get(PDF2ZH_CONFIG_ENV) or DEFAULT_CONFIG)
    text = src.read_text(encoding="utf-8") if src.is_file() else ""
    lines: list[str] = []
    for line in text.splitlines():
        s = line.strip()
        if s == "gui = true":
            lines.append("gui = false")
        elif line.startswith("output = "):
            lines.append(f'output = "{out_dir}"')
        elif skip_scanned and s.startswith("skip_scanned_detection"):
            lines.append("skip_scanned_detection = true")
        else:
            lines.append(line)
    if not any("gui = false" in x for x in lines):
        lines.append("gui = false")
    if not any(x.startswith("output = ") for x in lines):
        lines.append(f'output = "{out_dir}"')
    if skip_scanned and not any(
        x.strip().startswith("skip_scanned_detection = true") for x in lines
    ):
        lines.append("skip_scanned_detection = true")
    dest = out_dir / "config.toml"
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return dest


def find_mono_dual(out_dir: Path, src: Path) -> tuple[Path | None, Path | None]:
    stem = src.stem
    candidates_mono = list(out_dir.glob(f"{stem}*.mono.pdf")) + list(
        out_dir.glob("*.mono.pdf")
    )
    candidates_dual = list(out_dir.glob(f"{stem}*.dual.pdf")) + list(
        out_dir.glob("*.dual.pdf")
    )
    mono = next((p for p in candidates_mono if p.is_file()), None)
    dual = next((p for p in candidates_dual if p.is_file()), None)
    return mono, dual


def collect_sidecars(out_dir: Path) -> list[str]:
    paths: list[str] = []
    for pattern in ("*.imgtr.json", "*tbltr*", "*execution*", "*.qc.json"):
        for p in out_dir.rglob(pattern):
            if p.is_file():
                paths.append(str(p))
    return sorted(set(paths))


def default_translate(
    entry: GoldEntry,
    src: Path,
    out_dir: Path,
    *,
    model_id: str | None = None,
    ollama_host: str | None = None,
    run_post: bool = True,
) -> dict[str, Any]:
    """调用 pdf2zh_next；可选后处理 imgtr/tbltr。"""
    cli = _which_or_blocked(_pdf2zh_cli())
    model = model_id or (os.environ.get(OLLAMA_MODEL_ENV) or DEFAULT_MODEL)
    host = ollama_host or (os.environ.get(OLLAMA_HOST_ENV) or DEFAULT_OLLAMA_HOST)
    out_dir.mkdir(parents=True, exist_ok=True)
    config = build_tmp_config(
        out_dir=out_dir,
        skip_scanned="ocr" in (entry.tags or ()),
    )
    cmd = [
        cli,
        "--config-file",
        str(config),
        "--disable-config-auto-save",
        "--ollama",
        "--ollama-model",
        model,
        "--ollama-host",
        host,
        "--lang-in",
        "en",
        "--lang-out",
        "zh",
        "--output",
        str(out_dir),
        "--ignore-cache",
        "--no-auto-extract-glossary",
        "--watermark-output-mode",
        "no_watermark",
        str(src),
    ]
    proc = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        check=False,
        env=pdf2zh_subprocess_env(),
    )
    log_path = out_dir / "run.log"
    log_path.write_text(
        (proc.stdout or "") + "\n" + (proc.stderr or ""),
        encoding="utf-8",
    )
    if proc.returncode != 0:
        raise Plan051Blocked(
            f"{entry.id}: pdf2zh_next exit {proc.returncode} (see {log_path})"
        )
    mono, dual = find_mono_dual(out_dir, src)
    if mono is None:
        raise Plan051Blocked(f"{entry.id}: mono.pdf missing under {out_dir}")

    if run_post:
        try:
            _run_postprocess(src, mono, dual, model=model, host=host)
        except Plan051Blocked:
            raise
        except Exception as exc:
            raise Plan051Blocked(f"{entry.id}: post-process failed: {exc}") from exc
        mono, dual = find_mono_dual(out_dir, src) or (mono, dual)
        # 后处理可能原地覆盖；再扫一遍
        mono2, dual2 = find_mono_dual(out_dir, src)
        mono = mono2 or mono
        dual = dual2 or dual

    return {
        "mono": str(mono),
        "dual": str(dual) if dual else "",
        "sidecar": collect_sidecars(out_dir),
        "exit_code": 0,
        "model_id": model,
    }


def _run_postprocess(
    src: Path,
    mono: Path,
    dual: Path | None,
    *,
    model: str,
    host: str,
) -> None:
    """与 033n 同链；scripts 不在包内，按仓库根插入 path。"""
    import sys

    root = Path(__file__).resolve().parents[2]
    scripts = root / "scripts"
    for p in (str(scripts), str(root)):
        if p not in sys.path:
            sys.path.insert(0, p)
    from pdf_image_translate import translate_pdf_images  # type: ignore
    from pdf_table_translate import translate_pdf_tables  # type: ignore
    from qyunslation.structure.model_trace import bind_task_model_trace
    from qyunslation.structure.scan_pdf import PdfStructureScanner

    bind_task_model_trace(model_id=model, endpoint=f"{host.rstrip('/')}/v1")
    manifest = PdfStructureScanner().scan(src)
    translate_pdf_images(mono, to_lang="简体中文", structure_manifest=manifest)
    translate_pdf_tables(
        mono, origin=src, to_lang="简体中文", structure_manifest=manifest
    )
    if dual is not None and dual.is_file():
        translate_pdf_images(dual, to_lang="简体中文", x_min_frac=0.5)
        translate_pdf_tables(
            dual,
            origin=src,
            to_lang="简体中文",
            structure_manifest=manifest,
            x_min_frac=0.5,
        )


def run_one(
    entry: GoldEntry,
    *,
    out_root: Path | None = None,
    gold_root_path: Path | str | None = None,
    translate_fn: TranslateFn | None = None,
    force: bool = False,
    dry_run: bool = False,
) -> dict[str, Any]:
    """跑单条；可注入 translate_fn 供单测。"""
    dest = cache_dir(entry, out_root=out_root)
    if not force and is_cache_hit(entry, out_root=out_root):
        man = load_run_manifest(manifest_path(entry, out_root=out_root)) or {}
        man["cached"] = True
        return man

    src = resolve_source(entry, root=gold_root_path)
    if dry_run:
        return {
            "entry_id": entry.id,
            "source_sha256": entry.sha256,
            "dry_run": True,
            "src": str(src),
            "out_dir": str(dest),
        }

    dest.mkdir(parents=True, exist_ok=True)
    fn = translate_fn or (
        lambda e, s, o: default_translate(e, s, o, run_post=True)
    )
    result = fn(entry, src, dest)
    mono = Path(str(result.get("mono") or ""))
    if not mono.is_file():
        raise Plan051Blocked(f"{entry.id}: translate_fn did not produce mono")

    payload: dict[str, Any] = {
        "entry_id": entry.id,
        "source_sha256": entry.sha256,
        "git_head": _git_head(),
        "model_id": result.get("model_id")
        or (os.environ.get(OLLAMA_MODEL_ENV) or DEFAULT_MODEL),
        "mono": str(mono),
        "dual": str(result.get("dual") or ""),
        "sidecar": list(result.get("sidecar") or []),
        "exit_code": int(result.get("exit_code") or 0),
        "cached": False,
        "class": entry.class_,
        "tags": list(entry.tags),
    }
    write_run_manifest(manifest_path(entry, out_root=out_root), payload)
    return payload


def run_selected(
    *,
    include_synthetic: bool | None = None,
    entry_id: str | None = None,
    limit: int | None = None,
    out_root: Path | None = None,
    gold_root_path: Path | str | None = None,
    translate_fn: TranslateFn | None = None,
    force: bool = False,
    dry_run: bool = False,
) -> list[dict[str, Any]]:
    selected = select_entries(
        include_synthetic=include_synthetic,
        entry_id=entry_id,
        limit=limit,
    )
    if not selected:
        raise Plan051Blocked("no scoring entries selected (need real tags or --include-synthetic)")
    # 预检 GOLD_ROOT
    base = gold_root(gold_root_path)
    if not base.is_dir() and not dry_run:
        raise Plan051Blocked(f"GOLD_ROOT missing: {base}")
    results: list[dict[str, Any]] = []
    for e in selected:
        results.append(
            run_one(
                e,
                out_root=out_root,
                gold_root_path=gold_root_path,
                translate_fn=translate_fn,
                force=force,
                dry_run=dry_run,
            )
        )
    return results
