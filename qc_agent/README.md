# Documentation QC Agent (design sketch)

Goal: automate generation + validation of data cards and schema docs for raw/processed datasets.

## Components
- **Extractor**: pulls stats from source files (row counts, column types, checksums, missing fractions, duplicate groups) using Python/SQLite/ijson.
- **Template Filler**: renders data card + schema YAML/MD from templates with filled metrics.
- **Validator**: checks required fields present, numeric fields within thresholds, and cross-file consistency (e.g., checksum in data card matches observed).
- **Judge (LLM)**: optional pass using GPT to flag inconsistencies, missing required blocks, and unclear sections.
- **Pipeline Runner**: CLI to run extract → render → validate → report.

## Metrics & thresholds
- Row-count tolerance: processed DB row counts must be >0 and match previously observed order of magnitude; fail if 0.
- Missing unit fraction: warn if >0.8; error if >0.9.
- Duplicate groups (ec/category/value/unit/context): warn if >0.15 of enzyme_facts.
- Required sections: error if any REQUIRED blocks from templates are absent.
- Checksum: must match computed SHA256; error otherwise.

## Iterative loop
1) **Generate** fresh docs from templates with current metrics.
2) **Validate** with rules above and a lint for required keys.
3) **LLM Review** (optional) to summarize risks/ambiguities.
4) **Apply fixes**: adjust text, update metrics, or flag issues.
5) Repeat until all validations pass and LLM review has no high-severity flags.

## Files to produce
- `docs/datacards/<dataset>_data_card.md`
- `docs/datacards/<dataset>_schema.yaml`
- `qc_agent/report.json` containing metrics + pass/fail.

## Minimal CLI outline
```bash
python -m qc_agent.run \
  --raw-json data/raw/brenda_2025_1.json \
  --raw-txt data/raw/brenda_2025_1.txt \
  --db data/processed/brenda.db \
  --output docs/datacards
```

## TODO to implement
- `qc_agent/extract.py`: compute checksums, row counts, missing fractions, duplicate groups.
- `qc_agent/render.py`: fill templates using Jinja2 or simple format dict.
- `qc_agent/validate.py`: enforce thresholds + required keys.
- `qc_agent/run.py`: wire the pipeline and emit JSON report.
- Tests: golden-file comparison for rendered docs; unit tests for validators.
