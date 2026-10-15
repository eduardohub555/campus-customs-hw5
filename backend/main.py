"""FastAPI backend for the Campus Customs dashboard.

Start it from this folder:

    uvicorn main:app --reload --port 8000

Routes exist so the React dashboard can read the ticket board, run the agent
team, watch what the agents are doing, see the cash, approve a payment, and
reset to a clean slate between demos.

Two rules shape the whole file:

1. **Only a human moves money.** Agents prepare payments; they do not hold
   record_payment. POST /approvals is the human click, and it is the only route
   in this API that changes cash. It requires an explicit approver name and an
   explicit confirmation flag, and the MCP tool rejects agent names on top.
2. **Shop facts come from MCP.** The API reads the database directly for two
   narrow things only — the ticket board and the cash balance, which are plain
   reads for the UI — and everything an agent asserts still goes through the
   MCP server, so the audit trail stays the record of record.
"""

from __future__ import annotations

import asyncio
import json
import shutil
import sqlite3
import time
import uuid
from datetime import datetime, timezone
from typing import Any, Literal

from fastapi import FastAPI, HTTPException
from pydantic_ai.exceptions import UsageLimitExceeded
from fastapi.middleware.cors import CORSMiddleware
from fastmcp import Client
from fastmcp.client.transports import StdioTransport
from pydantic import BaseModel, Field

import expectations
import settings
from agents import TeamDeps, boss
from audit import AuditTrail
from models import AgentName

app = FastAPI(
    title="Campus Customs back office",
    version="1.0",
    description="Ticket board, agent runs, cash, and the human approval step.",
)

# The dashboard runs on a different port in development.
# Vite picks the first free port from 5173 upward, and this machine already has
# other dev servers on 5173/5174 — so match any localhost port rather than
# pinning one and breaking when the board lands somewhere else.
app.add_middleware(
    CORSMiddleware,
    allow_origin_regex=r"http://(localhost|127\.0\.0\.1):\d+",
    allow_methods=["*"],
    allow_headers=["*"],
)

PRISTINE_DB = settings.HW5 / "data" / "campus_customs.db"

# One ticket at a time: two concurrent runs on the same ticket would interleave
# in the audit trail and double-spend the token budget for no benefit.
_running: set[int] = set()
_run_lock = asyncio.Lock()


# --------------------------------------------------------------------------
# helpers
# --------------------------------------------------------------------------


def _db(readonly: bool = True) -> sqlite3.Connection:
    mode = "ro" if readonly else "rw"
    conn = sqlite3.connect(f"file:{settings.DB_PATH}?mode={mode}", uri=True)
    conn.row_factory = sqlite3.Row
    return conn


async def _mcp(tool: str, args: dict[str, Any]) -> Any:
    """Call one MCP tool. Used by the approval route, which must not bypass MCP."""
    transport = StdioTransport(
        command=str(settings.VENV_PYTHON), args=[str(settings.SERVER_PATH)]
    )
    async with Client(transport) as client:
        return (await client.call_tool(tool, args)).data


def _read_trail() -> dict[str, Any]:
    if not settings.AUDIT_PATH.exists():
        return {"audit_trail": {"runs": []}}
    try:
        return json.loads(settings.AUDIT_PATH.read_text())
    except json.JSONDecodeError:
        return {"audit_trail": {"runs": []}}


# --------------------------------------------------------------------------
# models
# --------------------------------------------------------------------------


class Ticket(BaseModel):
    id: int
    type: str
    requester: str
    subject: str
    status: Literal["open", "resolved"]
    is_open: bool
    notes: str | None = None
    sku: str | None = None
    size: str | None = None
    qty: int | None = None
    lease_id: int | None = None
    invoice_id: int | None = None
    created_at: str


