"""Human approval step for a payment. Not reachable by any agent.

Agents prepare payments; this script is how a person approves one. It is the
only path to record_payment, which is filtered out of every agent's toolset.

    .venv/bin/python backend/approve_payment.py --kind rent --ref 1 --approved-by "Your Name"

It shows the draft, asks for typed confirmation, and only then writes. The
amount always comes from the invoice or lease row — approving means approving
that obligation, not a number passed on the command line.
"""

from __future__ import annotations

import argparse
import asyncio
import json
from datetime import datetime, timezone

from fastmcp import Client
from fastmcp.client.transports import StdioTransport

import settings
from audit import AuditTrail
from models import AgentName


async def main() -> None:
    ap = argparse.ArgumentParser(description="Approve and execute one payment (human only)")
    ap.add_argument("--kind", required=True, choices=["invoice", "rent"])
    ap.add_argument("--ref", required=True, type=int, help="invoice id, or lease id")
    ap.add_argument("--approved-by", required=True, help="your name — not an agent's")
    ap.add_argument("--yes", action="store_true", help="skip the typed confirmation")
    args = ap.parse_args()

    transport = StdioTransport(
        command=str(settings.VENV_PYTHON), args=[str(settings.SERVER_PATH)]
    )
    async with Client(transport) as client:
        draft = (
            await client.call_tool(
                "prepare_payment", {"kind": args.kind, "ref_id": args.ref}
            )
        ).data
        print("\nDRAFT PAYMENT")
        print(json.dumps(draft, indent=2))

        if not draft.get("drafted"):
            raise SystemExit("\nNothing to approve.")

        if not args.yes:
            print(
                f"\nThis pays {draft['payee']} ${draft['amount']:,.2f} and leaves "
                f"${draft['balance_after_if_paid']:,.2f} in checking."
            )
            if input('Type "approve" to confirm: ').strip().lower() != "approve":
                raise SystemExit("Not approved. Nothing was written.")

        result = (
            await client.call_tool(
                "record_payment",
                {
                    "kind": args.kind,
                    "ref_id": args.ref,
                    "human_approved": True,
                    "approved_by": args.approved_by,
                },
            )
        ).data

    print("\nRESULT")
    print(json.dumps(result, indent=2))

    # The approval is part of the audit story, so it joins the same trail.
    run_id = f"approval-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}"
    audit = AuditTrail(settings.AUDIT_PATH, run_id, model="none (human approval, no model called)")
    audit.record(
        AgentName.ACCOUNTING,
        "tool_call" if result.get("paid") else "refusal",
        asked_by="human",
        tool_name="record_payment",
        tool_args={
            "kind": args.kind,
            "ref_id": args.ref,
            "human_approved": True,
            "approved_by": args.approved_by,
        },
        tool_result=result,
        note=f"Human approval step run by {args.approved_by}. No agent can reach this tool.",
    )
    audit.finish(notes=f"Human payment approval: paid={result.get('paid')}")
    print(f"\nappended to {settings.AUDIT_PATH.relative_to(settings.HW5)}")


if __name__ == "__main__":
    asyncio.run(main())
