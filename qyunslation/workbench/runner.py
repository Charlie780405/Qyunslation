# SPDX-License-Identifier: MPL-2.0
"""PLAN-066e: isolated PDF translation runner.

The Vue workbench must not depend on Gradio's in-memory task registry.  This
module is the small process boundary used by the web API while the existing
``TranslationService`` remains the compatibility adapter for Office and image
workflows.  State is deliberately boring: a 0600 JSON file is atomically
replaced after every validated progress or lifecycle update, and outputs are
discovered only below the run's private directory.
"""
from __future__ import annotations

import asyncio
import json
import os
import re
import shutil
import signal
import sys
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

NON_TERMINAL = frozenset({"queued", "scanning", "translating", "rendering"})
TERMINAL = frozenset({"succeeded", "failed", "cancelled", "degraded"})
# PLAN-071b：CLI/执行器完成但尚未 QA/批准（仅 QYUNSLATION_PIPELINE=v2）
EXECUTOR_DONE = frozenset({"layout_complete"})
# User cancel must still apply after CLI finishes (layout_complete) so the web
# ledger can abandon QA/review without being refreshed back to "translating".
CANCEL_TERMINAL = TERMINAL
_SAFE_COMPONENT = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$")
_PROGRESS_RE = re.compile(r"\bProgress:\s*(?P<value>0(?:\.\d+)?|1(?:\.0+)?)\s*,\s*(?P<label>.*)$")
_PERCENT_RE = re.compile(r"\b(?P<value>\d{1,3}(?:\.\d+)?)%\b")
# Rich MofNCompleteColumn: "Translate Paragraphs (1/1) ━━━ 150/300 0:03:12 0:01:00"
# Totals may be truncated to "…" under narrow terminals; no trailing \\b (ellipsis is non-word).
_RICH_LINE_RE = re.compile(
    r"^(?P<label>.+?)\s+(?:━|─|\[|=){2,}\s*(?P<cur>\d+)\s*/\s*(?P<total>\d+|…|\.\.\.)(?:\s|$)",
    re.UNICODE,
)
# Overall babeldoc bar is named "translate" with total=100 (= overall_progress).
_RICH_OVERALL_RE = re.compile(
    r"^translate\s+(?:━|─|\[|=){2,}\s*(?P<cur>\d+)\s*/\s*(?P<total>\d+|…|\.\.\.)(?:\s|$)",
    re.IGNORECASE | re.UNICODE,
)
# Stage weights for synthesizing a total when only a stage bar is available (PLAN-082 S3).
_STAGE_PROGRESS_BANDS: tuple[tuple[tuple[str, ...], int, int], ...] = (
    (("parse pdf", "detectscannedfile", "parse page", "parse paragraphs", "parse formulas", "parse"), 0, 15),
    (("translate paragraphs", "translate"), 15, 75),
    (("typesetting", "add fonts", "generate drawing", "subset font", "render"), 75, 95),
    (("save pdf", "export"), 95, 99),
)
_LIVE_PROGRESS_LABELS: tuple[tuple[str, str], ...] = (
    ("translate paragraphs", "正在翻译段落"),
    ("parse pdf and create intermediate representation", "正在解析 PDF 结构"),
    ("detectscannedfile", "正在检测扫描件"),
    ("parse page layout", "正在分析页面版式"),
    ("parse paragraphs", "正在提取段落"),
    ("parse formulas and styles", "正在解析公式与样式"),
    ("typesetting", "正在处理版式"),
    ("add fonts", "正在嵌入字体"),
    ("generate drawing instructions", "正在生成绘图指令"),
    ("subset font", "正在优化字体"),
    ("save pdf", "正在保存 PDF"),
    ("export", "正在导出结果"),
    ("parse", "正在解析文档"),
    ("translate", "正在翻译正文"),
    ("render", "正在渲染文档"),
)


class RunnerError(RuntimeError):
    """Base error raised before a process can be safely launched."""


class RunnerUnavailable(RunnerError):
    """The configured CLI or input is not available on this host."""


@dataclass(frozen=True)
class RunnerLaunch:
    task_id: str
    state_path: Path
    output_dir: Path


@dataclass
class _ManagedProcess:
    process: asyncio.subprocess.Process
    log_handle: Any
    state_path: Path
    task_id: str
    pty_master: int | None = None
    tee_task: asyncio.Task | None = None


async def _tee_pty_to_log(master_fd: int, log_handle: Any) -> None:
    """Copy PTY output into runner.log, turning CR updates into discrete lines."""
    loop = asyncio.get_running_loop()

    def _read() -> bytes:
        try:
            return os.read(master_fd, 8192)
        except OSError:
            return b""

    try:
        while True:
            chunk = await loop.run_in_executor(None, _read)
            if not chunk:
                break
            # Rich redraws with \\r; make each redraw a parseable log line.
            normalized = chunk.replace(b"\r\n", b"\n").replace(b"\r", b"\n")
            try:
                log_handle.write(normalized)
                log_handle.flush()
            except OSError:
                break
    finally:
        try:
            os.close(master_fd)
        except OSError:
            pass


async def _spawn_cli_process(
    command: list[str],
    *,
    cwd: str,
    log_handle: Any,
    env: dict[str, str],
) -> tuple[asyncio.subprocess.Process, int | None, asyncio.Task | None]:
    """Start the CLI, preferring a PTY so Rich emits live progress (PLAN-082 S3)."""
    if _runner_use_pty():
        try:
            import pty

            master_fd, slave_fd = pty.openpty()
            try:
                process = await asyncio.create_subprocess_exec(
                    *command,
                    cwd=cwd,
                    stdin=slave_fd,
                    stdout=slave_fd,
                    stderr=slave_fd,
                    env=env,
                    start_new_session=True,
                )
            except Exception:
                os.close(master_fd)
                os.close(slave_fd)
                raise
            os.close(slave_fd)
            # Tee owns master_fd and closes it when the child exits.
            tee_task = asyncio.create_task(_tee_pty_to_log(master_fd, log_handle))
            return process, None, tee_task
        except Exception:
            pass
    process = await asyncio.create_subprocess_exec(
        *command,
        cwd=cwd,
        stdout=log_handle,
        stderr=asyncio.subprocess.STDOUT,
        env=env,
        start_new_session=True,
    )
    return process, None, None


