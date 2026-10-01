# SPDX-License-Identifier: MPL-2.0
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SETTINGS = ROOT / "frontend/src/next/pages/SettingsPage.vue"
ROUTER = ROOT / "frontend/src/next/router.js"


def test_settings_section_url_and_single_render():
    text = SETTINGS.read_text(encoding="utf-8")
    assert "route.query.section" in text
    assert "v-else-if=\"activeSection === 'accessibility'\"" in text
    assert "qy-reduce-motion" in text


def test_admin_route_requires_policy():
    text = ROUTER.read_text(encoding="utf-8")
    assert "requiresPolicy" in text
    assert "can_manage_policy" in text
