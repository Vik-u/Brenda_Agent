# BRENDA Agentic Workflow

Production-ready scaffolding for a multi-agent system that mines, analyses, and reports on enzymatic information from the BRENDA database.

## Features

- Structured configuration via YAML + environment variables
- Async client for the BRENDA API
- Multi-agent orchestration (researcher, analyst, orchestrator)
- Workflow runner with logging and reporting
- Ready-to-use Python virtual environment, dependency management, and lint/test tooling
- Offline fallback to the ingested SQLite mirror when the upstream API is unavailable

## Getting Started

### Requirements

- Python 3.11 (use `scripts/setup_py311_env.sh` to create `.venv-py311`)
- Ollama running locally with the `gpt-oss:20b` model (`ollama pull gpt-oss:20b`)
- Raw BRENDA dumps (`brenda_2025_1.json` and `brenda_2025_1.txt`) placed in `data/raw/`
- Processed SQLite mirror (`data/processed/brenda.db`) – generated locally, not stored in Git

### 1. Bootstrap the virtual environment

```bash
cd Brenda_Agent
./scripts/setup_py311_env.sh

# manual alternative
# python3.11 -m venv .venv-py311
# source .venv-py311/bin/activate
# pip install -r requirements/base.txt
```

### 2. Configure application settings

```bash
cp .env.example .env
```

Add BRENDA/OpenAI/Redis credentials if you have them. The chatbot relies on `OLLAMA_BASE_URL` and `OLLAMA_MODEL` only when diverging from the defaults in `config/settings.yaml`.

### 3. Build the local BRENDA database

Download the official JSON/TXT dumps from BRENDA and place them under `data/raw/`:

```
data/raw/brenda_2025_1.json
data/raw/brenda_2025_1.txt
```

Then build the SQLite mirror (stored at `data/processed/brenda.db`):

```bash
./scripts/build_brenda_db.sh
```

This script activates the virtual environment, runs the streaming ingester, and overwrites any existing database.

### 4. Ensure Ollama is ready

```bash
ollama pull gpt-oss:20b
ollama serve  # run in a separate terminal
```

### 5. Verify the local database

Confirm `data/processed/brenda.db` exists. If not, rerun `./scripts/build_brenda_db.sh` and double-check that the raw dumps are present.

## Running the Workflow

```bash
source .venv-py311/bin/activate
python -m src.main 1.1.1.1 --organism "Homo sapiens"
```

## Testing

```bash
source .venv-py311/bin/activate
python -m pytest
```

## Project Layout & Agent Roles

- `config/` – Runtime configuration for agents and workflows (`settings.yaml`, `agents.yaml`, `workflows.yaml`).
- `src/` – Application code:
  - `agents/researcher.py` – Proposes exploration paths, identifies knowledge gaps, and drafts intermediate hypotheses on top of the BRENDA facts. Uses the LLM to reason about new angles.
  - `agents/analyst.py` – Validates and enriches the researcher’s ideas by querying the structured database, summarising kinetics/inhibitors, and checking for inconsistencies.
  - `agents/orchestrator.py` – Coordinates the researcher/analyst loop, applies retry/blending policies, and determines when a report is ready.
  - `workflows/brenda_enzyme_insight.py` – High-level workflow definition that wires the agent trio, settings, and persistence hooks (see `crew/workflow.py` for orchestration scaffolding).
  - `services/` – Integrations (Brenda API client, Chatbot, PubMed fetchers, response formatter).
  - `core/` & `utils/` – Environment configuration, logging, shared helpers.
- `scripts/` – Automation helpers (env setup, chatbot/Gradio/API runners, Nextflow glue).
- `tests/` – Pytest suite validating settings loading and the chatbot abstraction.
- `docs/` – Architecture notes and generated analysis outputs.

## Next Steps

- Integrate real authentication flow for the BRENDA API.
- Connect to vector stores or RAG pipelines for literature enrichment.
- Wire up observability (metrics, traces) and persistence for results.

## Data Preparation

Run the helper script to convert the raw BRENDA dumps into the structured SQLite database:

```bash
./scripts/build_brenda_db.sh \
  data/raw/brenda_2025_1.json \
  data/raw/brenda_2025_1.txt \
  data/processed/brenda.db
```

Internally this invokes `python -m src.pipelines.brenda_ingestion`, streaming the JSON (≈661 MB) with `ijson` and parsing the TXT dump. The output database contains the `enzymes`, `proteins`, `enzyme_facts`, and `text_facts` tables used by the agents.

Generate a Markdown snapshot once the database exists:

```bash
python -m src.pipelines.brenda_analysis --output docs/brenda_analysis.md
```

### Regenerating large artifacts

Several derived datasets are intentionally excluded from Git. Rebuild them locally with the commands below (activate the virtual environment first):

| Output file | Purpose | Command |
| --- | --- | --- |
| `artifacts/pubmed_references.json` | Aggregated PubMed IDs per EC number | `python -m src.pipelines.pubmed_reference_export --database data/processed/brenda.db --output artifacts/pubmed_references.json` |
| `artifacts/pubmed_articles.json` | Full article metadata + cleaned HTML for each PMID | `python -m src.pipelines.pubmed_article_scrape --references artifacts/pubmed_references.json --output artifacts/pubmed_articles.json` |
| `artifacts/pubmed_links.json` | Lightweight mapping of PubMed IDs to EC context | `python -m src.pipelines.pubmed_link_index --articles artifacts/pubmed_articles.json --output artifacts/pubmed_links.json` |
| `artifacts/pubmed_stats_summary.json`, plots in `artifacts/figures/` | Visual summaries and statistics | `python -m src.pipelines.pubmed_stats --references artifacts/pubmed_references.json --links artifacts/pubmed_links.json --summary artifacts/pubmed_stats_summary.json` |