def _utc_now() -> str:
    return datetime.now(UTC).isoformat()


def _safe_component(value: str, label: str) -> str:
    value = str(value)
    if not _SAFE_COMPONENT.fullmatch(value):
        raise RunnerError(f"invalid {label}")
    return value


def _root_from_env() -> Path:
    raw = (os.environ.get("QYUNSLATION_RUNNER_ROOT") or "var/translation-runs").strip()
    root = Path(raw)
    return (root if root.is_absolute() else Path.cwd() / root).resolve()


def _cli_executable() -> str | None:
    configured = (os.environ.get("QYUNSLATION_PDF2ZH_CLI") or "pdf2zh_next").strip()
    if not configured:
        return None
    path = Path(configured)
    if path.is_absolute():
        return str(path) if path.is_file() and os.access(path, os.X_OK) else None
    return shutil.which(configured)


def _config_file() -> Path | None:
    configured = (
        os.environ.get("QYUNSLATION_PDF2ZH_CONFIG")
        or "/home/dev/pdf2zh/config.toml"
    ).strip()
    if not configured:
        return None
    path = Path(configured).expanduser().resolve()
    return path if path.is_file() else None


def _runner_env() -> dict[str, str]:
    """Give the isolated CLI the repository package roots it imports at render time."""
    env = os.environ.copy()
    roots = [Path(__file__).resolve().parents[3], Path(__file__).resolve().parents[2]]
    current = [item for item in (env.get("PYTHONPATH") or "").split(os.pathsep) if item]
    merged: list[str] = []
    for item in [*(str(root) for root in roots), *current]:
        if item not in merged:
            merged.append(item)
    env["PYTHONPATH"] = os.pathsep.join(merged)
    # Wide columns so Rich MofN totals are not truncated to "…"; xterm so Rich
    # treats a PTY slave as an interactive terminal and emits live updates.
    env.setdefault("COLUMNS", "200")
    env.setdefault("TERM", "xterm-256color")
    env.setdefault("NO_COLOR", "1")
    env["PYTHONUNBUFFERED"] = "1"
    return env


def _runner_use_pty() -> bool:
    raw = (os.environ.get("QYUNSLATION_RUNNER_PTY") or "1").strip().casefold()
    return raw not in {"0", "false", "off", "no"}


def _pdf_needs_hpd(path: Path) -> bool:
    """Use the existing HPD detector without making OCR part of preflight."""
    try:
        if "/home/dev/pdf2zh" not in sys.path:
            sys.path.insert(0, "/home/dev/pdf2zh")
        from hpd_ocr import pdf_needs_hpd

        return bool(pdf_needs_hpd(path))
    except Exception:
        # The CLI remains the primary path.  If the optional HPD service or
        # its dependencies are unavailable, let the normal runner report the
        # original failure instead of failing task creation synchronously.
        return False


def _ocr_pdf_with_hpd(source: Path, destination: Path) -> Path:
    """Materialize a searchable PDF through the existing HPD OCR bridge."""
    if "/home/dev/pdf2zh" not in sys.path:
        sys.path.insert(0, "/home/dev/pdf2zh")
    from hpd_ocr import ocr_pdf_with_hpd

    return Path(ocr_pdf_with_hpd(source, destination))


def _prepare_runtime_config(
    base: Path | None, run_dir: Path, settings: dict[str, Any] | None = None
) -> Path | None:
    """Copy the operator config and force CLI mode without mutating it.

    The production GUI config intentionally contains ``[basic] gui = true``.
    Passing that file directly to the CLI would make ``pdf2zh_next`` start a
    second Gradio server and report a false success.  A private 0600 copy keeps
    provider settings available while making the execution mode explicit.
    """
    if base is None:
        return None
    try:
        content = base.read_text(encoding="utf-8")
    except OSError as exc:
        raise RunnerUnavailable("pdf2zh config is unreadable") from exc
    replaced, count = re.subn(
        r"(?m)^(\s*gui\s*=\s*)(?:true|false)\s*$",
        r"\1false",
        content,
        count=1,
    )
    if count == 0:
        # No [basic].gui key means the upstream default is already CLI mode.
        replaced = content
    try:
        from qyunslation.workbench.runtime_config import apply_model_snapshot

        snapshot = (settings or {}).get("model_snapshot")
        if isinstance(snapshot, dict):
            replaced = apply_model_snapshot(replaced, snapshot)
    except Exception:
        pass
    ad_prompt = str((settings or {}).get("ad_prompt_text") or "").strip()
    if ad_prompt:
        # The compiled prompt is kept in the private per-run config.  It is
        # never placed on argv or in the public run response where it could
        # become an accidental prompt-editing API.
        encoded = json.dumps(ad_prompt, ensure_ascii=False)
        translation_block = re.search(r"(?ms)^\[translation\]\s*\n(.*?)(?=^\[|\Z)", replaced)
        if translation_block:
            block = translation_block.group(0)
            prompt_line = re.compile(r"(?m)^\s*custom_system_prompt\s*=.*$")
            if prompt_line.search(block):
                block = prompt_line.sub(f"custom_system_prompt = {encoded}", block, count=1)
            else:
                block = block.rstrip() + f"\ncustom_system_prompt = {encoded}\n"
            replaced = replaced.replace(translation_block.group(0), block)
    target = run_dir / "runner-config.toml"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(replaced, encoding="utf-8")
    os.chmod(target, 0o600)
    return target


def _language_codes(direction: str) -> tuple[str, str]:
    if direction == "English → 简体中文":
        return "en", "zh"
    if direction == "简体中文 → English":
        return "zh", "en"
    raise RunnerError("unsupported language direction")


