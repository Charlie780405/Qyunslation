# PLAN-030 structure fixtures

Synthetic binary fixtures are generated into a temporary directory and are not
committed. Run:

```bash
.venv/bin/python tests/fixtures/structure/generate_synthetic.py --output /tmp/plan030-fixtures
```

`catalog.v1.json` pins each generated artifact by SHA-256 and maps it to a source
format, content profile, expected semantic objects, and the child plan that will
turn the fixture into a green end-to-end test.

## ljae439 knowledge-base slot

`reference/ljae439.pdf` is a development copy imported from the managed knowledge
base. `ljae439.truth.json` pins its full SHA-256 and the semantic truth required by
PLAN-030: Figure 1–5 and Table 1–3 in the main article. PLAN-030b verifies the
real bytes and ten canonical page canvases; semantic Figure/Table reconciliation
remains owned by PLAN-030c.

The knowledge base is a development-fixture source only. Production ingestion
remains user upload of arbitrary supported documents; no scanner, translator,
router, or deployment may depend on the fixture knowledge base.
