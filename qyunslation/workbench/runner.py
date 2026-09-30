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
_SAFE_COMPONENT = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$")
_PROGRESS_RE = re.compile(r"\bProgress:\s*(?P<value>0(?:\.\d+)?|1(?:\.0+)?)\s*,\s*(?P<label>.*)$")
_PERCENT_RE = re.compile(r"\b(?P<value>\d{1,3}(?:\.\d+)?)%\b")


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
    return env


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


def _prepare_runtime_config(base: Path | None, run_dir: Path) -> Path | None:
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
    target = run_dir / "runner-config.toml"
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
    if any(token in lowered for token in ("scan", "ocr", "parse", "structure", "layout analysis")):
        return "structure"
    if any(token in lowered for token in ("render", "typeset", "layout", "export")):
        return "rendering"
    if any(token in lowered for token in ("table", "figure", "image")):
        return "table_figure"
    if any(token in lowered for token in ("qa", "quality", "term")):
        return "qa"
    return "translating"


def _parse_progress(line: str) -> tuple[int | None, str | None]:
    match = _PROGRESS_RE.search(line)
    if match:
        value = max(0.0, min(1.0, float(match.group("value"))))
        return round(value * 100), _stage_for_label(match.group("label"))
    match = _PERCENT_RE.search(line)
    if match:
        value = max(0.0, min(100.0, float(match.group("value"))))
        return round(value), None
    return None, None


def _safe_reason(value: str, fallback: str) -> str:
    clean = " ".join(str(value).replace("\x00", " ").split())
    return (clean[:512] or fallback)[:512]


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

    def _state_path_for_task(self, task_id: str) -> Path | None:
        if not task_id.startswith("pdf2zh:"):
            return None
        matches = []
        for path in self.root.glob("*/*/generation-*/state.json"):
            state = _read_json(path)
            if state and state.get("task_id") == task_id:
                matches.append(path)
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
            "status_message": state.get("reason") or status,
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
            runtime_config = _prepare_runtime_config(_config_file(), run_dir)
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
        state: dict[str, Any] = {
            "schema": "qyunslation.runner.v1",
            "task_id": task_id,
            "run_id": run_id,
            "generation": generation,
            "status": "queued",
            "stage": "validation",
            "progress": None,
            "pid": None,
            "command": [str(item) for item in command if not str(item).startswith("--")],
            "source_filename": Path(original_filename).name[:256],
            "outputs": [],
            "reason": None,
            "created_at": _utc_now(),
            "started_at": None,
            "finished_at": None,
            "updated_at": _utc_now(),
        }
        _atomic_write_json(state_path, state)
        log_path = run_dir / "runner.log"
        log_handle = log_path.open("ab", buffering=0)
        os.chmod(log_path, 0o600)
        try:
            process = await asyncio.create_subprocess_exec(
                *command,
                cwd=str(run_dir),
                stdout=log_handle,
                stderr=asyncio.subprocess.STDOUT,
                env=_runner_env(),
                start_new_session=True,
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
        managed = _ManagedProcess(process=process, log_handle=log_handle, state_path=state_path, task_id=task_id)
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
            process = await asyncio.create_subprocess_exec(
                *retry_command,
                cwd=str(run_dir),
                stdout=managed.log_handle,
                stderr=asyncio.subprocess.STDOUT,
                env=_runner_env(),
                start_new_session=True,
            )
        except Exception as exc:
            return False, state, f"scanned PDF retry could not start: {_safe_reason(exc, 'unknown error')}"
        managed.process = process
        state = self._write_state(
            managed.state_path,
            state,
            status="scanning",
            stage="structure",
            progress=None,
            pid=process.pid,
            command=[str(item) for item in retry_command if not str(item).startswith("--")],
            reason="已生成 OCR 文字层，正在重新翻译",
        )
        return True, state, None

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
        try:
            while True:
                offset = log_path.stat().st_size if log_path.exists() else 0
                last_reason = ""
                while managed.process.returncode is None:
                    await asyncio.sleep(0.5)
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
                        if progress is not None or stage is not None:
                            state = self._write_state(
                                state_path,
                                state,
                                status="rendering" if stage == "rendering" else "translating",
                                progress=progress if progress is not None else state.get("progress"),
                                stage=stage or state.get("stage") or "translating",
                            )
                returncode = await managed.process.wait()
                # Cancellation is written by the API task while this watcher
                # is waiting for the process group to exit; reload the atomic
                # state so a clean SIGTERM cannot be overwritten.
                latest = _read_json(state_path) or state
                if latest.get("status") == "cancelled":
                    return
                outputs = self._discover_outputs(run_dir / "output")
                if returncode == 0 and outputs:
                    self._write_state(
                        state_path,
                        state,
                        status="succeeded",
                        stage="export",
                        progress=100,
                        outputs=outputs,
                        reason=None,
                        finished_at=_utc_now(),
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

    async def cancel(self, task_id: str) -> dict[str, Any]:
        state_path = self._state_path_for_task(task_id)
        if state_path is None:
            raise RunnerError("translation runner task not found")
        state = _read_json(state_path)
        if not state:
            raise RunnerError("translation runner state is unreadable")
        if state.get("status") in TERMINAL:
            return {"cancelled": False, "already_terminal": True}
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
                stage="qa",
                progress=state.get("progress"),
                reason="runner process was not found after service restart",
                finished_at=_utc_now(),
            )
            (run_dir / "runner-config.toml").unlink(missing_ok=True)
            (run_dir / "run.lock").unlink(missing_ok=True)
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
                    status="succeeded",
                    stage="export",
                    progress=100,
                    outputs=outputs,
                    finished_at=_utc_now(),
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
