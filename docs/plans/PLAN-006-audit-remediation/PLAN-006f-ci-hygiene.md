# PLAN-006f：CI / 测试 / 卫生

- `.github/workflows/pytest.yml`
- `tests/test_app.py`；`scripts/verify-plan-006.sh`
- 归档 `enhanced_translate.py` → `archive/legacy/`
- 删除孤儿 `translation_cache.json`；统一 glossary 至 `extensions/glossary_db.json`
