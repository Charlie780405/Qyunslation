from __future__ import annotations

from qyunslation.pipeline.ad_prompt import PromptContext, compile_prompt
from qyunslation.pipeline.ad_prompt_store import (
    load_frozen_prompt,
    verify_frozen_digest,
    write_frozen_prompt,
)


def test_frozen_prompt_roundtrip_and_digest_verify(tmp_path):
    compiled = compile_prompt(
        PromptContext("ad", "en-zh", "医学研究文献", "translate")
    )
    snapshot = compiled.snapshot()
    write_frozen_prompt(tmp_path, text=compiled.text, snapshot=snapshot)
    loaded_text, manifest = load_frozen_prompt(tmp_path)
    assert loaded_text == compiled.text
    assert manifest["digest"] == snapshot["digest"]
    assert verify_frozen_digest(tmp_path, snapshot["digest"])
    assert not verify_frozen_digest(tmp_path, "sha256:deadbeef")