class ApprovalRequest(BaseModel):
    """A human clicking approve. Agents cannot produce one of these."""

    kind: Literal["invoice", "rent", "purchase_order"]
    ref_id: int = Field(description="invoice id, lease id, or vendor id for a purchase order")
    approved_by: str = Field(min_length=2, description="The approving person's name — never an agent's")
    confirm: bool = Field(description="Must be true. The explicit click.")
    ticket_id: int | None = None
    # Purchase orders only; ignored for payments, whose amount comes from the row.
    sku: str | None = None
    size: str | None = None
    qty: int | None = None


# --------------------------------------------------------------------------
# routes
# --------------------------------------------------------------------------


@app.get("/health", summary="Liveness check for the dashboard")
def health() -> dict[str, Any]:
    with _db() as conn:
        today = conn.execute("SELECT date_today FROM desk;").fetchone()["date_today"]
    return {
        "ok": True,
        "model": settings.MODEL_NAME,
        "database": settings.DB_PATH.name,
        "shop_date": today,
    }


@app.get("/tickets", response_model=list[Ticket], summary="All tickets with open/resolved status")
def list_tickets() -> list[Ticket]:
    with _db() as conn:
        rows = conn.execute(
            "SELECT id, type, requester, subject, sku, size, qty, lease_id, "
            "invoice_id, status, notes, created_at FROM tickets ORDER BY id;"
        ).fetchall()
    return [
        Ticket(
            **{k: r[k] for k in r.keys() if k != "status"},
            status="open" if r["status"] == "open" else "resolved",
            is_open=r["status"] == "open",
        )
        for r in rows
    ]


@app.get("/tickets/{ticket_id}", response_model=Ticket, summary="One ticket")
def get_ticket(ticket_id: int) -> Ticket:
    for t in list_tickets():
        if t.id == ticket_id:
            return t
    raise HTTPException(404, f"No ticket {ticket_id}.")


