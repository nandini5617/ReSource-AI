"""ReSource AI command-line interface.

Run:  python main.py                          (interactive)
      python main.py "I have 3 old chairs"    (one-shot)
      python main.py --mock "..."             (force offline mode)

Exchange approval and completion are user actions: /approve and /complete ask
you to type 'yes'. The AI itself can never approve or complete an exchange.
"""
from __future__ import annotations

import argparse
import json
import os
import sys

HELP = (
    "Commands: /records  /exchanges  /approve <id>  /complete <id>  "
    "/cancel <id>  /reset  /exit"
)


def _print_result(result) -> None:
    for step in result.trace:
        args = json.dumps(step["args"], ensure_ascii=False, default=str)
        status = "ERROR" if "error" in step["result"] else "ok"
        print(f"  [tool] {step['tool']}({args[:100]}) -> {status}")
    if result.provider:
        print(f"  [provider] {result.provider}")
    print("\n" + result.answer + "\n")


def _print_outcome(result: dict) -> None:
    if "error" in result:
        print("  Not done:", result["error"], "\n")
        return
    print(f"  Exchange {result['exchange_id']} is now '{result['status']}'.")
    if "impact_logged" in result:
        est = result["impact_logged"]
        print(f"  Impact logged ({est['label']}): ~{est['kg_diverted']} kg diverted, "
              f"~{est['co2e_avoided_kg']} kg CO2e avoided.")
    print()


def _ask_yes(question: str) -> bool:
    try:
        return input(question + " Type 'yes' to confirm: ").strip().lower() == "yes"
    except (EOFError, KeyboardInterrupt):
        return False


def _parse_id(text: str) -> int | None:
    parts = text.split()
    if len(parts) == 2 and parts[1].isdigit():
        return int(parts[1])
    print("  Usage example: /approve 3\n")
    return None


def _show_exchanges(database) -> None:
    rows = database.list_exchanges(20)
    if not rows:
        print("  No exchanges yet.\n")
        return
    for ex in rows:
        res = database.get_resource(ex["resource_id"])
        org = database.get_org(ex["org_id"])
        print(f"  #{ex['id']} [{ex['status']}] "
              f"{res['name'] if res else '?'} -> {org['name'] if org else '?'}")
    print()


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    parser = argparse.ArgumentParser(description="ReSource AI agent")
    parser.add_argument("prompt", nargs="*", help="One-shot request")
    parser.add_argument("--mock", action="store_true", help="Force offline mode")
    args = parser.parse_args()
    if args.mock:
        os.environ["RESOURCE_AI_MOCK"] = "1"

    import ai_router
    import database
    import tools
    from agent import ResourceAgent
    from config import get_settings, is_mock_mode

    database.init_db()
    agent = ResourceAgent()

    if is_mock_mode():
        print("ReSource AI - mode: OFFLINE demo (no cloud AI calls)")
    else:
        settings = get_settings()
        models = {"groq": settings.groq_model, "gemini": settings.gemini_model,
                  "openrouter": settings.openrouter_model}
        chain = " -> ".join(f"{p} ({models[p]})" for p in ai_router.configured_providers())
        print("ReSource AI - mode: cloud AI, provider order:", chain)

    if args.prompt:
        _print_result(agent.run(" ".join(args.prompt)))
        return

    print("Describe a resource.", HELP, "\n")
    while True:
        try:
            text = input("You> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if not text:
            continue
        cmd = text.split()[0].lower()

        if cmd == "/exit":
            break
        if cmd == "/reset":
            agent.reset()
            print("Session memory cleared.\n")
        elif cmd == "/records":
            for r in database.list_resources(10):
                print(f"  #{r['id']} {r['name']} [{r['category']}/{r['condition']}] {r['status']}")
            print(" ", database.impact_summary(), "\n")
        elif cmd == "/exchanges":
            _show_exchanges(database)
        elif cmd == "/approve":
            eid = _parse_id(text)
            if eid and _ask_yes(f"Has the organisation accepted exchange #{eid}?"):
                _print_outcome(tools.confirm_exchange_approval(eid, True))
            elif eid:
                print("  Cancelled. Nothing changed.\n")
        elif cmd == "/complete":
            eid = _parse_id(text)
            if eid and _ask_yes(f"Did the physical hand-over for exchange #{eid} really happen?"):
                _print_outcome(tools.confirm_exchange_completion(eid, True))
            elif eid:
                print("  Cancelled. Nothing changed.\n")
        elif cmd == "/cancel":
            eid = _parse_id(text)
            if eid:
                _print_outcome(tools.cancel_exchange(eid))
        elif cmd.startswith("/"):
            print(" ", HELP, "\n")
        else:
            _print_result(agent.run(text))


if __name__ == "__main__":
    main()