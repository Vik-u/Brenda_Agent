"""Command-line interface for the BrendaChatbot."""

from __future__ import annotations

import argparse

from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.syntax import Syntax

from src.services.chatbot import BrendaChatbot

console = Console()


def main() -> None:
    parser = argparse.ArgumentParser(description="Query the BRENDA database via the LLM agent")
    parser.add_argument(
        "question",
        nargs="?",
        help="Natural-language question to ask the agent (omit with --schema)",
    )
    parser.add_argument(
        "--show-sql",
        action="store_true",
        help="Print the SQL statements executed by the agent",
    )
    parser.add_argument(
        "--schema",
        action="store_true",
        help="Show the table/column overview instead of running a query",
    )
    parser.add_argument(
        "--model",
        help="Override the Ollama model to use (defaults to configuration)",
    )
    args = parser.parse_args()

    if not args.schema and not args.question:
        parser.error("provide a question or use --schema")

    bot = BrendaChatbot(model=args.model)

    if args.schema:
        schema = bot.schema_overview()
        console.print_json(data=schema)
        return

    result = bot.ask(args.question)
    console.print(Markdown(result.answer))

    if args.show_sql and result.sql:
        sql_text = "\n\n".join(result.sql)
        panel = Panel(
            Syntax(sql_text, "sql", theme="monokai", word_wrap=True, background_color="black"),
            title="Executed SQL",
            border_style="cyan",
        )
        console.print(panel)


if __name__ == "__main__":
    main()
