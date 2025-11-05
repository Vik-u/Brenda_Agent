"""CLI entrypoint for running the BRENDA multi-agent workflow."""

from __future__ import annotations

import argparse
import asyncio
from typing import Optional

from src.workflows.brenda_enzyme_insight import BrendaEnzymeInsightWorkflow


async def _run_workflow(ec_number: str, organism: Optional[str]) -> None:
    workflow = BrendaEnzymeInsightWorkflow()
    result = await workflow.run(ec_number=ec_number, organism=organism)
    print("=== Workflow Result ===")
    print(result["report"])


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run the BRENDA enzyme insight multi-agent workflow",
    )
    parser.add_argument("ec_number", help="EC number to investigate, e.g. 1.1.1.1")
    parser.add_argument("--organism", help="Optional organism filter")
    args = parser.parse_args()

    asyncio.run(_run_workflow(ec_number=args.ec_number, organism=args.organism))


if __name__ == "__main__":
    main()