@app.post("/tickets/{ticket_id}/run", summary="Run the agent team on one ticket")
async def run_ticket(ticket_id: int) -> dict[str, Any]:
    """Run the team, then score the run against the Problem 6 plan.

    The Boss's brief carries the routing rule — one specialist, a second only if
    the first cannot finish, never every specialist — and the response reports
    whether the run actually obeyed it.
    """
    with _db() as conn:
        row = conn.execute("SELECT status FROM tickets WHERE id = ?;", (ticket_id,)).fetchone()
    if row is None:
        raise HTTPException(404, f"No ticket {ticket_id}.")

    async with _run_lock:
        if ticket_id in _running:
            raise HTTPException(409, f"Ticket {ticket_id} is already running.")
        _running.add(ticket_id)

    try:
        run_id = f"api-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}-{uuid.uuid4().hex[:6]}"
        audit = AuditTrail(settings.AUDIT_PATH, run_id, settings.MODEL_NAME)
        deps = TeamDeps(audit=audit, ticket_id=ticket_id, call_stack=[AgentName.BOSS])
        brief = expectations.brief_for(ticket_id)

        started = time.perf_counter()
        try:
            async with boss:
                result = await boss.run(
                    brief, deps=deps, usage_limits=settings.AGENT_USAGE_LIMITS
                )
        except UsageLimitExceeded as exc:
            # Record the stop rather than losing the partial chain silently.
            audit.record(
                AgentName.BOSS,
                "refusal",
                ticket_id=ticket_id,
                note=f"Usage ceiling reached before finishing: {exc}",
            )
            audit.finish(notes=f"API run for ticket {ticket_id} halted on usage limits.")
            raise HTTPException(
                429,
                f"Ticket {ticket_id} hit the usage ceiling before finishing: {exc}. "
                "Partial steps are in the audit trail.",
            ) from exc
        elapsed = int((time.perf_counter() - started) * 1000)

        usage = result.usage
        audit.record(
            AgentName.BOSS,
            "agent_run",
            ticket_id=ticket_id,
            asked_by="human",
            prompt=brief,
            output=result.output.model_dump(mode="json"),
            model=settings.MODEL_NAME,
            input_tokens=getattr(usage, "input_tokens", None),
            output_tokens=getattr(usage, "output_tokens", None),
            duration_ms=elapsed,
        )
        audit.run.decisions.append(result.output)
        audit.run.tickets_handled.append(ticket_id)
        audit.run.total_input_tokens += getattr(usage, "input_tokens", 0) or 0
        audit.run.total_output_tokens += getattr(usage, "output_tokens", 0) or 0

        steps = audit.run.steps
        # Order by when each agent was *asked*, not when it finished. A nested
        # delegate (Accounting inside Inventory) completes first, so ordering by
        # agent_run would report the chain backwards.
        agents_used = [
            s.note.split(" -> ")[-1]
            for s in steps
            if s.event == "delegation" and s.note and " -> " in s.note
        ]
        for s in steps:  # anything that ran without a recorded delegation
            if s.event == "agent_run" and s.agent.value not in agents_used:
                agents_used.append(s.agent.value)
        tools_used = [s.tool_name for s in steps if s.event == "tool_call" and s.tool_name]
        paid_by_agent = [s for s in steps if s.tool_name == "record_payment"]
        audit.run.payments_made = len(paid_by_agent)

        scorecard = expectations.compare(ticket_id, agents_used, tools_used)

        # The run finished, so the ticket is closed on the board. Done here
        # rather than by an agent: closing your own ticket is a self-assessment.
        resolved = await _mcp(
            "mark_ticket_resolved",
            {
                "ticket_id": ticket_id,
                "resolved_by": "agent board",
                "summary": result.output.decision[:160],
            },
        )
        audit.finish(notes=f"API run for ticket {ticket_id}. Routing match: {scorecard}")

        if paid_by_agent:  # defence in depth; agents do not hold the tool
            raise HTTPException(500, "An agent executed a payment. Run halted.")

        return {
            "run_id": run_id,
            "ticket_id": ticket_id,
            "model": settings.MODEL_NAME,
            "decision": result.output.model_dump(mode="json"),
            "agents_involved": list(dict.fromkeys(agents_used)),
            "tools_called": tools_used,
            "delegations": [s.note for s in steps if s.event == "delegation"],
            "refusals": [s.note for s in steps if s.event == "refusal"],
            "vs_expected": scorecard,
            "agent_summaries": [
                {
                    "agent": st.agent.value,
                    "says": (st.output or {}).get("summary") or (st.output or {}).get("decision"),
                    "action": (st.output or {}).get("recommended_action"),
                    "draft": (st.output or {}).get("draft_message"),
                    "needs_human_approval": (st.output or {}).get("needs_human_approval"),
                    "tools": [
                        t.tool_name for t in steps
                        if t.event == "tool_call" and t.agent == st.agent
                    ],
                }
                for st in steps if st.event == "agent_run"
            ],
            "needs_human_approval": result.output.needs_human_approval,
            "awaiting_human": result.output.awaiting_human,
            "payments_made_by_agents": 0,
            "resolved": bool(resolved.get("resolved")),
            "duration_ms": elapsed,
            "tokens": {
                "input": audit.run.total_input_tokens,
                "output": audit.run.total_output_tokens,
            },
        }
    finally:
        _running.discard(ticket_id)


@app.get("/events", summary="Recent agent events for the board to poll")
def events(limit: int = 40, ticket_id: int | None = None) -> dict[str, Any]:
    """What each agent said and which tools it actually used, newest first.

    Read from the audit trail, so the board shows the recorded tool arguments
    and results rather than an agent's account of them.
    """
    runs = _read_trail()["audit_trail"].get("runs", [])
    out: list[dict[str, Any]] = []

    for run in runs:
        for step in run.get("steps", []):
            if ticket_id is not None and step.get("ticket_id") != ticket_id:
                continue
            item = {
                "run_id": run.get("run_id"),
                "step": step.get("step"),
                "at": step.get("at"),
                "agent": step.get("agent"),
                "event": step.get("event"),
                "ticket_id": step.get("ticket_id"),
                "asked_by": step.get("asked_by"),
                "note": step.get("note"),
            }
            if step.get("event") == "tool_call":
                item |= {
                    "tool_name": step.get("tool_name"),
                    "tool_args": step.get("tool_args"),
                    "tool_result": step.get("tool_result"),
                }
            elif step.get("event") == "agent_run":
                output = step.get("output") or {}
                item |= {
                    "says": output.get("summary") or output.get("decision"),
                    "recommended_action": output.get("recommended_action"),
                    "draft_message": output.get("draft_message"),
                    "needs_human_approval": output.get("needs_human_approval"),
                    "input_tokens": step.get("input_tokens"),
                    "output_tokens": step.get("output_tokens"),
                }
            elif step.get("event") == "delegation":
                item["prompt"] = step.get("prompt")
            out.append(item)

    out.sort(key=lambda e: (e.get("at") or "", e.get("step") or 0), reverse=True)
    return {"count": len(out[:limit]), "total_available": len(out), "events": out[:limit]}