def build_pdf2zh_command(
    *,
    executable: str,
    input_path: Path,
    output_dir: Path,
    direction: str,
    settings: dict[str, Any] | None = None,
    config_file: Path | None = None,
) -> list[str]:
    """Build argv for the documented non-GUI ``pdf2zh_next`` CLI.

    Secrets are intentionally not accepted here.  Provider credentials remain
    in the protected config/environment used by the runner process rather than
    being copied into a command line or a state file.
    """
    source_lang, target_lang = _language_codes(direction)
    options = settings or {}
    command = [str(executable)]
    if config_file is not None:
        command.extend(["--config-file", str(config_file)])
    command.extend(
        [
            "--report-interval",
            "1",
            "--lang-in",
            source_lang,
            "--lang-out",
            target_lang,
            "--output",
            str(output_dir),
            "--watermark-output-mode",
            "no_watermark",
        ]
    )
    pages = options.get("pages")
    if isinstance(pages, str) and pages.strip() and re.fullmatch(r"[0-9,\- ]+", pages):
        command.extend(["--pages", pages.strip()])
    glossary = options.get("glossaries") or os.environ.get("QYUNSLATION_PDF2ZH_GLOSSARIES")
    if isinstance(glossary, str) and glossary.strip():
        command.extend(["--glossaries", glossary.strip()])
    if options.get("scan_strategy") == "skip-detection":
        command.append("--skip-scanned-detection")
    elif options.get("auto_ocr_workaround", True) is True:
        # Scanned-heavy PDFs otherwise exit 0 after reporting a BabelDOC
        # translation error, leaving the output directory empty and making
        # the durable run appear as a QA/artefact-gate failure.  Let the CLI
        # decide when OCR is actually needed; text PDFs keep the normal path.
        command.append("--auto-enable-ocr-workaround")
    if options.get("ocr_workaround") is True:
        command.append("--ocr-workaround")
    if options.get("disable_rich_text_translate") is True:
        command.append("--disable-rich-text-translate")
    # The workbench's "source/translation pair" option; absent means the CLI default
    # (both outputs), so legacy snapshots keep their behaviour.
    if options.get("bilingual") is False:
        command.append("--no-dual")
    command.append(str(input_path))
    return command


def _atomic_write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    encoded = json.dumps(data, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    with temporary.open("w", encoding="utf-8") as handle:
        os.chmod(temporary, 0o600)
        handle.write(encoded)
        handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temporary, path)
    os.chmod(path, 0o600)


def _read_json(path: Path) -> dict[str, Any] | None:
    try:
        if path.stat().st_size > 1024 * 1024:
            return None
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        return None
    return value if isinstance(value, dict) else None


def _process_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except (OSError, ProcessLookupError):
        return False
    return True


def _runner_process_matches(pid: int) -> bool:
    """Avoid attaching to a recycled PID during startup reconcile."""
    try:
        argv = Path(f"/proc/{pid}/cmdline").read_bytes().split(b"\x00")
    except OSError:
        return False
    expected = Path(_cli_executable() or "pdf2zh_next").name.encode("utf-8")
    return any(expected in item for item in argv if item)


def _stage_for_label(label: str) -> str:
    lowered = label.casefold()
    if any(token in lowered for token in ("parse page layout", "parse paragraphs", "parse formulas")):
        return "structure"
    if "save pdf" in lowered or "export" in lowered:
        return "export"
    if "detectscannedfile" in lowered:
        return "structure"
    if any(token in lowered for token in ("scan", "ocr", "parse", "structure", "layout analysis")):
        return "structure"
    if any(token in lowered for token in ("render", "typeset", "layout", "export")):
        return "rendering"
    if any(token in lowered for token in ("table", "figure", "image")):
        return "table_figure"
    if any(token in lowered for token in ("qa", "quality", "term")):
        return "qa"
    return "translating"


def _progress_message_from_line(line: str) -> str | None:
    """Map trusted CLI progress labels to concise user-facing Chinese text.

    Rich redraws its progress bars as terminal lines such as ``Translate
    Paragraphs (1/1)``.  Those lines do not always contain a reliable global
    percentage, so we expose the current operation separately and let the UI
    render an indeterminate bar instead of inventing a percentage.
    """
    lowered = " ".join(str(line).casefold().split())
    progress_match = _PROGRESS_RE.search(line)
    if progress_match:
        lowered = progress_match.group("label").casefold().strip()
    # Skip the overall Rich bar named "translate" — it is not a stage label.
    if re.match(r"^translate\s*(?:━|─|\[|=)", lowered):
        return None
    for label, message in _LIVE_PROGRESS_LABELS:
        if label in lowered:
            return message
    if "scanned pdf detected" in lowered or "ocr" in lowered:
        return "正在准备 OCR 文字层"
    return None


def _stage_band_progress(label: str, cur: int, total: int | None) -> int | None:
    """Map a Rich stage bar into the weighted overall band (capped at 99)."""
    lowered = " ".join(label.casefold().split())
    for keys, start, end in _STAGE_PROGRESS_BANDS:
        if any(key in lowered for key in keys):
            if total and total > 0:
                ratio = max(0.0, min(1.0, cur / total))
                return min(99, start + round((end - start) * ratio))
            return start
    return None


def _parse_rich_progress(line: str) -> tuple[int | None, str | None]:
    """Parse Rich progress bars written under a PTY (PLAN-082 S3)."""
    text = " ".join(str(line).replace("\x00", " ").split())
    if not text:
        return None, None
    overall = _RICH_OVERALL_RE.match(text)
    if overall:
        cur = int(overall.group("cur"))
        total_raw = overall.group("total")
        if total_raw.isdigit():
            total = int(total_raw)
            if total > 0:
                return min(99, max(0, round(100 * cur / total))), "translating"
        # total truncated to "…" — babeldoc's overall bar is out of 100
        return min(99, max(0, cur)), "translating"
    rich = _RICH_LINE_RE.match(text)
    if rich:
        label = rich.group("label").strip()
        if label.casefold() == "translate":
            return None, None
        cur = int(rich.group("cur"))
        total_raw = rich.group("total")
        total = int(total_raw) if total_raw.isdigit() else None
        value = _stage_band_progress(label, cur, total)
        return value, _stage_for_label(label)
    return None, None


def _parse_progress(line: str) -> tuple[int | None, str | None]:
    match = _PROGRESS_RE.search(line)
    if match:
        value = max(0.0, min(1.0, float(match.group("value"))))
        # Cap below 100 until the process exits so the UI does not look finished.
        return min(99, round(value * 100)) if value < 1.0 else 99, _stage_for_label(match.group("label"))
    rich_progress, rich_stage = _parse_rich_progress(line)
    if rich_progress is not None or rich_stage is not None:
        return rich_progress, rich_stage
    match = _PERCENT_RE.search(line)
    if match:
        value = max(0.0, min(100.0, float(match.group("value"))))
        return min(99, round(value)), None
    return None, None


