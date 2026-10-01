# SPDX-License-Identifier: MPL-2.0
from qyunslation.glossary.redaction import redact_term_context


def test_redacts_email_and_ids():
    text = "Contact jane.doe@fda.gov about IND 123456 at Acme Corp."
    out, report = redact_term_context(text, classification="internal")
    assert report.ok
    assert "jane.doe@fda.gov" not in out
    assert "[EMAIL]" in out
    assert "[ID]" in out
    assert "[ORG]" in out


def test_confidential_forbids_egress():
    out, report = redact_term_context("safe context", classification="confidential")
    assert report.ok is False
    assert report.reason == "confidential_forbids_egress"