@app.get("/cash", summary="Current checking balance")
def cash() -> dict[str, Any]:
    with _db() as conn:
        acct = conn.execute(
            "SELECT name, balance, date FROM cash_accounts WHERE name = 'checking';"
        ).fetchone()
        payments = conn.execute(
            "SELECT id, kind, ref_id, amount, paid_at, approved_by FROM payments "
            "ORDER BY id DESC;"
        ).fetchall()
        owed = conn.execute(
            "SELECT COALESCE(SUM(amount), 0) AS t FROM invoices WHERE status = 'open';"
        ).fetchone()["t"]
        rent = conn.execute("SELECT COALESCE(SUM(monthly_rent), 0) AS t FROM leases;").fetchone()["t"]
        today = conn.execute("SELECT date_today FROM desk;").fetchone()["date_today"]

        # Each thing a human could be asked to pay, with whether it is already
        # settled. Without this the board prices an approval from a running
        # total that moves once something is paid, and keeps offering to pay a
        # bill that is already cleared.
        settled = {(p["kind"], p["ref_id"]) for p in payments}
        invoices = conn.execute(
            "SELECT i.id, i.amount, i.status, v.name AS payee FROM invoices i "
            "JOIN vendors v ON v.id = i.vendor_id ORDER BY i.id;"
        ).fetchall()
        leases = conn.execute(
            "SELECT id, space_name, landlord, monthly_rent FROM leases ORDER BY id;"
        ).fetchall()

        obligations = [
            {
                "kind": "invoice",
                "ref_id": i["id"],
                "label": f"invoice {i['id']} to {i['payee']}",
                "payee": i["payee"],
                "amount": round(i["amount"], 2),
                "paid": i["status"] == "paid" or ("invoice", i["id"]) in settled,
            }
            for i in invoices
        ] + [
            {
                "kind": "rent",
                "ref_id": l["id"],
                "label": f"rent on the {l['space_name']}",
                "payee": l["landlord"],
                "amount": round(l["monthly_rent"], 2),
                "paid": ("rent", l["id"]) in settled,
            }
            for l in leases
        ]

        outstanding = round(sum(o["amount"] for o in obligations if not o["paid"]), 2)

    if acct is None:
        raise HTTPException(500, "No checking account row.")
    return {
        "account": acct["name"],
        "balance": round(acct["balance"], 2),
        "as_of": today,
        "open_invoice_total": round(owed, 2),
        "rent_total": round(rent, 2),
        # Only what is still owed. Rent already paid for this period is not a
        # claim on the balance, so counting it again produced a negative figure.
        "outstanding_total": outstanding,
        "remaining_if_all_paid": round(acct["balance"] - outstanding, 2),
        "obligations": obligations,
        "payments": [dict(p) for p in payments],
        "payment_count": len(payments),
    }