def _monotonic_progress(previous: Any, current: int | None) -> int | None:
    if current is None:
        return int(previous) if isinstance(previous, (int, float)) else None
    if isinstance(previous, (int, float)):
        return max(int(previous), int(current))
    return int(current)


# BabelDOC 日志进度只占 0–89%，90–99% 留给 CLI 之后的表格重排等后处理，
# 否则进度会停在 99% 数分钟不动。
_BABEL_PROGRESS_SHARE = 0.9
POSTPROCESS_PROGRESS_START = 90
POSTPROCESS_PROGRESS_END = 99


def _scale_babel_progress(value: int | None) -> int | None:
    if value is None:
        return None
    return min(POSTPROCESS_PROGRESS_START - 1, round(float(value) * _BABEL_PROGRESS_SHARE))


def _safe_reason(value: str, fallback: str) -> str:
    clean = " ".join(str(value).replace("\x00", " ").split())
    return (clean[:512] or fallback)[:512]


def _pipeline_mode() -> str:
    raw = (os.environ.get("QYUNSLATION_PIPELINE") or "legacy").strip().casefold()
    return "v2" if raw in {"v2", "pipeline", "document"} else "legacy"


def _cli_success_updates(
    outputs: list[dict[str, Any]],
    *,
    progress_message: str | None,
    pipeline: str | None = None,
) -> dict[str, Any]:
    """Finalize CLI success. v2 must not claim formal export/succeeded."""
    mode = _pipeline_mode() if not pipeline else ("v2" if pipeline == "v2" else "legacy")
    if mode == "v2":
        return {
            "status": "layout_complete",
            "stage": "layout",
            "progress": None,
            "outputs": outputs,
            "reason": None,
            "cli_complete": True,
            "progress_message": progress_message or "CLI 已完成，等待版式质检与审核",
            "finished_at": _utc_now(),
        }
    return {
        "status": "succeeded",
        "stage": "export",
        "progress": 100,
        "outputs": outputs,
        "reason": None,
        "cli_complete": True,
        "progress_message": progress_message or "翻译完成",
        "finished_at": _utc_now(),
    }


