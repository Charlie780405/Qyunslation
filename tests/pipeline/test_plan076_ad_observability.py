from __future__ import annotations

import json

from qyunslation.pipeline import ad_observability


def test_rollout_mode_change_is_audited_once_per_transition(monkeypatch, tmp_path):
    monkeypatch.setenv("QYUNSLATION_AD_AUDIT_ROOT", str(tmp_path))
    monkeypatch.setenv("QYUNSLATION_ENV", "production")
    monkeypatch.setenv("QYUNSLATION_AD_PROMPT_MODE", "pilot")
    monkeypatch.setenv("QYUNSLATION_AD_PROMPT_TENANTS", "pilot")
    assert ad_observability.record_rollout_mode_if_changed() == "pilot"
    assert ad_observability.record_rollout_mode_if_changed() is None
    monkeypatch.setenv("QYUNSLATION_AD_PROMPT_MODE", "off")
    assert ad_observability.record_rollout_mode_if_changed() == "off"
    events = [json.loads(line) for path in tmp_path.glob("ad-events-*.jsonl") for line in path.read_text().splitlines()]
    assert [e["event"] for e in events] == ["rollout_mode_change", "rollout_mode_change"]
    assert events[-1]["previous"] == "pilot" and events[-1]["current"] == "off"
    assert json.loads((tmp_path / "rollout-mode.json").read_text())["mode"] == "off"
