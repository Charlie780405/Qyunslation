# PLAN-030 structure fixtures

Binary fixtures are generated into a temporary directory and are not committed.
Run:

```bash
.venv/bin/python tests/fixtures/structure/generate_synthetic.py --output /tmp/plan030-fixtures
```

`catalog.v1.json` pins each generated artifact by SHA-256 and maps it to a source
format, content profile, expected semantic objects, and the child plan that will
turn the fixture into a green end-to-end test.

## ljae439 knowledge-base slot

`ljae439.truth.json` reserves the semantic truth required by PLAN-030:
Figure 1–5 and Table 1–3 in the main article. The PDF is supplied by the managed
knowledge base rather than committed to this repository. Until it is imported,
the truth remains executable for counting tests and the source SHA-256 is null.
When materialized, set `import_state` to `IMPORTED` and record the full lowercase
SHA-256 before running byte-level scanner acceptance in PLAN-030b.

The knowledge base is a development-fixture source only. Production ingestion
remains user upload of arbitrary supported documents; no scanner, translator,
router, or deployment may depend on the fixture knowledge base.
