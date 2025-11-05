"""CrewAI orchestration over the BRENDA knowledge base."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Dict, Optional

from crewai import Agent, Crew, Task
from langchain_core.tools import Tool
from langchain_community.chat_models import ChatOllama

from src.core.settings import get_settings
from src.services.chatbot import BrendaChatbot


@dataclass
class CrewRunResult:
    """Bundle the raw crew output together with structured payloads."""

    final_answer: str
    query_payload: Dict[str, Any]
    filter_payload: Dict[str, Any]


def _build_llm(model_override: Optional[str] = None) -> ChatOllama:
    settings = get_settings()
    ollama_cfg = settings.services.ollama
    return ChatOllama(
        model=model_override or ollama_cfg.model,
        base_url=ollama_cfg.base_url,
        temperature=ollama_cfg.temperature,
        top_p=ollama_cfg.top_p,
    )


def _build_brenda_tool(chatbot: BrendaChatbot) -> Tool:
    def _run(question: str) -> str:
        result = chatbot.ask(question)
        payload = {
            "question": question,
            "sql": result.sql,
            "rows": result.raw.get("rows", []),
        }
        return json.dumps(payload, ensure_ascii=False)

    return Tool.from_function(
        func=_run,
        name="brenda_sql_lookup",
        description=(
            "Query the structured BRENDA SQLite database. Always pass a clear, "
            "domain-specific question. The tool returns JSON with the executed "
            "SQL and the matching rows."
        ),
    )


def build_brenda_crew(
    user_request: str, model_override: Optional[str] = None
) -> Crew:
    """Create a Crew that performs filter -> query -> reporting over BRENDA."""

    llm_filter = _build_llm(model_override)
    llm_query = _build_llm(model_override)
    llm_report = _build_llm(model_override)

    chatbot = BrendaChatbot(llm=_build_llm(model_override))
    brenda_tool = _build_brenda_tool(chatbot)

    filter_agent = Agent(
        role="Constraint Planner",
        goal="Understand the scientist's request and propose precise database filters.",
        backstory=(
            "You are an experienced enzymologist. Given a free-form request you "
            "identify EC numbers, organisms, mutation terms, wildtype mentions "
            "and other constraints."
        ),
        llm=llm_filter,
        memory=False,
        verbose=False,
        allow_delegation=False,
    )

    query_agent = Agent(
        role="BRENDA Data Miner",
        goal=(
            "Use the SQL lookup tool to fetch structured information (substrates, "
            "kinetics, inhibitors, variants) that satisfy the planner's constraints."
        ),
        backstory=(
            "You specialise in crafting precise SQL based on the schema for the "
            "BRENDA SQLite mirror."
        ),
        llm=llm_query,
        memory=False,
        verbose=False,
        allow_delegation=False,
        tools=[brenda_tool],
    )

    report_agent = Agent(
        role="Scientific Communication Specialist",
        goal="Present findings in clear, human-friendly language with insights.",
        backstory=(
            "You convert structured enzyme data into practical conclusions for "
            "biochemists, always highlighting missing data and suggesting next experiments."
        ),
        llm=llm_report,
        memory=False,
        verbose=False,
        allow_delegation=False,
    )

    filter_task = Task(
        description=(
            "Analyse the following request and summarise the required search constraints. "
            "Identify EC numbers, organisms, mutation or wildtype requirements, kinetic "
            "parameters, and any other relevant filters. Return a compact JSON payload with "
            "keys: refined_query (str), filters (list[str]), and notes (str).\n\n"
            f"User request: {user_request}"
        ),
        expected_output=(
            "JSON with keys refined_query (str), filters (list[str]), notes (str)."
        ),
        agent=filter_agent,
    )

    query_task = Task(
        description=(
            "Using the JSON from the planner, craft a question for the brenda_sql_lookup tool. "
            "Focus on the requested EC numbers and constraints. The tool returns JSON with SQL "
            "and rows. If multiple tool calls are needed, merge rows and deduplicate them."
        ),
        expected_output=(
            "JSON containing keys refined_query, sql, rows (list of dicts), and commentary summarising the retrieved data."
        ),
        agent=query_agent,
        tools=[brenda_tool],
        context=[filter_task],
    )

    report_task = Task(
        description=(
            "Write a comprehensive, conversational answer for the user using the structured JSON from the query task and the planner notes. "
            "Mention enzyme roles, substrates, kinetics, inhibitors, mutations, missing data, and include a suggested next step."
        ),
        expected_output="A multi-paragraph response suitable for a researcher.",
        agent=report_agent,
        context=[filter_task, query_task],
    )

    crew = Crew(
        agents=[filter_agent, query_agent, report_agent],
        tasks=[filter_task, query_task, report_task],
        verbose=True,
    )
    return crew


def _parse_json_safely(text: Optional[str]) -> Dict[str, Any]:
    if not text:
        return {}
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return {"raw": text}


def run_brenda_crew(
    user_request: str, model_override: Optional[str] = None
) -> CrewRunResult:
    """Kick off the crew pipeline and collect structured outputs."""

    crew = build_brenda_crew(user_request=user_request, model_override=model_override)
    final_answer = crew.kickoff()

    filter_output = crew.tasks[0].output.result if crew.tasks[0].output else None
    query_output = crew.tasks[1].output.result if crew.tasks[1].output else None

    return CrewRunResult(
        final_answer=final_answer,
        query_payload=_parse_json_safely(query_output),
        filter_payload=_parse_json_safely(filter_output),
    )