@app.post("/approvals", summary="Human approves a payment or purchase — the only route that moves cash")
async def approve(req: ApprovalRequest) -> dict[str, Any]:
    """The human click. No agent can reach this.

    For a payment, it calls record_payment through MCP, which writes the
    payments row and decrements cash in one transaction. The amount is read
    from the invoice or lease row, so approving means approving that
    obligation, never a figure passed in from the browser.
    """
    if not req.confirm:
        raise HTTPException(400, "confirm must be true. A payment needs an explicit human click.")

    if req.kind == "purchase_order":
        # Honest limitation: the schema has no purchase_orders table, so an
        # approved PO is recorded in the audit trail and nothing else. No cash
        # moves until the vendor invoices us, which is correct accounting.
        if not all([req.sku, req.size, req.qty]):
            raise HTTPException(400, "A purchase order needs sku, size and qty.")
        draft = await _mcp(
            "prepare_purchase_order",
            {"sku": req.sku, "size": req.size, "qty": req.qty, "vendor_id": req.ref_id},
        )
        if not draft.get("drafted"):
            raise HTTPException(400, draft.get("reason", "Could not draft the purchase order."))

        audit = AuditTrail(
            settings.AUDIT_PATH,
            f"approval-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}",
            model="none (human approval, no model called)",
        )
        audit.record(
            AgentName.ACCOUNTING,
            "approval",
            ticket_id=req.ticket_id,
            asked_by="human",
            tool_name="prepare_purchase_order",
            tool_args={"sku": req.sku, "size": req.size, "qty": req.qty, "vendor_id": req.ref_id},
            tool_result=draft,
            note=f"Purchase order approved by {req.approved_by}.",
        )
        audit.finish(notes=f"Human approved purchase order: {req.sku} x{req.qty}")
        return {
            "approved": True,
            "kind": "purchase_order",
            "approved_by": req.approved_by,
            "order": draft,
            "cash_changed": False,
            "note": (
                "Recorded in the audit trail. This database has no purchase_orders "
                "table, so nothing else was written — and no cash moves until the "
                "vendor invoices for it."
            ),
        }

    result = await _mcp(
        "record_payment",
        {
            "kind": req.kind,
            "ref_id": req.ref_id,
            "human_approved": True,
            "approved_by": req.approved_by,
        },
    )

    audit = AuditTrail(
        settings.AUDIT_PATH,
        f"approval-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}",
        model="none (human approval, no model called)",
    )
    audit.record(
        AgentName.ACCOUNTING,
        "approval" if result.get("paid") else "refusal",
        ticket_id=req.ticket_id,
        asked_by="human",
        tool_name="record_payment",
        tool_args={"kind": req.kind, "ref_id": req.ref_id, "approved_by": req.approved_by},
        tool_result=result,
        note=f"Human approval by {req.approved_by}. No agent can reach this tool.",
    )
    audit.finish(notes=f"Human payment approval: paid={result.get('paid')}")

    if not result.get("paid"):
        raise HTTPException(400, result.get("refused", "Payment refused."))

    return {"approved": True, "cash_changed": True, **result}


@app.post("/reset", summary="Restore the database to its original values")
def reset() -> dict[str, Any]:
    """Copy the pristine database over the working copy, for a fresh run.

    The audit trail is deliberately **not** touched: it is append-only, and
    wiping the record of what happened before a reset would defeat its purpose.
    The reset itself is appended to it instead.
    """
    if not PRISTINE_DB.exists():
        raise HTTPException(500, f"Original database missing at {PRISTINE_DB}.")

    with _db() as conn:
        before = {
            "balance": conn.execute(
                "SELECT balance FROM cash_accounts WHERE name='checking';"
            ).fetchone()["balance"],
            "payments": conn.execute("SELECT COUNT(*) AS c FROM payments;").fetchone()["c"],
            "open_tickets": conn.execute(
                "SELECT COUNT(*) AS c FROM tickets WHERE status='open';"
            ).fetchone()["c"],
        }

    shutil.copy2(PRISTINE_DB, settings.DB_PATH)

    with _db() as conn:
        after = {
            "balance": conn.execute(
                "SELECT balance FROM cash_accounts WHERE name='checking';"
            ).fetchone()["balance"],
            "payments": conn.execute("SELECT COUNT(*) AS c FROM payments;").fetchone()["c"],
            "open_tickets": conn.execute(
                "SELECT COUNT(*) AS c FROM tickets WHERE status='open';"
            ).fetchone()["c"],
        }

    audit = AuditTrail(
        settings.AUDIT_PATH,
        f"reset-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}",
        model="none (database reset, no model called)",
    )
    audit.record(
        AgentName.BOSS,
        "reset",
        asked_by="human",
        note=f"Database restored from {PRISTINE_DB.name}. Before: {before}. After: {after}.",
    )
    audit.finish(notes="Database reset to original values. Audit trail preserved.")

    return {
        "reset": True,
        "restored_from": PRISTINE_DB.name,
        "before": before,
        "after": after,
        "audit_trail": "preserved — append-only, not wiped by reset",
    }


