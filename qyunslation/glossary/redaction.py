# SPDX-License-Identifier: MPL-2.0
"""PLAN-071h：术语外发前脱敏。"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

_EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
_PHONE = re.compile(r"\b(?:\+?\d{1,3}[-.\s]?)?(?:\(?\d{2,4}\)?[-.\s]?)?\d{3,4}[-.\s]?\d{4}\b")
_ORG = re.compile(
    r"\b(?:[A-Z][A-Za-z0-9&.-]+\s+)?(?:Inc\.|Ltd\.|LLC|Corp\.|Corporation|University|Hospital|Clinic)\b"
    r"|\bAcme(?:\s+Corp\.?)?\b",
    re.I,
)
_PERSONISH = re.compile(
    r"\b(?:Mr\.|Ms\.|Mrs\.|Dr\.|Prof\.)\s+[A-Z][a-z]+(?:\s+[A-Z][a-z]+)?\b"
)
_ID_LIKE = re.compile(r"\b(?:IND|PIND|NCT)\s*[:#]?\s*\d+\b", re.I)


@dataclass
class RedactionReport:
    ok: bool
    replacements: dict[str, int] = field(default_factory=dict)
    reason: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "replacements": dict(self.replacements),
            "reason": self.reason,
        }


def redact_term_context(text: str, *, classification: str = "internal") -> tuple[str, RedactionReport]:
    """Minimize PII/org identifiers before external term suggestions."""
    if not text:
        return text, RedactionReport(ok=True)
    c = (classification or "internal").casefold()
    if c == "public":
        # Still strip emails/phones as hygiene.
        pass
    if c == "confidential":
        return text, RedactionReport(ok=False, reason="confidential_forbids_egress")

    out = text
    counts: dict[str, int] = {}

    def _sub(pattern: re.Pattern[str], label: str, repl: str) -> None:
        nonlocal out
        found = pattern.findall(out)
        if not found:
            return
        counts[label] = counts.get(label, 0) + len(found)
        out = pattern.sub(repl, out)

    _sub(_EMAIL, "email", "[EMAIL]")
    _sub(_PHONE, "phone", "[PHONE]")
    _sub(_PERSONISH, "person", "[NAME]")
    _sub(_ID_LIKE, "study_id", "[ID]")
    _sub(_ORG, "org", "[ORG]")

    # Fail closed if residual email-like tokens remain.
    if _EMAIL.search(out):
        return out, RedactionReport(ok=False, reason="email_residual", replacements=counts)
    return out, RedactionReport(ok=True, replacements=counts)
