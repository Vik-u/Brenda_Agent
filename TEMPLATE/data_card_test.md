# ===============================
# 1. IDENTIFICATION & PROVENANCE (REQUIRED)
# ===============================

db_name: "REQUIRED"
short_name: "REQUIRED"
domain: "REQUIRED"   # e.g., Kinetics / Sequence / Pathway / Structure
version: "REQUIRED"
download_date: "REQUIRED"
source_url: "REQUIRED"
source_path: "REQUIRED"     # exact FTP/HTTP path
checksum_sha256: "REQUIRED"
license: "REQUIRED"         # e.g., CC-BY-4.0
parsing_difficulty: "low / medium / high"

schema_version: "1.0.0"
schema_last_updated: "YYYY-MM-DD"
backward_compatible: true

# ===============================
# 2. BIOLOGICAL CONTEXT (REQUIRED)
# ===============================

organism_specificity: "Single-organism / Multi-organism"
primary_entities: ["REQUIRED"]
secondary_entities: ["OPTIONAL"]

intended_use:
  - "REQUIRED: What questions this DB can answer"

not_suitable_for:
  - "REQUIRED: What this DB should NOT be used for"

# ===============================
# 3. INTEROPERABILITY / JOIN KEYS (REQUIRED)
# ===============================

join_keys:
  - local: "REQUIRED"
    maps_to: ["EC", "UniProt", "CHEBI", "Rhea"]
    join_confidence: "high / medium / low"

cross_db_equivalents:
  - local: "id_field"
    target: "other_db.field"
    relation: "exact / approximate"

warnings:
  - "Known mapping issues, deprecated IDs, taxonomy problems..."

# ===============================
# 4. CONTENT FLAGS & UNIT RULES (REQUIRED)
# ===============================

has_sequences: true/false
has_structures: true/false
has_kinetics: true/false
has_taxonomy: true/false
has_pathways: true/false

unit_fields:
  - field: "unit"
    typical_values: ["mM", "uM", "1/s"]
    normalization_required: true
    critical_note: "Unit inconsistencies are common."

# ===============================
# 5. LOCAL NORMALIZATION DONE (OPTIONAL BUT IMPORTANT)
# ===============================

local_processing:
  renamed_columns: true/false
  standardized_units: "none / partial / complete"
  mapped_taxonomy: true/false
  dropped_invalid_rows: number
  additional_notes:
    - "Any transformations performed..."

# ===============================
# 6. SNAPSHOT STATS (REQUIRED)
# ===============================

stats_snapshot:
  estimated_rows: REQUIRED
  missing_unit_fraction: number
  missing_taxid_fraction: number
  duplicate_fraction: number
  sparsity_notes:
    - "Short narrative on sparsity"
    - "Which fields are dense vs sparse"

# ===============================
# 7. FAILURE PATTERNS WITH EXAMPLES (REQUIRED)
# ===============================

failure_patterns:
  - issue: "Unit mismatch"
    example: "Km=0.5 with unit='uM' but source context says mM"
  - issue: "Deprecated EC numbers"
    example: "1.1.1.37 encountered"
  - issue: "Organism string ambiguity"
    example: "'Bacillus sp.' → TaxID unresolved"

# ===============================
# 8. AI USAGE GUIDANCE (OPTIONAL BUT VERY USEFUL)
# ===============================

best_queries:
  - "What people should use this DB for"

avoid_queries:
  - "What people should NOT ask this DB"

embedding_strategy:
  chunk_unit: "row / reaction / kinetic_entry"
  must_include_fields: ["id_fields", "critical_numeric_fields"]
  avoid_fields: ["long free-text comments"]

failure_modes:
  - "Never assume unit consistency"
  - "Never assume EC mapping is complete"

# ===============================
# 9. PROHIBITED USES (REQUIRED)
# ===============================

prohibited_use:
  - "Do not infer missing values"
  - "Do not use raw free text for deterministic reasoning"

# ===============================
# 10. DATA TYPE GUARANTEES (OPTIONAL)
# ===============================

data_type_guarantees:
  - "unit is always a string"
  - "value is always numeric"
  - "id fields are always string-like"

# ===============================
# 11. DATA CHANGELOG (REQUIRED FOR TEAM)
# ===============================

changelog:
  - date: "YYYY-MM-DD"
    schema_version: "1.0.0"
    changes:
      - "Description of updates"

# ===============================
# 12. HEALTH CHECKS (REQUIRED)
# ===============================

health_check:
  file_openable: true
  row_count_ok: true
  unit_field_clean: false
  taxonomy_mapped: true

# ===============================
# 13. QUERY EXAMPLES (OPTIONAL)
# ===============================

query_examples:
  python_pandas: |
    df[df['ec_number']=="1.1.1.1"]

  sql_duckdb: |
    SELECT * FROM kinetics WHERE parameter_type='Km';

# ===============================
# 14. CITATIONS (REQUIRED)
# ===============================

primary_reference: "Author et al., Year, DOI"
additional_refs: []

## HUMAN SUMMARY (REQUIRED)
Short paragraph explaining what this DB is, what it’s for, and its limitations.
