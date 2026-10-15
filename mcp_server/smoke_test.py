"""Problem 4 smoke test — exercise every tool over a real MCP session.

Spawns server.py as a subprocess and talks to it with an MCP client, so this
tests the tools the way an agent reaches them (protocol round trip), not by
importing the Python functions directly.

Every value the tools return is re-checked against data/campus_customs_new.db
with independent SQL. A test passes only if the two agree.

Writes output/mcp_smoke.json.

    .venv/bin/python mcp_server/smoke_test.py
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastmcp import Client
from fastmcp.client.transports import StdioTransport

HERE = Path(__file__).resolve().parent
HW5 = HERE.parent
DB = HW5 / "data" / "campus_customs_new.db"
OUT = HW5 / "output" / "mcp_smoke.json"
PY = HW5 / ".venv" / "bin" / "python"


def q(sql: str, args: tuple = ()) -> Any:
    """Independent read straight from the database file."""
    conn = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    try:
        row = conn.execute(sql, args).fetchone()
        return row[0] if row and len(row) == 1 else row
    finally:
        conn.close()


def md5(path: Path) -> str:
    return hashlib.md5(path.read_bytes()).hexdigest()


# Each case: the prompt a user would type, the tool it should reach for, the
# arguments, and the database checks the output must satisfy.
#
# Exactly one tool per ticket, and exactly one ticket per tool. The three open
# tickets each ask a different question, so the mapping is 1:1 and the test
# asserts it below.
CASES = [
    {
        "ticket": 101,
        "ticket_type": "customer_order",
        "prompt": "Ticket 101: Tauhid Zaman wants a Classic Bulldog Tee in size S. Can we ship it today?",
        "tool": "check_stock",
        "args": {"sku": "CC-TEE-WHITE", "size": "S", "qty_needed": 1},
        "checks": lambda o: [
            ("qty_on_hand", o["qty_on_hand"],
             q("SELECT qty FROM inventory WHERE sku='CC-TEE-WHITE' AND size='S';")),
            ("name", o["name"],
             q("SELECT name FROM inventory WHERE sku='CC-TEE-WHITE' AND size='S';")),
            ("location", o["location"],
             q("SELECT location FROM inventory WHERE sku='CC-TEE-WHITE' AND size='S';")),
            ("can_fill", o["can_fill"],
             q("SELECT qty >= 1 FROM inventory WHERE sku='CC-TEE-WHITE' AND size='S';") == 1),
            ("shortfall", o["shortfall"],
             max(0, 1 - q("SELECT qty FROM inventory WHERE sku='CC-TEE-WHITE' AND size='S';"))),
        ],
    },
    {
        "ticket": 102,
        "ticket_type": "rent_notice",
        "prompt": "Ticket 102: we got an email from Elm City Properties saying the shop rent is due. "
                  "How much do we actually owe on lease 1, and when is it due?",
        "tool": "get_lease_payment",
        "args": {"lease_id": 1},
        "checks": lambda o: [
            ("amount_due", o["amount_due"], q("SELECT monthly_rent FROM leases WHERE id=1;")),
            ("next_due", o["next_due"], q("SELECT next_due FROM leases WHERE id=1;")),
            ("landlord", o["landlord"], q("SELECT landlord FROM leases WHERE id=1;")),
            ("space_name", o["space_name"], q("SELECT space_name FROM leases WHERE id=1;")),
            ("as_of (desk date, not system clock)", o["as_of"],
             q("SELECT date_today FROM desk;")),
            ("days_until_due", o["days_until_due"],
             q("SELECT CAST(julianday((SELECT next_due FROM leases WHERE id=1)) "
               "- julianday((SELECT date_today FROM desk)) AS INTEGER);")),
            ("is_overdue", o["is_overdue"], False),
        ],
    },
    {
        "ticket": 103,
        "ticket_type": "price_override",
        "prompt": "Ticket 103: the Yale AI Club wants 20 navy hoodies in size M and is asking for a "
                  "bulk discount. What is our cost and list price, and how much margin is on that order?",
        "tool": "get_price_and_margin",
        "args": {"sku": "CC-HOOD-NAVY", "qty": 20},
        "checks": lambda o: [
            ("unit_cost", o["unit_cost"], q("SELECT unit_cost FROM pricing WHERE sku='CC-HOOD-NAVY';")),
            ("list_price", o["list_price"], q("SELECT list_price FROM pricing WHERE sku='CC-HOOD-NAVY';")),
            ("unit_margin", o["unit_margin"],
             round(q("SELECT list_price - unit_cost FROM pricing WHERE sku='CC-HOOD-NAVY';"), 2)),
            ("order_total_at_list", o["order_total_at_list"],
             round(q("SELECT list_price FROM pricing WHERE sku='CC-HOOD-NAVY';") * 20, 2)),
            ("order_total_at_cost", o["order_total_at_cost"],
             round(q("SELECT unit_cost FROM pricing WHERE sku='CC-HOOD-NAVY';") * 20, 2)),
            ("name", o["name"], q("SELECT name FROM inventory WHERE sku='CC-HOOD-NAVY' LIMIT 1;")),
            ("discount_authority_in_database", o["discount_authority_in_database"],
             # No approval/policy table exists anywhere in the schema.
             bool(q("SELECT COUNT(*) FROM sqlite_master WHERE type='table' "
                    "AND (name LIKE '%approv%' OR name LIKE '%discount%' OR name LIKE '%polic%');"))),
        ],
    },
]

# The never-invent rule: absent rows must be flagged, not guessed.
NEGATIVE_CASES = [
    {
        "prompt": "Do we have a blue cap in size M?",
        "tool": "check_stock",
        "args": {"sku": "CC-HAT-BLUE", "size": "M"},
        "expect": "found=False, and sizes_carried lists only the sizes really in the table",
        "check": lambda o: o["found"] is False
        and o["sizes_carried"] == [r[0] for r in sqlite3.connect(
            f"file:{DB}?mode=ro", uri=True).execute(
            "SELECT size FROM inventory WHERE sku='CC-HAT-BLUE' ORDER BY size;").fetchall()],
    },
    {
        "prompt": "How many CC-FAKE-999 do we have in size M?",
        "tool": "check_stock",
        "args": {"sku": "CC-FAKE-999", "size": "M"},
        "expect": "found=False, no invented stock figure",
        "check": lambda o: o["found"] is False and "qty_on_hand" not in o,
    },
    {
        "prompt": "What is the rent on lease 99?",
        "tool": "get_lease_payment",
        "args": {"lease_id": 99},
        "expect": "found=False, no invented amount",
        "check": lambda o: o["found"] is False and "amount_due" not in o,
    },
    {
        "prompt": "What does CC-FAKE-999 cost us and what do we sell it for?",
        "tool": "get_price_and_margin",
        "args": {"sku": "CC-FAKE-999"},
        "expect": "found=False, no invented price",
        "check": lambda o: o["found"] is False and "list_price" not in o,
    },
]


async def main() -> None:
    db_md5_before = md5(DB)
    transport = StdioTransport(command=str(PY), args=[str(HERE / "server.py")])

    results: list[dict[str, Any]] = []
    negatives: list[dict[str, Any]] = []

    async with Client(transport) as client:
        listed = await client.list_tools()
        tool_names = sorted(t.name for t in listed)

        for case in CASES:
            res = await client.call_tool(case["tool"], case["args"])
            out = res.data
            checks = [
                {
                    "field": field,
                    "tool_returned": got,
                    "database_says": exp,
                    "match": got == exp,
                }
                for field, got, exp in case["checks"](out)
            ]
            results.append({
                "ticket": case["ticket"],
                "ticket_type": case["ticket_type"],
                "prompt_to_vibe_coder": case["prompt"],
                "tool_called": case["tool"],
                "arguments": case["args"],
                "tool_output": out,
                "verified_against_database": checks,
                "all_fields_match_database": all(c["match"] for c in checks),
            })

        for case in NEGATIVE_CASES:
            res = await client.call_tool(case["tool"], case["args"])
            out = res.data
            negatives.append({
                "prompt_to_vibe_coder": case["prompt"],
                "tool_called": case["tool"],
                "arguments": case["args"],
                "tool_output": out,
                "expected_behaviour": case["expect"],
                "behaved_correctly": bool(case["check"](out)),
            })

    db_md5_after = md5(DB)
    # One tool per ticket, one ticket per tool, and every tool exercised once.
    tickets_covered = sorted(r["ticket"] for r in results)
    tools_used = sorted(r["tool_called"] for r in results)
    mapping_is_one_to_one = (
        tickets_covered == [101, 102, 103]
        and tools_used == ["check_stock", "get_lease_payment", "get_price_and_margin"]
    )

    all_ok = (
        all(r["all_fields_match_database"] for r in results)
        and all(n["behaved_correctly"] for n in negatives)
        and db_md5_before == db_md5_after
        and tool_names == ["check_stock", "get_lease_payment", "get_price_and_margin"]
        and mapping_is_one_to_one
    )

    report = {
        "test_run": {
            "problem": "HW5 Problem 4 — add the MCP server to the vibe coder and test each tool",
            "run_at": datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds"),
            "mcp_server": "campus-customs",
            "registered_in": "../.mcp.json (project root)",
            "transport": "stdio (server.py spawned as a subprocess, real MCP protocol round trip)",
            "database_under_test": "data/campus_customs_new.db",
            "tools_discovered": tool_names,
            "tools_discovered_count": len(tool_names),
        },
        "ticket_tool_calls": results,
        "never_invent_checks": negatives,
        "database_integrity": {
            "md5_before": db_md5_before,
            "md5_after": db_md5_after,
            "unchanged": db_md5_before == db_md5_after,
            "note": "All three tools open the database read-only; the smoke test must not alter it.",
        },
        "tool_ticket_mapping": {
            "rule": "Each open ticket is unlocked by exactly one tool, and each tool serves exactly one ticket.",
            "mapping": {str(r["ticket"]): r["tool_called"] for r in results},
            "tickets_covered": tickets_covered,
            "tools_exercised": tools_used,
            "is_one_to_one": mapping_is_one_to_one,
        },
        "summary": {
            "ticket_calls_run": len(results),
            "ticket_calls_matching_database": sum(r["all_fields_match_database"] for r in results),
            "field_level_comparisons": sum(len(r["verified_against_database"]) for r in results),
            "never_invent_checks_run": len(negatives),
            "never_invent_checks_passed": sum(n["behaved_correctly"] for n in negatives),
            "all_passed": all_ok,
        },
    }

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(report, indent=2) + "\n")

    s = report["summary"]
    print(f"tools discovered      : {tool_names}")
    print(f"tool<->ticket mapping : {report['tool_ticket_mapping']['mapping']} (1:1 = {mapping_is_one_to_one})")
    print(f"ticket calls          : {s['ticket_calls_matching_database']}/{s['ticket_calls_run']} match database")
    print(f"field comparisons     : {s['field_level_comparisons']}")
    print(f"never-invent checks   : {s['never_invent_checks_passed']}/{s['never_invent_checks_run']} passed")
    print(f"database unchanged    : {report['database_integrity']['unchanged']}")
    print(f"ALL PASSED            : {s['all_passed']}")
    print(f"\nwrote {OUT.relative_to(HW5)}")


if __name__ == "__main__":
    asyncio.run(main())
