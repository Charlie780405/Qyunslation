"""PLAN-076i: lightweight AD rollout metrics and audit hooks."""
from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_LOGGER = logging.getLogger("qyunslation.ad")
_AUDIT_ROOT = Path(os.environ.get("QYUNSLATION_AD_AUDIT_ROOT") or "var/ad-audit")


def record_ad_event(event: str, **fields: Any) -> None:
    payload = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "event": event,
        **fields,
    }
    _LOGGER.info("ad_event %s", json.dumps(payload, ensure_ascii=False, sort_keys=True))
    try:
        _AUDIT_ROOT.mkdir(parents=True, exist_ok=True)
        day = datetime.now(timezone.utc).strftime("%Y%m%d")
        with (_AUDIT_ROOT / f"ad-events-{day}.jsonl").open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, ensure_ascii=False) + "\n")
    except OSError:
        pass


def record_rollout_mode_change(*, previous: str, current: str, actor: str = "env") -> None:
    record_ad_event("rollout_mode_change", previous=previous, current=current, actor=actor)