These files can be large (100 MB–600 MB) and are gitignored. Remove them freely and regenerate when needed.

## Dependencies

The project uses Python packages from `requirements/base.txt`. Key runtime dependencies include:

- `langchain`, `langchain-community`, `langchain-openai` – Agent framework and LLM wrappers.
- `sqlalchemy`, `pandas`, `tabulate` – Structured data access and tabular formatting.
- `fastapi`, `uvicorn[standard]` – REST API layer for interactive exploration.
- `structlog` – Structured logging throughout agents and services.
- `redis`, `requests`, `httpx` – Optional caching and HTTP integrations.
- `gradio`, `rich` – Chat UI and rich CLI output.
- `ijson`, `aiofiles` – Streaming ingestion of large JSON dumps.

Install everything with:

```bash
source .venv-py311/bin/activate
pip install -r requirements/base.txt
```

## Interactive API

Launch the FastAPI service for browsing enzymes, facts, and kinetic parameters:

```bash
./scripts/serve_api.sh
```

Endpoints:
- `GET /health` – health probe.
- `GET /search?q=...` – fuzzy search across enzyme names and synonyms.
- `GET /enzymes/{ec}` – base metadata plus grouped facts/proteins.
- `GET /enzymes/{ec}/facts` – paginated facts filtered by category.
- `GET /kinetics` – cross-enzyme view over KM, kcat/KM, turnover, and specific activity data.
- `GET /text-fields` – paginate raw BRENDA text fields by EC or field code.

Quick smoke test:

```bash
curl -s http://localhost:8000/health
# -> {"status":"ok"}
```

Interactive docs are available at http://localhost:8000/docs once the server is running.

Example query for enzyme metadata + grouped facts:

```bash
curl -s "http://localhost:8000/enzymes/1.1.1.1?limit=5" | jq '.recommended_name, .facts[0]'
```


## Nextflow Pipeline

Execute the full data build + analysis pipeline using Nextflow (Chatbot stage is optional).

```bash
nextflow run main.nf

# enable the crew/LLM demo once Ollama is running locally
nextflow run main.nf --enable_chatbot true
```

The pipeline orchestrates the ingestion, analysis, PubMed enrichment, and optional chatbot demo via the processes defined in `main.nf`. Each process maps directly to the Python pipelines shown above, allowing reproducible end-to-end builds on local machines or CI runners. Use `nextflow run main.nf -resume` to leverage Nextflow’s caching between runs.

## Chatbot Interfaces

### CLI (rich-formatted)

Activate the virtual environment and make sure the Ollama daemon is running:

```bash
source .venv-py311/bin/activate

# Inspect available tables and columns
./scripts/run_chatbot.sh --schema

# Run a question and display the executed SQL
./scripts/run_chatbot.sh "Summarize inhibitors reported for EC 1.1.1.1" --show-sql
```

Example response (truncated):

```markdown
**EC 1.1.1.1 – Alcohol Dehydrogenase (ADH)**  
The classic “alcohol dehydrogenase” that converts alcohols to aldehydes/ketones (or vice‑versa) using NAD⁺/NADH as a co‑factor. It is found in virtually every organism that needs to metabolise ethanol or other short‑chain alcohols.

| Inhibitor | Concentration & Effect | Notes |
|-----------|------------------------|-------|
| **Na⁺** | 10 mM → 13 % loss of activity | Mild ionic inhibition; relevant when tweaking buffer composition. |
| **Isopropanol** | 50 % (v/v) → 88 % loss | Strong solvent-induced inhibition — keep below 5 % in assays. |
| **Methanol** | 50 % (v/v) → 30 % loss | Noticeable impact at high solvent content, but less severe than isopropanol. |
```

The CLI renders Markdown via `rich`, includes executed SQL in a highlighted panel, and exposes a `--model` flag if you want to override the Ollama model. The underlying class is importable for scripts: `from src.services import BrendaChatbot`.

### Gradio chat UI

```bash
./scripts/run_gradio_chatbot.sh --port 8570
```

This starts a local chat UI at http://127.0.0.1:8570 (auto-selected if the port is busy). Use the optional text box to override the Ollama model and the checkbox to stream the executed SQL with each response. The session keeps conversational history so you can ask follow-up questions without losing context.

> **Note:** LangChain currently emits a deprecation warning about `ChatOllama`. You can silence it by `pip install langchain-ollama` and updating the configuration, but it does not affect functionality.

### Programmatic access

```python
from src.services.chatbot import BrendaChatbot

bot = BrendaChatbot()
result = bot.ask("Summarize inhibitors reported for EC 1.1.1.1")
print(result.answer)
print(result.sql)  # list of executed queries
```

Pair this with the FastAPI service to offer remote access:

```bash
source .venv-py311/bin/activate
uvicorn src.interfaces.api:app --host 0.0.0.0 --port 8000
```

You can now send POST requests to `/chat` with `{"question": "..."}` for fully automated workflows.

```bash
curl -s -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{"question": "Summarize inhibitors reported for EC 1.1.1.1"}' \
  | jq '.answer'
```

## Verification Checklist

Before pushing changes or deploying, confirm the following:

- `source .venv-py311/bin/activate && pip install -r requirements/base.txt` completes without errors.
- `./scripts/run_chatbot.sh "Summarize inhibitors reported for EC 1.1.1.1" --show-sql` returns a formatted Markdown answer and shows the executed SQL in a panel.
- `./scripts/run_gradio_chatbot.sh` launches the web UI and returns answers for a couple of queries.
- `./scripts/serve_api.sh` starts successfully and `curl -s http://localhost:8000/health` responds with `{"status":"ok"}`.
- `python -m pytest` passes (optional but recommended before releases).
