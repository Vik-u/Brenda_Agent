# ===============================
# 1. IDENTIFICATION & CONTEXT (REQUIRED)
# ===============================

service_name: "REQUIRED"          # e.g., UniProt REST API, KEGG REST, NCBI E-utilities
short_name: "REQUIRED"            # e.g., uniprot_api, kegg_rest, ncbi_esearch
provider: "REQUIRED"              # e.g., UniProt, KEGG, NCBI
domain: "REQUIRED"                # e.g., Sequence, Pathway, Kinetics, Structure, Literature
documentation_url: "REQUIRED"
terms_of_use_url: "OPTIONAL"
support_contact: "OPTIONAL"       # email, helpdesk URL, or issue tracker

service_type: "REST_API / GraphQL_API / FTP / SOAP / CLI / Mixed"
supports_bulk_download: true/false
has_offline_dump_alternative: true/false    # e.g., prebuilt dump via FTP or snapshot

license: "REQUIRED"               # e.g., CC-BY-4.0, custom, restricted
commercial_use_allowed: true/false/unknown

# ===============================
# 2. ACCESS & AUTHENTICATION (REQUIRED)
# ===============================

access_methods:
  - method: "REST"
    base_url: "https://api.example.org/v1"
  - method: "FTP"
    base_url: "ftp://ftp.example.org/pub/database"

authentication:
  required: true/false
  auth_type: "None / API_KEY / OAuth2 / Token / IP_ALLOWLIST / Other"
  credential_acquisition: "Short instructions or URL"
  credential_storage_recommended:
    - "Environment variables"
    - "Config file outside version control"
    - "Secret manager"

network_requirements:
  - "Outbound HTTPS required"
  - "FTP ports must be allowed if FTP is used"

# ===============================
# 3. DATA MODEL & ENTITIES (REQUIRED)
# ===============================

primary_entities:                 # core objects this service exposes
  - "Protein"
  - "Reaction"
  - "Pathway"
secondary_entities:               # supporting entities
  - "Organism"
  - "Taxonomy"
  - "Evidence"
  - "CrossReference"

resource_overview:
  - name: "entry"
    description: "Single primary entity record (e.g., one protein, one reaction)."
  - name: "search"
    description: "Search over primary entities with filters and pagination."
  - name: "metadata"
    description: "Service-level or database-level metadata (versions, releases)."

join_keys:
  - local_field: "accession"
    maps_to: ["UniProtKB Accession"]
    join_confidence: "high"
  - local_field: "tax_id"
    maps_to: ["NCBI Taxonomy ID"]
    join_confidence: "high"
  - local_field: "ec_number"
    maps_to: ["EC Number"]
    join_confidence: "medium"

cross_db_equivalents:
  - local: "accession"
    target: "internal_db.uniprot_id"
    relation: "exact"
  - local: "tax_id"
    target: "ncbi.taxonomy.tax_id"
    relation: "exact"
  - local: "pathway_id"
    target: "kegg.pathway.id"
    relation: "approximate"

# ===============================
# 4. ENDPOINTS & PARAMETERS (REQUIRED)
# ===============================

endpoints:
  - name: "Get entry by ID"
    path: "/entries/{id}"                 # relative to base_url
    method: "GET"
    description: "Retrieve a single primary entity by its identifier."
    path_parameters:
      - name: "id"
        type: "string"
        required: true
        example: "P12345"
    query_parameters:
      - name: "format"
        type: "string"
        required: false
        allowed_values: ["json", "xml"]
        default: "json"
    request_body: null
    response_format: "JSON"
    typical_http_statuses: [200, 400, 404, 500]

  - name: "Search entries"
    path: "/entries/search"
    method: "GET"
    description: "Search across primary entities using filters."
    query_parameters:
      - name: "query"
        type: "string"
        required: true
        example: "ec:1.1.1.* AND organism_id:9606"
      - name: "size"
        type: "integer"
        required: false
        default: 100
      - name: "cursor"
        type: "string"
        required: false
        description: "Pagination cursor for subsequent pages."
    response_format: "JSON"
    typical_http_statuses: [200, 400, 429, 500]

pagination:
  style: "cursor / offset / page_token / none"
  fields:
    - "size"
    - "cursor"
  notes: "Describe how to iterate over all results safely."

filtering:
  supported: true/false
  example_syntax:
    - "ec:1.1.1.*"
    - "organism_id:9606"
    - "length:[100 TO 500]"

sorting:
  supported: true/false
  example_syntax:
    - "sort=score:desc"

# ===============================
# 5. RESPONSE STRUCTURE (REQUIRED)
# ===============================

primary_response_schema:          # high-level description, not full OpenAPI
  entity_name: "entry"
  key_fields:
    - "id"
    - "accession"
    - "tax_id"
  example_fields:
    - name: "id"
      type: "string"
      description: "Internal or public identifier."
    - name: "accession"
      type: "string"
      description: "Stable canonical identifier (e.g., UniProt accession)."
    - name: "sequence"
      type: "string"
      description: "Amino acid sequence if applicable."
    - name: "ec_numbers"
      type: "list<string>"
      description: "Associated EC numbers."
    - name: "cross_references"
      type: "list<object>"
      description: "Links to external databases."

response_formats:
  - "JSON"
  - "XML"
  - "TSV"
  - "FASTA"

sparsity_notes:
  - "Some fields are present only for well-curated entries."
  - "Legacy records may lack newer annotations."

# ===============================
# 6. PERFORMANCE & RATE LIMITS (REQUIRED)
# ===============================

