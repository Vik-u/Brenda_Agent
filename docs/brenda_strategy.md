# BRENDA Data Strategy

## Objectives

- Transform the BRENDA JSON release into a form that supports interactive exploration and downstream automation.
- Keep the pipeline reproducible, memory-safe, and auditable.
- Provide a foundation for API / agent workflows that require fast lookups over enzyme facts and kinetics.

## Evaluated Options

1. **Ad-hoc JSON Access** – Load fragments of the 661 MB JSON dump in memory on demand and let agents query with Python helpers.
   - *Pros*: No extra storage layer, minimal upfront work.
   - *Cons*: Memory spikes when multiple agents access data, slow repeated parsing, no indexing, hard to share with other services.

2. **Document Store (e.g., MongoDB, Elasticsearch)** – Import JSON wholesale into a document database and expose search endpoints.
   - *Pros*: Native JSON querying, built-in indexing/search.
   - *Cons*: Requires external infrastructure, more operational overhead, difficult to version-control, overkill for offline analysis.

3. **Relational / Analytical Store (SQLite or DuckDB)** – Stream the JSON once, normalize core entities (enzymes, proteins, quantitative facts) into a portable database, and build APIs/views on top.
   - *Pros*: Strong indexing, ACID, zero external dependencies, easy to ship with the repo, can power both analytics and services.
   - *Cons*: Requires ingestion work and schema design; very large analytical queries may need optimization.

## Chosen Approach

Option 3 is the best fit. We ingest the JSON into a structured SQLite database with:
- An `enzymes` table summarising high-level metadata and counts.
- A `proteins` table for organism-specific enzyme instances.
- An `enzyme_facts` wide table capturing all list-like attributes (kinetics, inhibitors, cofactors, tissues, etc.) with normalized numeric/context columns for filtering.

The ingestion pipeline streams the JSON via `ijson` to stay memory-safe and emits indexes for fast search. In addition, the legacy tab-delimited TXT download is parsed into a `text_facts` table so the short-form BRENDA annotations (AC, AP, CF, etc.) remain queryable alongside the structured JSON. This layout keeps the data portable, enables SQL for analytics, and can back both FastAPI endpoints and agent tools without external services. The structured tables also make it easy to export subsets (Parquet/CSV) or load into warehouse solutions later if needed.

## Next Steps

- Run `python -m src.pipelines.brenda_ingestion` to build `data/processed/brenda.db`.
- Add lightweight API endpoints (FastAPI) for EC lookup and free-text search over facts.
- Layer agent tools on top of SQL queries for kinetic parameter retrieval and reporting.
