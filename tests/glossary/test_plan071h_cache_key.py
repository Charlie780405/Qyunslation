# SPDX-License-Identifier: MPL-2.0
from qyunslation.workbench.term_align import suggestion_cache_key


def test_prompt_version_changes_cache_key():
    a = suggestion_cache_key("EGFR", "ctx", prompt_version="v1")
    b = suggestion_cache_key("EGFR", "ctx", prompt_version="v2")
    assert a != b


def test_same_tuple_stable():
    a = suggestion_cache_key(
        "EGFR",
        "ctx",
        direction="en-zh",
        model_version="m1",
        prompt_version="p1",
        termbase_version="t1",
    )
    b = suggestion_cache_key(
        "EGFR",
        "ctx",
        direction="en-zh",
        model_version="m1",
        prompt_version="p1",
        termbase_version="t1",
    )
    assert a == b