rate_limits:
  documented: true/false
  requests_per_second_soft: "number or unknown"
  requests_per_second_hard: "number or unknown"
  daily_quota: "number or unknown"
  rate_limit_docs_url: "OPTIONAL"

latency_profile:
  typical_latency_ms: "range, e.g., 200–800"
  high_latency_scenarios:
    - "Large search queries with size > 1000."
    - "Endpoints that aggregate across multiple resources."

recommended_client_settings:
  default_rps: 1
  max_parallel_requests: 2
  timeout_seconds: 30

backoff_and_retry_strategy:
  - "Use exponential backoff on HTTP 429 and 500."
  - "Respect Retry-After header when available."
  - "Do not retry on 400-level client errors except 408/429."

# ===============================
# 7. ERROR HANDLING & FAILURE PATTERNS (REQUIRED)
# ===============================

http_error_semantics:
  - code: 400
    meaning: "Invalid request or malformed query."
  - code: 401
    meaning: "Authentication required or invalid credentials."
  - code: 403
    meaning: "Access forbidden or quota exceeded for this account."
  - code: 404
    meaning: "Resource not found."
  - code: 429
    meaning: "Rate limit exceeded."
  - code: 500
    meaning: "Internal server error."

retryable_errors:
  - 429
  - 500
  - "Network timeouts"

failure_patterns:
  - issue: "Silent truncation of results when pagination parameters are omitted."
  - issue: "Inconsistent field presence across old and new records."
  - issue: "Some endpoints return different schemas for similar entities."
  - issue: "FTP directory contents may change without explicit version tags."

# ===============================
# 8. LOCAL CACHING & MIRRORING STRATEGY (REQUIRED)
# ===============================

caching_recommended: true/false
cache_use_cases:
  - "Repeated queries during the same workflow."
  - "Stable reference data (e.g., taxonomy)."
cache_location: "e.g., /data/cache/uniprot_api"   # cluster path or bucket

cache_format:
  - "Parquet"
  - "JSONL"
  - "SQLite"

cache_invalidation:
  strategy:
    - "Time-based refresh (e.g., weekly)."
    - "Manual refresh when upstream releases a new version."
  notes:
    - "For frequently updated data, prefer short cache TTL."

bulk_mirroring:
  supported: true/false
  approach:
    - "If FTP is available, mirror specific directories."
    - "If REST supports bulk export, use that instead of per-ID requests."

# ===============================
# 9. SECURITY & PRIVACY (REQUIRED)
# ===============================

contains_sensitive_data: false/true
notes:
  - "Typically only public biological data; verify if any human subject data is exposed."

credential_handling:
  - "Store API keys in environment variables (e.g., SERVICE_API_KEY)."
  - "Do not hard-code credentials in notebooks or scripts."
  - "Do not commit credentials to version control."

access_control_notes:
  - "Some endpoints may be restricted to specific IP ranges or subscription tiers."

# ===============================
# 10. API VERSIONING & STABILITY (REQUIRED)
# ===============================

api_versioning:
  current_version: "e.g., v1"
  version_in_url: true/false
  version_in_header: true/false

stability:
  deprecation_policy_known: true/false
  stability_notes:
    - "Core endpoints are stable."
    - "Experimental endpoints may change without notice."

changelog_url: "OPTIONAL"

# ===============================
# 11. EXAMPLE USAGE (REQUIRED)
# ===============================

example_requests:
  curl:
    - description: "Fetch a single entry by ID."
      command: |
        curl "https://api.example.org/v1/entries/P12345"
    - description: "Search entries by EC and organism."
      command: |
        curl "https://api.example.org/v1/entries/search?query=ec:1.1.1.*%20AND%20organism_id:9606&size=100"

  python:
    - description: "Basic GET request with error handling."
      code: |
        import requests

        url = "https://api.example.org/v1/entries/P12345"
        r = requests.get(url, timeout=30)
        r.raise_for_status()
        data = r.json()

# ===============================
# 12. AGENT USAGE GUIDANCE (REQUIRED)
# ===============================

intended_agent_behaviors:
  - "Use the API when up-to-date information is required."
  - "Prefer cached or mirrored data for large-scale analyses."
  - "Respect documented rate limits and quotas."

prohibited_agent_behaviors:
  - "Do not brute-force identifiers sequentially."
  - "Do not crawl the entire API via per-ID requests if bulk options exist."
  - "Do not treat a single page of results as a complete dataset."

good_query_patterns:
  - "Given a stable identifier, fetch a single entity."
  - "Search with explicit filters and controlled page size."
bad_query_patterns:
  - "Unbounded free-text search without filters."
  - "Very large page sizes that risk timeouts or truncation."

# ===============================
# 13. PIPELINE INTEGRATION NOTES (OPTIONAL)
# ===============================

used_by_components:
  - "enzyme_knowledge_agent"
  - "pathway_mapping_pipeline"

downstream_artifacts:
  - "Local normalized SQLite database."
  - "Parquet tables used in analytics."

# ===============================
# 14. CHANGELOG (REQUIRED FOR TEAM)
# ===============================

service_record_changelog:
  - date: "YYYY-MM-DD"
    changes:
      - "Initial documentation."
  - date: "YYYY-MM-DD"
    changes:
      - "Updated rate limit and pagination details."
      - "Added new endpoint examples."

## HUMAN SUMMARY (REQUIRED)

Write 1–3 paragraphs explaining:

- What biological or technical content this service exposes.
- When to use the live API versus local mirrors or dumps.
- Known quirks, instabilities, or operational risks.
