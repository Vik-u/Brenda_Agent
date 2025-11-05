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
- Processed BRENDA database at `data/processed/brenda.db` (see [Data Preparation](#data-preparation))

### 1. Bootstrap the virtual environment

```bash
cd brenda-agentic-workflow
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

### 3. Ensure Ollama is ready

```bash
ollama pull gpt-oss:20b
ollama serve  # run in a separate terminal
```

### 4. Verify the local database

Confirm `data/processed/brenda.db` exists. If you need to build it, run the ingestion pipeline described in [Data Preparation](#data-preparation).

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

## Project Layout

- `config/` – Runtime configuration for agents and workflows
- `src/` – Application code
  - `agents/` – Agent implementations (researcher, analyst, orchestrator)
  - `services/` – External service clients (BRENDA API)
  - `workflows/` – Workflow orchestration logic
  - `core/` – Shared configuration utilities
  - `utils/` – Logging and helpers
- `tests/` – Pytest-based unit tests
- `docs/` – Architecture and operational documentation
- `scripts/` – Automation scripts for deployment & operations

## Next Steps

- Integrate real authentication flow for the BRENDA API.
- Connect to vector stores or RAG pipelines for literature enrichment.
- Wire up observability (metrics, traces) and persistence for results.

## Data Preparation

Run the ingestion pipeline to convert the raw BRENDA JSON dump into a structured SQLite database:

```bash
source .venv-py311/bin/activate
# unpack tarballs if you pulled the raw archives
# tar -xf data/brenda_2025_1.json.tar -C data/raw
# tar -xf data/brenda_2025_1.txt.tar -C data/raw
python -m src.pipelines.brenda_ingestion --source data/raw/brenda_2025_1.json --text data/raw/brenda_2025_1.txt --target data/processed/brenda.db
```

The script streams the 2025.1 JSON release (~661 MB) with `ijson` and parses the legacy TXT dump, producing `data/processed/brenda.db` with summary tables (`enzymes`, `proteins`), a wide `enzyme_facts` table, and a `text_facts` table that keeps the short-form annotations (AC, KM, IN, etc.).

Generate a Markdown snapshot once the database exists:

```bash
python -m src.pipelines.brenda_analysis --output docs/brenda_analysis.md
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
