"""Run the Campus Customs agent team over the open tickets.

    .venv/bin/python backend/run_team.py            # all open tickets
    .venv/bin/python backend/run_team.py 101 103    # selected tickets

The Boss reads each ticket, delegates to one specialist, and decides. Every
step appends to output/audit_trail.json; earlier runs are preserved.

No payment is made here. Agents do not hold record_payment — when a payment is
the right answer they prepare it and the decision stops, waiting for a person.
Use backend/approve_payment.py to approve one.
"""

from __future__ import annotations

import asyncio
import json
import sys
import time
import uuid
from datetime import datetime, timezone

from fastmcp import Client
from fastmcp.client.transports import StdioTransport

import settings
from agents import TeamDeps, boss
from audit import AuditTrail
from models import AgentName, BossDecision

BRIEF = (
    "Ticket {tid} is open. Read it with get_ticket, delegate it to the one "
    "specialist best suited, and give your final decision. Keep it brief."
)


async def open_ticket_ids() -> list[int]:
    """Ask the MCP server which tickets are open, rather than hard-coding them."""
    transport = StdioTransport(
        command=str(settings.VENV_PYTHON), args=[str(settings.SERVER_PATH)]
    )
    async with Client(transport) as client:
        result = await client.call_tool("list_open_tickets", {})
    return [t["id"] for t in result.data["tickets"]]


async def handle_ticket(ticket_id: int, audit: AuditTrail) -> BossDecision:
    deps = TeamDeps(audit=audit, ticket_id=ticket_id, call_stack=[AgentName.BOSS])
    started = time.perf_counter()

    result = await boss.run(
        BRIEF.format(tid=ticket_id),
        deps=deps,
        usage_limits=settings.AGENT_USAGE_LIMITS,
    )

    usage = result.usage
    audit.record(
        AgentName.BOSS,
        "agent_run",
        ticket_id=ticket_id,
        asked_by="human",
        prompt=BRIEF.format(tid=ticket_id),
        output=result.output.model_dump(mode="json"),
        model=settings.MODEL_NAME,
        input_tokens=getattr(usage, "input_tokens", None),
        output_tokens=getattr(usage, "output_tokens", None),
        duration_ms=int((time.perf_counter() - started) * 1000),
    )
    audit.run.decisions.append(result.output)
    audit.run.tickets_handled.append(ticket_id)
    audit.run.total_input_tokens += getattr(usage, "input_tokens", 0) or 0
    audit.run.total_output_tokens += getattr(usage, "output_tokens", 0) or 0
    return result.output


async def main() -> None:
    wanted = [int(a) for a in sys.argv[1:]] or None

    run_id = f"run-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}-{uuid.uuid4().hex[:6]}"
    audit = AuditTrail(settings.AUDIT_PATH, run_id, settings.MODEL_NAME)

    print(f"run      : {run_id}")
    print(f"model    : {settings.MODEL_NAME} (every agent)")
    print(f"database : {settings.DB_PATH.name} via MCP")
    print()

    if wanted is None:
        wanted = await open_ticket_ids()
        print(f"open tickets: {wanted}\n")

    async with boss:  # opens the shared MCP connection for all five agents
        for tid in wanted:
            print(f"--- ticket {tid} ---")
            decision = await handle_ticket(tid, audit)
            print(f"  assigned to      : {decision.assigned_to.value}")
            print(f"  instruction      : {decision.instruction_given[:110]}")
            print(f"  decision         : {decision.decision[:160]}")
            if decision.needs_human_approval:
                print(f"  AWAITING HUMAN   : {decision.awaiting_human}")
            print()

    # Nothing in this run may have paid anything: agents do not hold that tool.
    paid = [
        s for s in audit.run.steps
        if s.event == "tool_call" and s.tool_name == "record_payment"
    ]
    audit.run.payments_made = len(paid)

    models_used = {s.model for s in audit.run.steps if s.model}
    run = audit.finish(
        notes=(
            f"Models used: {sorted(models_used)}. "
            f"Payments executed by agents: {len(paid)} (must be 0 — only humans pay)."
        )
    )

    print("=" * 62)
    print(f"steps recorded   : {len(run.steps)}")
    print(f"tool calls       : {sum(1 for s in run.steps if s.event == 'tool_call')}")
    print(f"delegations      : {sum(1 for s in run.steps if s.event == 'delegation')}")
    print(f"refusals         : {sum(1 for s in run.steps if s.event == 'refusal')}")
    print(f"tokens in/out    : {run.total_input_tokens} / {run.total_output_tokens}")
    print(f"models used      : {sorted(models_used)}")
    print(f"payments by agent: {len(paid)}  (must be 0)")
    print(f"appended to      : {settings.AUDIT_PATH.relative_to(settings.HW5)}")

    if models_used - {settings.MODEL_NAME}:
        raise SystemExit(f"FAIL: a model other than {settings.MODEL_NAME} was used.")
    if paid:
        raise SystemExit("FAIL: an agent executed a payment. Only humans may approve.")


if __name__ == "__main__":
    asyncio.run(main())
