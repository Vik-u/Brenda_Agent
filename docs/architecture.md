# Architecture Overview

The BRENDA Agentic Workflow is designed as a modular, production-ready scaffold for multi-agent research automation. It layers configuration-driven orchestration on top of domain agents that interact with the BRENDA enzyme database.

## Components

- **Configuration Layer** (`config/`, `src/core/settings.py`): Loads YAML configuration and environment variables to provide runtime settings.
- **Service Layer** (`src/services/brenda_client.py`, `src/services/chatbot.py`): Provides external service clients and the Ollama-backed SQL agent over the ingested BRENDA data.
- **Agent Layer** (`src/agents/`): Encapsulates distinct responsibilities for the orchestration, research, and analysis roles.
- **Workflow Layer** (`src/workflows/`): Defines high-level business processes that sequences agents and aggregates outputs.
- **Interface Layer** (`src/main.py`, `scripts/`): Command-line entrypoints and automation scripts for running workflows.

## Control Flow

1. `BrendaEnzymeInsightWorkflow` seeds the orchestrator with the EC number and optional organism.
2. `OrchestratorAgent` coordinates `ResearcherAgent` and `AnalystAgent` tasks using asynchronous execution.
3. `ResearcherAgent` calls the BRENDA API via `BrendaClient`, collecting enzyme records.
4. `AnalystAgent` validates and summarizes the collected data using pandas.
5. The orchestrator composes a final report for downstream consumers.

## Extending the System

- Add new agents by subclassing `BaseAgent` and registering them in the orchestrator.
- Extend workflows via YAML configuration (`config/workflows.yaml`) and implementation modules under `src/workflows/`.
- Integrate observability by piping structlog events into metrics/trace backends.
- Deploy the workflow behind an API by wrapping `BrendaEnzymeInsightWorkflow` in a FastAPI service.
- Build conversational tooling by wiring `BrendaChatbot` into chat UIs or agent frameworks.