@app.post("/runs/all", summary="Reset to original values, then run the team on every open ticket")
async def run_all(reset_first: bool = True) -> dict[str, Any]:
    """A full run of the shop's queue, from a clean slate.

    Shop rule: a full run starts from the original database, so the tickets are
    resolved against the same starting cash, stock and invoices every time and
    one run cannot inherit another's state. Pass reset_first=false only when
    deliberately continuing from where the last run left off.
    """
    reset_result = reset() if reset_first else None

    with _db() as conn:
        ids = [
            r["id"]
            for r in conn.execute(
                "SELECT id FROM tickets WHERE status = 'open' ORDER BY created_at;"
            )
        ]

    runs = []
    for tid in ids:
        runs.append(await run_ticket(tid))

    cash_now = cash()
    return {
        "reset_first": reset_first,
        "reset": reset_result,
        "tickets_run": ids,
        "runs": runs,
        "cash": {
            "balance": cash_now["balance"],
            "payments_made": cash_now["payment_count"],
            "note": "Unchanged by agents — only POST /approvals moves cash.",
        },
        "routing_summary": [
            {
                "ticket": r["ticket_id"],
                "agents": r["agents_involved"],
                "first_matched": r["vs_expected"].get("first_matched"),
                "no_forbidden_agents": r["vs_expected"].get("no_forbidden_agents"),
                "no_forbidden_tools": r["vs_expected"].get("no_forbidden_tools"),
            }
            for r in runs
        ],
        "awaiting_human": [
            {"ticket": r["ticket_id"], "what": r["awaiting_human"]}
            for r in runs
            if r["needs_human_approval"]
        ],
        "total_tokens": {
            "input": sum(r["tokens"]["input"] for r in runs),
            "output": sum(r["tokens"]["output"] for r in runs),
        },
    }


@app.get("/shop-rules", summary="The shop rules this backend enforces")
def shop_rules() -> dict[str, Any]:
    """Stated so the dashboard can show them, and so they are testable."""
    with _db() as conn:
        today = conn.execute("SELECT date_today FROM desk;").fetchone()["date_today"]
        blocked = conn.execute(
            "SELECT v.id, v.name, v.lead_days, COUNT(i.id) AS open_invoices, "
            "COALESCE(SUM(i.amount), 0) AS owed FROM vendors v "
            "LEFT JOIN invoices i ON i.vendor_id = v.id AND i.status = 'open' "
            "GROUP BY v.id ORDER BY v.id;"
        ).fetchall()
    return {
        "today_comes_from": {"source": "desk.date_today", "value": today},
        "lead_times_come_from": "vendors.lead_days",
        "vendor_shipping": [
            {
                "vendor": b["name"],
                "lead_days": b["lead_days"],
                "can_ship": b["open_invoices"] == 0,
                "blocked_by_unpaid": round(b["owed"], 2) if b["open_invoices"] else 0,
            }
            for b in blocked
        ],
        "cash_direction": "out only — no revenue is modelled, so the balance never rises",
        "overdraft": "refused — record_payment rejects a payment larger than the balance",
        "payments": "every payment needs a human; agents do not hold record_payment",
        "outbound": "nothing is sent — no email, no vendor contact; drafts stay on the board",
        "full_runs": "POST /runs/all resets to the original database first by default",
    }
