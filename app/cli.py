"""Interactive CLI for local testing.

Usage:
    python -m app.cli
    python -m app.cli "2025-yilda jami savdo summasi qancha?"
    python -m app.cli --debug "Eng ko'p paxta sotgan 5 kompaniya"
"""

from __future__ import annotations

import argparse
import sys

from .agent import get_agent


def print_response(question: str, debug: bool = False) -> None:
    response = get_agent().ask(question)
    print("\n" + response.answer)
    if debug:
        print("\n--- debug ---")
        print("intent:", response.intent)
        print("lang:", response.lang)
        print("filters:", response.filters)
        if response.sql:
            print("sql:", response.sql)
        print("used_llm:", response.used_llm)
    print()


def main() -> None:
    cli = argparse.ArgumentParser(description="UZEX local agent CLI")
    cli.add_argument("question", nargs="*", help="savol (bo'sh bo'lsa interaktiv rejim)")
    cli.add_argument("--debug", action="store_true", help="SQL va filtrlarni ko'rsatish")
    args = cli.parse_args()

    if args.question:
        print_response(" ".join(args.question), debug=args.debug)
        return

    print("UZEX local agent. Savolingizni yozing. Chiqish: /quit")
    while True:
        try:
            question = input("> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if not question:
            continue
        if question.lower() in {"/quit", "/exit", "quit", "exit"}:
            break
        print_response(question, debug=args.debug)


if __name__ == "__main__":
    sys.exit(main())