class Pdf2zhRunner:
    """Own PDF CLI processes and their durable state files."""

    def __init__(self, root: Path | None = None):
        self.root = (root or _root_from_env()).resolve()
        self._processes: dict[str, _ManagedProcess] = {}
        self._watchers: dict[str, asyncio.Task[Any]] = {}

    def _run_dir(self, *, tenant_id: str, run_id: str, generation: int) -> Path:
        tenant = _safe_component(tenant_id, "tenant id")
        run = _safe_component(run_id, "run id")
        if generation < 1:
            raise RunnerError("invalid generation")
        return self.root / tenant / run / f"generation-{generation}"

    def _task_id(self, run_id: str, generation: int) -> str:
        _safe_component(run_id, "run id")
        if generation < 1:
            raise RunnerError("invalid generation")
        return f"pdf2zh:{run_id}:{generation}"

    def _state_path_for_task(
        self, task_id: str, *, tenant_id: str | None = None
    ) -> Path | None:
        if not task_id.startswith("pdf2zh:"):
            return None
        parts = task_id.split(":")
        if len(parts) != 3:
            return None
        _, run_id, generation_raw = parts
        try:
            generation = int(generation_raw)
        except ValueError:
            return None
        if tenant_id:
            candidate = self._run_dir(
                tenant_id=tenant_id, run_id=run_id, generation=generation
            ) / "state.json"
            return candidate if candidate.is_file() else None
        matches = list(
            self.root.glob(f"*/{run_id}/generation-{generation}/state.json")
        )
        return matches[0] if len(matches) == 1 else None

    def read_task_state(self, task_id: str) -> dict[str, Any] | None:
        path = self._state_path_for_task(task_id)
        if path is None:
            return None
        state = _read_json(path)
        if not state:
            return None
        return self._api_task_state(state, path.parent)

    def _write_state(self, path: Path, state: dict[str, Any], **updates: Any) -> dict[str, Any]:
        state = dict(state)
        state.update(updates)
        state["updated_at"] = _utc_now()
        _atomic_write_json(path, state)
        return state

    def _api_task_state(self, state: dict[str, Any], run_dir: Path) -> dict[str, Any]:
        status = str(state.get("status") or "degraded")
        outputs: dict[str, dict[str, Any]] = {}
        for index, item in enumerate(state.get("outputs") or []):
            if not isinstance(item, dict):
                continue
            raw_path = Path(str(item.get("path") or "")).resolve()
            try:
                raw_path.relative_to(run_dir.resolve())
            except ValueError:
                continue
            if not raw_path.is_file():
                continue
            file_type = str(item.get("file_type") or raw_path.suffix.lstrip(".") or f"file-{index}")[:64]
            if file_type in outputs:
                file_type = f"{file_type}-{index}"[:64]
            outputs[file_type] = {
                "path": str(raw_path),
                "filename": Path(str(item.get("filename") or raw_path.name)).name[:256],
            }
        return {
            "status": status,
            "stage": state.get("stage") or "validation",
            "progress_percent": state.get("progress"),
            "download_ready": status == "succeeded" and bool(outputs),
            "is_processing": status in NON_TERMINAL,
            "error_flag": status in {"failed", "degraded"},
            "cli_complete": bool(state.get("cli_complete")) or status in EXECUTOR_DONE,
            "status_message": state.get("reason") or status,
            "progress_message": state.get("progress_message"),
            "downloadable_files": outputs,
            "attachment_files": {},
            "runner_state_path": str(run_dir / "state.json"),
        }

    async def start(
        self,
        *,
        tenant_id: str,
        run_id: str,
        generation: int,
        input_path: Path,
        direction: str,
        original_filename: str,
        settings: dict[str, Any] | None = None,
    ) -> RunnerLaunch:
        executable = _cli_executable()
        source = input_path.resolve()
        if executable is None:
            raise RunnerUnavailable("pdf2zh_next CLI is not installed")
        if source.suffix.casefold() != ".pdf" or not source.is_file():
            raise RunnerUnavailable("PDF input is unavailable")
        task_id = self._task_id(run_id, generation)
        run_dir = self._run_dir(tenant_id=tenant_id, run_id=run_id, generation=generation)
        state_path = run_dir / "state.json"
        lock_path = run_dir / "run.lock"
        run_dir.mkdir(parents=True, exist_ok=True)
        try:
            fd = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
            os.close(fd)
        except FileExistsError as exc:
            existing = _read_json(state_path)
            if existing and existing.get("status") in NON_TERMINAL:
                raise RunnerError("translation generation is already running") from exc
            raise RunnerError("translation generation lock is not available") from exc

        output_dir = run_dir / "output"
        output_dir.mkdir(parents=True, exist_ok=True)
        try:
            runtime_config = _prepare_runtime_config(_config_file(), run_dir, settings)
            command = build_pdf2zh_command(
                executable=executable,
                input_path=source,
                output_dir=output_dir,
                direction=direction,
                settings=settings,
                config_file=runtime_config,
            )
        except Exception:
            lock_path.unlink(missing_ok=True)
            raise
        resume_done = set((settings or {}).get("resume_completed_stages") or [])
        state: dict[str, Any] = {
            "schema": "qyunslation.runner.v1",
            "task_id": task_id,
            "tenant_id": tenant_id,
            "run_id": run_id,
            "generation": generation,
            "status": "queued",
            "stage": "validation",
            "progress": None,
            "progress_message": "正在准备翻译",
            "pid": None,
            "command": [str(item) for item in command if not str(item).startswith("--")],
            "source_filename": Path(original_filename).name[:256],
            "pipeline": (settings or {}).get("pipeline") or _pipeline_mode(),
            "outputs": [],
            "reason": None,
            "created_at": _utc_now(),
            "started_at": None,
            "finished_at": None,
            "updated_at": _utc_now(),
        }
        _atomic_write_json(state_path, state)
        self._persist_runner_stages(state, resume_done)
        log_path = run_dir / "runner.log"
        log_handle = log_path.open("ab", buffering=0)
        os.chmod(log_path, 0o600)
        try:
            process, pty_master, tee_task = await _spawn_cli_process(
                command,
                cwd=str(run_dir),
                log_handle=log_handle,
                env=_runner_env(),
            )
        except Exception:
            log_handle.close()
            lock_path.unlink(missing_ok=True)
            state["status"] = "failed"
            state["reason"] = "could not start pdf2zh_next"
            state["finished_at"] = _utc_now()
            _atomic_write_json(state_path, state)
            raise
        state = self._write_state(
            state_path,
            state,
            status="scanning",
            pid=process.pid,
            started_at=_utc_now(),
        )
        managed = _ManagedProcess(
            process=process,
            log_handle=log_handle,
            state_path=state_path,
            task_id=task_id,
            pty_master=pty_master,
            tee_task=tee_task,
        )
        self._processes[task_id] = managed
        self._watchers[task_id] = asyncio.create_task(
            self._monitor(
                managed,
                state,
                run_dir,
                source=source,
                direction=direction,
                settings=dict(settings or {}),
                executable=executable,
                config_file=runtime_config,
            )
        )
        return RunnerLaunch(task_id=task_id, state_path=state_path, output_dir=output_dir)

    async def _retry_scanned_pdf_with_hpd(
        self,
        managed: _ManagedProcess,
        state: dict[str, Any],
        run_dir: Path,
        *,
        source: Path,
        direction: str,
        settings: dict[str, Any],
        executable: str,
        config_file: Path | None,
    ) -> tuple[bool, dict[str, Any], str | None]:
        """Retry an empty CLI result through the existing searchable-PDF path."""
        if settings.get("auto_ocr_workaround", True) is not True or not _pdf_needs_hpd(source):
            return False, state, None

        state = self._write_state(
            managed.state_path,
            state,
            status="scanning",
            stage="structure",
            progress=None,
            reason="PDF 扫描件未生成产物，正在补充 OCR 文字层",
            progress_message="正在补充 OCR 文字层",
        )
        ocr_source = run_dir / "input.hpd-ocr.pdf"
        try:
            await asyncio.to_thread(_ocr_pdf_with_hpd, source, ocr_source)
            if not ocr_source.is_file() or _pdf_needs_hpd(ocr_source):
                raise RunnerError("HPD OCR produced no searchable text layer")
        except Exception as exc:
            return False, state, f"scanned PDF OCR preprocessing failed: {_safe_reason(exc, 'unknown error')}"

        latest = _read_json(managed.state_path) or state
        if latest.get("status") == "cancelled":
            return False, latest, "translation cancelled by user"

        output_dir = run_dir / "output"
        for child in output_dir.iterdir():
            if child.is_dir():
                shutil.rmtree(child)
            else:
                child.unlink(missing_ok=True)
        retry_settings = dict(settings)
        retry_settings.update(
            {
                "auto_ocr_workaround": False,
                "scan_strategy": "skip-detection",
                "ocr_workaround": True,
                "disable_rich_text_translate": True,
            }
        )
        retry_command = build_pdf2zh_command(
            executable=executable,
            input_path=ocr_source,
            output_dir=output_dir,
            direction=direction,
            settings=retry_settings,
            config_file=config_file,
        )
        try:
            process, pty_master, tee_task = await _spawn_cli_process(
                retry_command,
                cwd=str(run_dir),
                log_handle=managed.log_handle,
                env=_runner_env(),
            )
        except Exception as exc:
            return False, state, f"scanned PDF retry could not start: {_safe_reason(exc, 'unknown error')}"
        managed.process = process
        managed.pty_master = pty_master
        managed.tee_task = tee_task
        state = self._write_state(
            managed.state_path,
            state,
            status="scanning",
            stage="structure",
            progress=None,
            pid=process.pid,
            command=[str(item) for item in retry_command if not str(item).startswith("--")],
            reason="已生成 OCR 文字层，正在重新翻译",
            progress_message="已生成 OCR 文字层，正在重新翻译",
        )
        return True, state, None

    @staticmethod
    def _mark_db_interrupted(state: dict[str, Any]) -> None:
        run_id = str(state.get("run_id") or "")
        generation = int(state.get("generation") or 0)
        if not run_id or generation < 1:
            return
        try:
            from qyunslation.persist.db import get_engine
            from qyunslation.persist.models import TranslationRunRecord
            from qyunslation.workbench.heartbeat import mark_interrupted
            from sqlalchemy.orm import Session

            with Session(get_engine()) as session:
                run = session.get(TranslationRunRecord, run_id)
                if run is not None and int(run.generation) == generation:
                    mark_interrupted(
                        session,
                        run,
                        reason="runner process was not found after service restart",
                    )
                    session.commit()
        except Exception:
            pass

    @staticmethod
    def _persist_runner_stages(state: dict[str, Any], completed: set[str]) -> None:
        run_id = str(state.get("run_id") or "")
        generation = int(state.get("generation") or 0)
        if not run_id or generation < 1:
            return
        try:
            from qyunslation.persist.db import get_engine
            from qyunslation.workbench.stage_persist import persist_stage_snapshot
            from sqlalchemy.orm import Session

            with Session(get_engine()) as session:
                for stage in ("validation", "structure"):
                    if stage in completed:
                        persist_stage_snapshot(
                            session,
                            run_id=run_id,
                            generation=generation,
                            stage=stage,
                            state="skipped",
                            message="resume: stage already completed",
                        )
                session.commit()
        except Exception:
            pass

    @staticmethod
    def _touch_run_heartbeat(state: dict[str, Any]) -> None:
        run_id = str(state.get("run_id") or "")
        generation = int(state.get("generation") or 0)
        if not run_id or generation < 1:
            return
        try:
            from qyunslation.persist.db import get_engine
            from qyunslation.persist.models import TranslationRunRecord
            from qyunslation.workbench.heartbeat import touch_run_heartbeat
            from sqlalchemy.orm import Session

            with Session(get_engine()) as session:
                run = session.get(TranslationRunRecord, run_id)
                if run is not None and int(run.generation) == generation:
                    touch_run_heartbeat(session, run)
                    session.commit()
        except Exception:
            pass

    @staticmethod
    def _persist_runner_progress(
        state: dict[str, Any], *, stage: str | None, message: str | None
    ) -> None:
        run_id = str(state.get("run_id") or "")
        generation = int(state.get("generation") or 0)
        if not run_id or generation < 1 or not stage:
            return
        marker = f"{stage}:{message or ''}"
        if state.get("_last_stage_persist") == marker:
            return
        state["_last_stage_persist"] = marker
        try:
            from qyunslation.persist.db import get_engine
            from qyunslation.workbench.stage_persist import persist_stage_snapshot
            from sqlalchemy.orm import Session

            progress = state.get("progress")
            with Session(get_engine()) as session:
                persist_stage_snapshot(
                    session,
                    run_id=run_id,
                    generation=generation,
                    stage=stage,
                    state="running",
                    message=message or "",
                    progress=float(progress) if isinstance(progress, (int, float)) else None,
                )
                session.commit()
        except Exception:
            pass

    async def _monitor(
        self,
        managed: _ManagedProcess,
        state: dict[str, Any],
        run_dir: Path,
        *,
        source: Path,
        direction: str,
        settings: dict[str, Any],
        executable: str,
        config_file: Path | None,
    ) -> None:
        state_path = managed.state_path
        log_path = run_dir / "runner.log"
        attempted_hpd = False
        heartbeat_tick = 0
        try:
            while True:
                offset = log_path.stat().st_size if log_path.exists() else 0
                last_reason = ""
                while managed.process.returncode is None:
                    await asyncio.sleep(0.5)
                    heartbeat_tick += 1
                    if heartbeat_tick % 10 == 0:
                        self._touch_run_heartbeat(state)
                    try:
                        with log_path.open("rb") as handle:
                            handle.seek(offset)
                            chunk = handle.read()
                            offset = handle.tell()
                    except OSError:
                        chunk = b""
                    if not chunk:
                        continue
                    for raw_line in chunk.decode("utf-8", errors="replace").splitlines():
                        line = raw_line.strip()
                        if not line:
                            continue
                        last_reason = _safe_reason(line, last_reason)
                        progress, stage = _parse_progress(line)
                        progress_message = _progress_message_from_line(line)
                        if progress_message and stage is None:
                            stage = _stage_for_label(line)
                        if progress is not None or stage is not None or progress_message:
                            next_stage = stage or state.get("stage") or "translating"
                            next_progress = _monotonic_progress(state.get("progress"), _scale_babel_progress(progress))
                            detail = {
                                "stage": next_stage,
                                "message": progress_message or state.get("progress_message"),
                            }
                            state = self._write_state(
                                state_path,
                                state,
                                status="rendering" if stage in {"rendering", "export"} else "translating",
                                progress=next_progress,
                                stage=next_stage,
                                progress_message=progress_message or state.get("progress_message"),
                                progress_detail=detail,
                            )
                            self._persist_runner_progress(
                                state,
                                stage=str(next_stage),
                                message=progress_message or last_reason,
                            )
                returncode = await managed.process.wait()
                if managed.tee_task is not None:
                    try:
                        await asyncio.wait_for(managed.tee_task, timeout=2.0)
                    except (asyncio.TimeoutError, asyncio.CancelledError, OSError):
                        managed.tee_task.cancel()
                    managed.tee_task = None
                # Cancellation is written by the API task while this watcher
                # is waiting for the process group to exit; reload the atomic
                # state so a clean SIGTERM cannot be overwritten.
                latest = _read_json(state_path) or state
                if latest.get("status") == "cancelled":
                    return
                outputs = self._discover_outputs(run_dir / "output")
                if returncode == 0 and outputs:
                    # PLAN-080d：译文产物就绪后、记录前，让下划线跟随译文（默认关闭，失败不影响交付）。
                    babel_message = state.get("progress_message")
                    state = self._report_postprocess(state_path, state, 90, "正在对齐装饰线")
                    await asyncio.to_thread(self._realign_decorations, source, run_dir / "output")
                    # PLAN-082 S4：补上空白字形 CID→空格的 ToUnicode（默认开启，失败不影响交付）。
                    state = self._report_postprocess(state_path, state, 91, "正在修复文字映射")
                    await asyncio.to_thread(self._fix_space_cmaps, run_dir / "output")
                    # PLAN-082 S5：文献表后处理（默认 literature；失败不影响交付）。
                    state = self._report_postprocess(state_path, state, 92, "正在重排表格译文")
                    holder = {"state": state}

                    def _on_table(pct: int, message: str, _h=holder) -> None:
                        _h["state"] = self._report_postprocess(state_path, _h["state"], pct, message)

                    await asyncio.to_thread(
                        self._postprocess_tables, source, run_dir / "output", _on_table
                    )
                    # 后处理的临时文案不带进终态；完成态沿用 BabelDOC 的最后一条。
                    state = {**holder["state"], "progress_message": babel_message}
                    self._write_state(
                        state_path,
                        state,
                        **_cli_success_updates(
                            outputs,
                            progress_message=state.get("progress_message"),
                            pipeline=state.get("pipeline"),
                        ),
                    )
                    break
                if not outputs and not attempted_hpd:
                    attempted_hpd = True
                    started, state, retry_reason = await self._retry_scanned_pdf_with_hpd(
                        managed,
                        state,
                        run_dir,
                        source=source,
                        direction=direction,
                        settings=settings,
                        executable=executable,
                        config_file=config_file,
                    )
                    if started:
                        continue
                    if retry_reason:
                        last_reason = retry_reason
                self._write_state(
                    state_path,
                    state,
                    status="failed",
                    stage="qa",
                    progress=state.get("progress"),
                    progress_message=state.get("progress_message") or "翻译失败",
                    reason=last_reason or (
                        "pdf2zh_next completed without output artifacts"
                        if returncode == 0
                        else f"pdf2zh_next exited with code {returncode}"
                    ),
                    finished_at=_utc_now(),
                )
                break
        finally:
            managed.log_handle.close()
            self._processes.pop(managed.task_id, None)
            self._watchers.pop(managed.task_id, None)
            (run_dir / "runner-config.toml").unlink(missing_ok=True)
            (run_dir / "run.lock").unlink(missing_ok=True)

    @staticmethod
    def _realign_decorations(source: Path, output_dir: Path) -> dict[str, Any] | None:
        """PLAN-080d：对输出目录里的 PDF（mono 与 dual）做装饰线随文。

        开关 ``QYUNSLATION_DECORATION_REALIGN``（默认 off）。任何异常都吞掉，保留原产物：
        这一步的失败模式必须是"线条不够漂亮"，不能是"交付失败"。返回各文件的统计，关闭时为 None。
        """
        try:
            from qyunslation.structure.decoration_realign import realign_mode, realign_pdf

            if realign_mode() != "on" or not source.is_file() or not output_dir.is_dir():
                return None
            summary: dict[str, Any] = {}
            for pdf in sorted(output_dir.glob("*.pdf")):
                try:
                    summary[pdf.name] = realign_pdf(source, pdf).as_dict()
                except Exception as exc:  # noqa: BLE001
                    summary[pdf.name] = {"error": type(exc).__name__}
            return summary
        except Exception:  # noqa: BLE001
            return None

    @staticmethod
    def _fix_space_cmaps(output_dir: Path) -> dict[str, Any] | None:
        """PLAN-082 S4: map blank CID 3 → U+0020 in ToUnicode (default on, fail-open)."""
        try:
            from qyunslation.structure.pdf_space_cmap import fix_space_cmap_tree

            return fix_space_cmap_tree(output_dir)
        except Exception:  # noqa: BLE001
            return None

    def _report_postprocess(
        self, state_path: Path, state: dict[str, Any], percent: int, message: str
    ) -> dict[str, Any]:
        """后处理阶段的进度汇报：只增不减，写入原子状态并落库，失败不影响交付。"""
        try:
            pct = max(POSTPROCESS_PROGRESS_START, min(POSTPROCESS_PROGRESS_END, int(percent)))
            nxt = _monotonic_progress(state.get("progress"), pct)
            state = self._write_state(
                state_path,
                state,
                status="rendering",
                progress=nxt,
                stage="table_figure",
                progress_message=message,
                progress_detail={"stage": "table_figure", "message": message},
            )
            self._persist_runner_progress(state, stage="table_figure", message=message)
        except Exception:  # noqa: BLE001
            pass
        return state

    @staticmethod
    def _postprocess_tables(
        source: Path, output_dir: Path, on_progress=None
    ) -> dict[str, Any] | None:
        """PLAN-082 S5: table normalize/translate after CLI (fail-open)."""
        try:
            from qyunslation.pipeline.events import StageEventBuffer
            from qyunslation.pipeline.stages.postprocess import run_table_figure_stage, table_postprocess_mode

            if table_postprocess_mode() == "off" or not output_dir.is_dir():
                return None
            mono = next(iter(sorted(output_dir.glob("*.zh.mono.pdf"))), None)
            if mono is None:
                mono = next(iter(sorted(output_dir.glob("*mono*.pdf"))), None)
            dual = next(iter(sorted(output_dir.glob("*.zh.dual.pdf"))), None)
            events = StageEventBuffer()
            result = run_table_figure_stage(
                mono_pdf=mono,
                dual_pdf=dual,
                events=events,
                enabled=True,
                origin_pdf=source if source.is_file() else None,
                on_progress=on_progress,
            )
            return {
                "state": result.state,
                "message": result.message,
                "outputs": result.outputs,
                "warnings": result.warnings,
            }
        except Exception as exc:  # noqa: BLE001
            return {"error": type(exc).__name__}

    @staticmethod
    def _discover_outputs(output_dir: Path) -> list[dict[str, Any]]:
        outputs: list[dict[str, Any]] = []
        if not output_dir.is_dir():
            return outputs
        for path in sorted(output_dir.rglob("*")):
            if not path.is_file() or path.name.startswith("."):
                continue
            try:
                path.relative_to(output_dir)
            except ValueError:
                continue
            outputs.append(
                {
                    "path": str(path.resolve()),
                    "filename": path.name[:256],
                    "file_type": path.suffix.lstrip(".")[:64] or "file",
                }
            )
        return outputs

    async def prepare_resume(
        self,
        *,
        tenant_id: str,
        run_id: str,
        generation: int,
    ) -> None:
        """Stop a stale generation and release its lock so resume can relaunch."""
        run_dir = self._run_dir(tenant_id=tenant_id, run_id=run_id, generation=generation)
        state_path = run_dir / "state.json"
        lock_path = run_dir / "run.lock"
        state = _read_json(state_path)
        if not state and not lock_path.is_file():
            return
        task_id = self._task_id(run_id, generation)
        managed = self._processes.pop(task_id, None)
        watcher = self._watchers.pop(task_id, None)
        if watcher is not None:
            watcher.cancel()
        if managed is not None:
            pid = int(managed.process.pid or 0)
            if pid > 0 and _process_alive(pid):
                try:
                    os.killpg(pid, signal.SIGTERM)
                except ProcessLookupError:
                    pass
                deadline = time.monotonic() + 5
                while _process_alive(pid) and time.monotonic() < deadline:
                    await asyncio.sleep(0.1)
                if _process_alive(pid):
                    try:
                        os.killpg(pid, signal.SIGKILL)
                    except ProcessLookupError:
                        pass
            try:
                managed.log_handle.close()
            except Exception:
                pass
        elif state:
            pid = int(state.get("pid") or 0)
            if pid > 0 and _process_alive(pid):
                try:
                    os.killpg(pid, signal.SIGTERM)
                except ProcessLookupError:
                    pass
        if state and state.get("status") in NON_TERMINAL:
            self._write_state(
                state_path,
                state,
                status="interrupted",
                reason="preparing generation resume",
                finished_at=_utc_now(),
            )
        lock_path.unlink(missing_ok=True)
        (run_dir / "runner-config.toml").unlink(missing_ok=True)

    async def cancel(self, task_id: str) -> dict[str, Any]:
        state_path = self._state_path_for_task(task_id)
        if state_path is None:
            raise RunnerError("translation runner task not found")
        state = _read_json(state_path)
        if not state:
            raise RunnerError("translation runner state is unreadable")
        if state.get("status") in CANCEL_TERMINAL:
            return {"cancelled": False, "already_terminal": True}
        if state.get("status") in EXECUTOR_DONE:
            self._write_state(
                state_path,
                state,
                status="cancelled",
                stage="qa",
                reason="translation cancelled by user",
                finished_at=_utc_now(),
            )
            return {"cancelled": True}
        pid = int(state.get("pid") or 0)
        managed = self._processes.get(task_id)
        if managed is not None:
            pid = int(managed.process.pid or pid)
        if pid > 0 and _process_alive(pid):
            try:
                os.killpg(pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
            deadline = time.monotonic() + 10
            while _process_alive(pid) and time.monotonic() < deadline:
                await asyncio.sleep(0.1)
            if _process_alive(pid):
                try:
                    os.killpg(pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
        self._write_state(
            state_path,
            state,
            status="cancelled",
            stage="qa",
            reason="translation cancelled by user",
            finished_at=_utc_now(),
        )
        return {"cancelled": True}

    async def reconcile(self) -> int:
        """Reconcile orphaned generations without launching duplicate work."""
        if not self.root.is_dir():
            return 0
        reconciled = 0
        for path in self.root.glob("*/*/generation-*/state.json"):
            state = _read_json(path)
            if not state or state.get("status") not in NON_TERMINAL:
                continue
            task_id = str(state.get("task_id") or "")
            pid = int(state.get("pid") or 0)
            if task_id in self._watchers:
                continue
            run_dir = path.parent
            if pid and _process_alive(pid) and _runner_process_matches(pid):
                reconciled += 1
                self._watchers[task_id] = asyncio.create_task(
                    self._monitor_orphan(task_id, path, state, run_dir, pid)
                )
                continue
            self._write_state(
                path,
                state,
                status="degraded",
                stage=state.get("stage") or "text",
                progress=state.get("progress"),
                reason="runner process was not found after service restart",
                finished_at=_utc_now(),
            )
            (run_dir / "runner-config.toml").unlink(missing_ok=True)
            (run_dir / "run.lock").unlink(missing_ok=True)
            self._mark_db_interrupted(state)
            reconciled += 1
        return reconciled

    async def _monitor_orphan(
        self, task_id: str, state_path: Path, state: dict[str, Any], run_dir: Path, pid: int
    ) -> None:
        try:
            while _process_alive(pid):
                await asyncio.sleep(1)
            outputs = self._discover_outputs(run_dir / "output")
            if outputs:
                self._write_state(
                    state_path,
                    state,
                    **_cli_success_updates(
                        outputs,
                        progress_message=state.get("progress_message"),
                        pipeline=state.get("pipeline"),
                    ),
                )
            else:
                self._write_state(
                    state_path,
                    state,
                    status="degraded",
                    stage="qa",
                    reason="runner process exited after service restart without outputs",
                    finished_at=_utc_now(),
                )
        finally:
            self._watchers.pop(task_id, None)
            (run_dir / "runner-config.toml").unlink(missing_ok=True)
            (run_dir / "run.lock").unlink(missing_ok=True)


_DEFAULT_RUNNER: Pdf2zhRunner | None = None


def get_pdf2zh_runner() -> Pdf2zhRunner:
    global _DEFAULT_RUNNER
    root = _root_from_env()
    if _DEFAULT_RUNNER is None or _DEFAULT_RUNNER.root != root:
        _DEFAULT_RUNNER = Pdf2zhRunner(root)
    return _DEFAULT_RUNNER


def get_pdf2zh_task_state(task_id: str) -> dict[str, Any] | None:
    return get_pdf2zh_runner().read_task_state(task_id)


def is_pdf2zh_task(task_id: str | None) -> bool:
    return bool(task_id and task_id.startswith("pdf2zh:"))


async def cancel_pdf2zh_task(task_id: str) -> dict[str, Any]:
    return await get_pdf2zh_runner().cancel(task_id)


async def reconcile_pdf2zh_runners() -> int:
    return await get_pdf2zh_runner().reconcile()
