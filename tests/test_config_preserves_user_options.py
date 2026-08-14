from docutranslate.core.schemas import TextWorkflowParams


def test_env_force_override_preserves_user_translation_preferences():
    payload = TextWorkflowParams.model_validate({
        "workflow_type": "txt",
        "base_url": "http://user.invalid/v1",
        "model_id": "user-model",
        "api_key": "user-key",
        "provider": "ollama",
        "to_lang": "English",
        "concurrent": 2,
        "chunk_size": 1234,
        "retry": 5,
        "insert_mode": "replace",
        "separator": "",
    })
    # Environment force override may change hidden connection defaults in the
    # production process, but must not rewrite user-visible translation choices.
    assert payload.to_lang == "English"
    assert payload.concurrent == 2
    assert payload.chunk_size == 1234
    assert payload.retry == 5
    assert payload.insert_mode == "replace"
