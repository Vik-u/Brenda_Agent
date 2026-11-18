# ===============================
# 1. IDENTIFICATION & PROVENANCE (REQUIRED)
# ===============================

db_name: "BRENDA Enzyme Database (release 2025_1) – raw JSON/TXT snapshot"
short_name: "brenda_raw_2025_1"
domain: "Kinetics / Enzyme annotations / Text curation"
version: "2025_1"
download_date: "2025-12-18"               # file mtime on disk
source_url: "https://www.brenda-enzymes.org/downloads"
source_path: "data/raw/brenda_2025_1.json (JSON), data/raw/brenda_2025_1.txt (TXT)"
checksum_sha256: "JSON a08268e5f4ae326b041b7b7b6c79a39363ef5080b0b65d81a02e9741ccbffd16; TXT d50efd71302267011556cb97d29af81ed84d0dc085fed9af22ffa759e769a0e0"
license: "Restricted / academic license (BRENDA)"
parsing_difficulty: "high"

schema_version: "1.0.0"
schema_last_updated: "2025-12-18"
backward_compatible: true

# ===============================
# 2. BIOLOGICAL CONTEXT (REQUIRED)
# ===============================

organism_specificity: "Multi-organism"
primary_entities: ["Enzyme (EC entry)"]
secondary_entities: ["Protein annotations", "Kinetic facts", "Text facts/references"]

intended_use:
  - "Retrieve curated enzyme kinetics, inhibitors/activators, substrates/products, and descriptive text directly from the raw BRENDA dump."
  - "Serve as a ground-truth source for building local mirrors or downstream parsing/analysis."

not_suitable_for:
  - "Up-to-date literature mining (limited to the release snapshot)."
  - "Sequence/structure analysis (no sequences; structures are sparse/absent)."
  - "Deterministic units or taxonomy without additional normalization."

# ===============================
# 3. INTEROPERABILITY / JOIN KEYS (REQUIRED)
# ===============================

join_keys:
  - local: "ec_number (JSON key)"
    maps_to: ["EC"]
    join_confidence: "high"
  - local: "protein.* keys (protein IDs/labels)"
    maps_to: ["UniProt", "NCBI protein IDs (approximate)"]
    join_confidence: "medium"

cross_db_equivalents:
  - local: "reaction.*"
    target: "Rhea.rxn_id"
    relation: "approximate"

warnings:
  - "Protein identifiers are free-form and may mix UniProt accessions with lab-specific IDs."
  - "Organism strings are not normalized (species/strain/tissue mixed)."
  - "EC numbers may include deprecated or provisional entries."

# ===============================
# 4. CONTENT FLAGS & UNIT RULES (REQUIRED)
# ===============================

has_sequences: false
has_structures: false
has_kinetics: true
has_taxonomy: true
has_pathways: false

unit_fields:
  - field: "value/unit inside kinetics lists (km_value, turnover_number, kcat_km_value, ic50_value, ki_value, etc.)"
    typical_values: ["mM", "uM", "nM", "1/s", "mg/mL", "μmol/min/mg"]
    normalization_required: true
    critical_note: "Units are often missing (~71% of processed facts lacked explicit units) and sometimes embedded in free-text value strings."

# ===============================
# 5. LOCAL NORMALIZATION DONE (OPTIONAL BUT IMPORTANT)
# ===============================

local_processing:
  renamed_columns: false
  standardized_units: "none (raw strings only)"
  mapped_taxonomy: false
  dropped_invalid_rows: 0
  additional_notes:
    - "Data is unmodified raw release; all parsing/normalization happens in downstream ingestion."

# ===============================
# 6. SNAPSHOT STATS (REQUIRED)
# ===============================

stats_snapshot:
  estimated_rows: 2079335          # enzyme_facts emitted after ingestion
  missing_unit_fraction: 0.71      # derived from processed mirror; raw is similar or higher
  missing_taxid_fraction: 1.0      # raw has organism names only, no TaxIDs
  duplicate_fraction: "≈0.10 groups duplicated across ec_number/category/value/unit/context"
  sparsity_notes:
    - "Reactions and enzyme names are dense."
    - "Kinetic numeric fields often lack units or numeric parsing."
    - "Text/reference sections are large but unevenly populated by EC."

# ===============================
# 7. FAILURE PATTERNS WITH EXAMPLES (REQUIRED)
# ===============================

failure_patterns:
  - issue: "Unit embedded in value string or missing"
    example: "value='0.5 (glucose)' with unit null"
  - issue: "Free-form protein IDs"
    example: "protein key '1' or 'isoform A' instead of canonical accession"
  - issue: "Organism ambiguity"
    example: "context='Bacillus sp.' without strain"

# ===============================
# 8. AI USAGE GUIDANCE (OPTIONAL BUT VERY USEFUL)
# ===============================

best_queries:
  - "Extract inhibitors/cofactors for a given EC number."
  - "List Km/turnover numbers for an EC number with organism filter in context."

avoid_queries:
  - "Precise taxonomy joins without external normalization."
  - "Comparing across units without explicit normalization."

embedding_strategy:
  chunk_unit: "fact record (per ec_number/category/value)"
  must_include_fields: ["ec_number", "category", "value", "unit", "context", "references"]
  avoid_fields: ["raw_json blobs", "unparsed protein dictionaries"]

failure_modes:
  - "Never assume unit consistency or presence."
  - "Never assume protein identifiers are globally unique."

# ===============================
# 9. PROHIBITED USES (REQUIRED)
# ===============================

prohibited_use:
  - "Do not infer missing numeric values or units."
  - "Do not redistribute without honoring BRENDA license terms."

# ===============================
# 10. DATA TYPE GUARANTEES (OPTIONAL)
# ===============================

data_type_guarantees:
  - "Top-level EC keys are strings."
  - "Kinetic lists contain dicts with at least a 'value' field; other fields may be absent."

# ===============================
# 11. DATA CHANGELOG (REQUIRED FOR TEAM)
# ===============================

changelog:
  - date: "2025-12-18"
    schema_version: "1.0.0"
    changes:
      - "Documented raw BRENDA 2025_1 JSON/TXT snapshot; added checksums and high-level stats."

# ===============================
# 12. HEALTH CHECKS (REQUIRED)
# ===============================

health_check:
  file_openable: true
  row_count_ok: true
  unit_field_clean: false
  taxonomy_mapped: false

# ===============================
# 13. QUERY EXAMPLES (OPTIONAL)
# ===============================

query_examples:
  python_pandas: |
    import ijson
    with open("data/raw/brenda_2025_1.json","rb") as f:
        for ec, payload in ijson.kvitems(f, "data"):
            if ec == "2.7.1.1":
                print(payload.get("km_value", [])[:3])
                break

# ===============================
# 14. CITATIONS (REQUIRED)
# ===============================

primary_reference: "Schomburg I. et al., BRENDA in 2025, Nucleic Acids Research (Release 2025_1)"
additional_refs: []

## HUMAN SUMMARY (REQUIRED)
BRENDA 2025_1 raw JSON/TXT is a curated enzymology snapshot keyed by EC number. It contains kinetics, inhibitors/activators, substrates/products, and free-text annotations, plus per-enzyme protein dictionaries. The data is richly annotated but unnormalized: units may be missing or embedded in text, organism labels are free-form, and identifiers for proteins/variants are not standardized. Use it as the authoritative source for local mirrors, but normalize units and taxonomy before quantitative analyses.
