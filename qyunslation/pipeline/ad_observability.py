"""PLAN-076i: lightweight AD rollout metrics and audit hooks."""
from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_LOGGER = logging.getLogger("qyunslation.ad")


def _audit_root() -> Path:
    return Path(os.environ.get("QYUNSLATION_AD_AUDIT_ROOT") or "var/ad-audit")


def record_ad_event(event: str, **fields: Any) -> None:
    payload = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "event": event,
        **fields,
    }
    _LOGGER.info("ad_event %s", json.dumps(payload, ensure_ascii=False, sort_keys=True))
    try:
        root = _audit_root()
        root.mkdir(parents=True, exist_ok=True)
        day = datetime.now(timezone.utc).strftime("%Y%m%d")
        with (root / f"ad-events-{day}.jsonl").open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, ensure_ascii=False) + "\n")
    except OSError:
        pass


def record_rollout_mode_change(*, previous: str, current: str, actor: str = "env") -> None:
    record_ad_event("rollout_mode_change", previous=previous, current=current, actor=actor)


def current_rollout_mode() -> str:
    from qyunslation.pipeline.ad_runtime import ad_rollout_mode

    return ad_rollout_mode(
        env=os.environ.get("QYUNSLATION_ENV"),
        configured=os.environ.get("QYUNSLATION_AD_PROMPT_MODE") or os.environ.get("QYUNSLATION_AD_ROLLOUT"),
    )


def record_rollout_mode_if_changed() -> str | None:
    """Persist the effective rollout mode at startup and audit transitions.

    Mode is configured by environment, so the only place a switch can be
    observed is process start; the last seen mode lives next to the audit log.
    """
    current = current_rollout_mode()
    tenants = sorted(
        item.strip().casefold()
        for item in (os.environ.get("QYUNSLATION_AD_PROMPT_TENANTS") or "").replace(";", ",").split(",")
        if item.strip()
    )
    state_path = _audit_root() / "rollout-mode.json"
    previous: dict[str, Any] = {}
    try:
        previous = json.loads(state_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        previous = {}
    if previous.get("mode") == current and previous.get("tenants") == tenants:
        return None
    record_ad_event(
        "rollout_mode_change",
        previous=str(previous.get("mode") or "unknown"),
        current=current,
        previous_tenants=previous.get("tenants") or [],
        tenants=tenants,
        actor="env",
    )
    try:
        state_path.parent.mkdir(parents=True, exist_ok=True)
        state_path.write_text(json.dumps({"mode": current, "tenants": tenants}, ensure_ascii=False) + "\n", encoding="utf-8")
    except OSError:
        pass
    return current
