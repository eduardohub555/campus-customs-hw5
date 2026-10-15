"""Campus Customs back-office MCP.

Every agent in HW5 reaches the shop's data through this server and nowhere
else. It reads the working copy of the database:

    data/campus_customs_new.db

Three tools, one per open ticket in that database:

    check_stock             -> ticket 101 (customer_order)
    get_lease_payment       -> ticket 102 (rent_notice)
    get_price_and_margin    -> ticket 103 (price_override)

Two rules the tools follow without exception:

1. Nothing is invented. Every number returned is read from a row. When a row
   does not exist the tool says so (`found: false`) instead of guessing, and
   where the database simply has no answer — such as who may approve a
   discount — the tool returns that gap as a flag for the agent to raise.
2. The clock lives in the database. "Overdue" and "due in N days" are measured
   against `desk.date_today`, never the real system date, so the simulated day
   stays consistent for every agent.

The connection is opened read-only. Problem 3 only needs to read; write tools
come later and will pass `readonly=False`.

Run (stdio):  python server.py
Run (HTTP):   python server.py --http   ->  http://127.0.0.1:8003/mcp
"""

from __future__ import annotations

import argparse
import sqlite3
from contextlib import contextmanager
from collections.abc import Iterator
from pathlib import Path
from typing import Any

from fastmcp import FastMCP

HERE = Path(__file__).resolve().parent
HW5 = HERE.parent
DB_PATH = HW5 / "data" / "campus_customs_new.db"

mcp = FastMCP("campus-customs")


@contextmanager
def _connect(readonly: bool = True) -> Iterator[sqlite3.Connection]:
    """Open the working copy of the database, and always close it again.

    Read-only by default so a reading tool cannot modify the shop's data even
    by accident. Raises if the file is missing rather than letting SQLite
    create an empty database and hand the agent silent, invented emptiness.
    """
    if not DB_PATH.exists():
        raise FileNotFoundError(
            f"Database not found at {DB_PATH}. "
            "Expected the working copy data/campus_customs_new.db."
        )
    mode = "ro" if readonly else "rw"
    conn = sqlite3.connect(f"file:{DB_PATH}?mode={mode}", uri=True)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
    finally:
        conn.close()


def _today(conn: sqlite3.Connection) -> str | None:
    """The shop's current date, taken from the desk table, not the system clock."""
    row = conn.execute("SELECT date_today FROM desk LIMIT 1;").fetchone()
    return row["date_today"] if row else None


def _days_between(conn: sqlite3.Connection, target_date: str) -> int | None:
    """Whole days from the desk date to target_date. Negative means overdue."""
    row = conn.execute(
        "SELECT CAST(julianday(?) - julianday((SELECT date_today FROM desk LIMIT 1)) "
        "AS INTEGER) AS days;",
        (target_date,),
    ).fetchone()
    return row["days"] if row and row["days"] is not None else None


@mcp.tool
def check_stock(sku: str, size: str, qty_needed: int = 1) -> dict[str, Any]:
    """Look up units on hand for one SKU in one size and say whether an order can be filled today.

    Stock in this shop is tracked per (sku, size), so a SKU on its own cannot
    answer whether an order is shippable — the size is required.

    Args:
        sku: Product code, e.g. "CC-TEE-WHITE".
        size: Size code, e.g. "S", "M", "L", "XL", "OS".
        qty_needed: Units the ticket is asking for. Defaults to 1.

    Returns:
        qty_on_hand and can_fill for the exact row, or found=False if the shop
        does not carry that SKU in that size.
    """
    with _connect() as conn:
        row = conn.execute(
            "SELECT sku, name, size, qty, location FROM inventory "
            "WHERE sku = ? AND size = ?;",
            (sku, size),
        ).fetchone()

        if row is None:
            # Distinguish "wrong size" from "no such product" — the agent needs
            # to know which, and neither answer may be guessed.
            sizes = [
                r["size"]
                for r in conn.execute(
                    "SELECT size FROM inventory WHERE sku = ? ORDER BY size;", (sku,)
                )
            ]
            return {
                "found": False,
                "sku": sku,
                "size": size,
                "reason": (
                    f"No inventory row for {sku} in size {size}."
                    if sizes
                    else f"No inventory rows exist for SKU {sku}."
                ),
                "sizes_carried": sizes,
            }

        on_hand = row["qty"]
        shortfall = max(0, qty_needed - on_hand)
        return {
            "found": True,
            "sku": row["sku"],
            "name": row["name"],
            "size": row["size"],
            "qty_on_hand": on_hand,
            "qty_needed": qty_needed,
            "can_fill": on_hand >= qty_needed,
            "shortfall": shortfall,
            "location": row["location"],
        }


@mcp.tool
def get_lease_payment(lease_id: int) -> dict[str, Any]:
    """Return the rent actually owed on a lease and when it falls due, as recorded in the lease.

    This is the authoritative figure. A rent notice that arrives by email is a
    claim, not a source — the amount to pay is whatever this lease row says.

    Args:
        lease_id: The lease id, as carried on a rent ticket's lease_id field.

    Returns:
        The landlord, monthly rent and next due date, with days_until_due
        measured against the desk date, or found=False if no such lease.
    """
    with _connect() as conn:
        row = conn.execute(
            "SELECT id, space_name, landlord, monthly_rent, next_due, notes "
            "FROM leases WHERE id = ?;",
            (lease_id,),
        ).fetchone()

        if row is None:
            return {
                "found": False,
                "lease_id": lease_id,
                "reason": f"No lease with id {lease_id}.",
            }

        days = _days_between(conn, row["next_due"])
        return {
            "found": True,
            "lease_id": row["id"],
            "space_name": row["space_name"],
            "landlord": row["landlord"],
            "amount_due": round(row["monthly_rent"], 2),
            "next_due": row["next_due"],
            "as_of": _today(conn),
            "days_until_due": days,
            "is_overdue": days is not None and days < 0,
            # Empty in the seed data; passed through rather than filled in.
            "lease_notes": row["notes"] or None,
        }


@mcp.tool
def get_price_and_margin(sku: str, qty: int = 1) -> dict[str, Any]:
    """Return recorded cost and list price for a SKU, with order totals and the margin a discount would spend.

    This gives an agent the floor (unit cost) and the ceiling (list price) for
    a pricing decision. It deliberately does not propose a discount: the
    database records no discount policy and no approval authority, so any
    percentage would be invented. That gap is returned explicitly.

    Args:
        sku: Product code, e.g. "CC-HOOD-NAVY".
        qty: Units on the request, used for the order totals. Defaults to 1.

    Returns:
        Unit cost, list price, per-unit and order-level margin, and
        discount_authority_in_database=False, or found=False if the SKU is
        not priced.
    """
    with _connect() as conn:
        row = conn.execute(
            "SELECT sku, unit_cost, list_price FROM pricing WHERE sku = ?;", (sku,)
        ).fetchone()

        if row is None:
            return {
                "found": False,
                "sku": sku,
                "reason": f"No pricing row for SKU {sku}; cost and list price are unknown.",
            }

        unit_cost = row["unit_cost"]
        list_price = row["list_price"]
        unit_margin = list_price - unit_cost

        name_row = conn.execute(
            "SELECT name FROM inventory WHERE sku = ? LIMIT 1;", (sku,)
        ).fetchone()

        return {
            "found": True,
            "sku": row["sku"],
            "name": name_row["name"] if name_row else None,
            "unit_cost": round(unit_cost, 2),
            "list_price": round(list_price, 2),
            "unit_margin": round(unit_margin, 2),
            "margin_pct_of_list": (
                round(100 * unit_margin / list_price, 1) if list_price else None
            ),
            "qty": qty,
            "order_total_at_list": round(list_price * qty, 2),
            "order_total_at_cost": round(unit_cost * qty, 2),
            "order_margin_at_list": round(unit_margin * qty, 2),
            # The database has no discount policy and no approval table. Flagged
            # so the agent escalates instead of inventing a percentage.
            "discount_authority_in_database": False,
            "note": (
                "No discount policy or approval authority is recorded in this "
                "database. Any discount must be approved outside these tools."
            ),
        }


# ---------------------------------------------------------------------------
# Ticket queue — the Boss reads work from here.
# ---------------------------------------------------------------------------


def _vendor_block(
    conn: sqlite3.Connection, vendor_id: int, ignoring_invoice: int | None = None
) -> dict[str, Any]:
    """Shop rule: a vendor will not ship new product while an invoice of theirs is unpaid.

    Returns the blocking invoices, read from the invoices table, so the caller
    can say exactly which bill is holding the order up.

    `ignoring_invoice` answers the forward-looking question — would this vendor
    ship once that invoice is cleared? — without pretending it is already paid.
    """
    rows = conn.execute(
        "SELECT id, amount, due_date, status, description FROM invoices "
        "WHERE vendor_id = ? AND status = 'open' AND id IS NOT ? ORDER BY due_date;",
        (vendor_id, ignoring_invoice),
    ).fetchall()
    owed = round(sum(r["amount"] for r in rows), 2)
    return {
        "can_ship": not rows,
        "blocking_invoices": [dict(r) for r in rows],
        "amount_owed": owed,
        "reason": (
            None
            if not rows
            else (
                f"Vendor will not ship while {len(rows)} unpaid invoice(s) totalling "
                f"${owed:,.2f} remain open. Clear invoice "
                f"{', '.join(str(r['id']) for r in rows)} first."
            )
        ),
    }


@mcp.tool
def list_open_tickets() -> dict[str, Any]:
    """List every ticket still open, with the fields that say which other tables it touches.

    This is the work queue. A ticket's type and its populated link fields
    (sku/size/qty, lease_id, invoice_id) tell the reader which specialist and
    which lookup the ticket needs.

    Returns:
        The open tickets in creation order, and the shop's current date.
    """
    with _connect() as conn:
        rows = conn.execute(
            "SELECT id, type, requester, subject, sku, size, qty, lease_id, "
            "invoice_id, status, notes, created_at FROM tickets "
            "WHERE status = 'open' ORDER BY created_at;"
        ).fetchall()
        return {
            "as_of": _today(conn),
            "open_ticket_count": len(rows),
            "tickets": [
                {k: r[k] for k in r.keys() if r[k] not in (None, "")} for r in rows
            ],
        }


@mcp.tool
def get_ticket(ticket_id: int) -> dict[str, Any]:
    """Read one ticket in full, including the free-text notes from the requester.

    The notes often carry the real ask (for example a discount request) that no
    column records, so they must be read rather than inferred from the subject.

    Args:
        ticket_id: The ticket id, e.g. 101.
    """
    with _connect() as conn:
        row = conn.execute(
            "SELECT id, type, requester, subject, sku, size, qty, lease_id, "
            "invoice_id, status, notes, created_at FROM tickets WHERE id = ?;",
            (ticket_id,),
        ).fetchone()
        if row is None:
            return {
                "found": False,
                "ticket_id": ticket_id,
                "reason": f"No ticket with id {ticket_id}.",
            }
        return {
            "found": True,
            "as_of": _today(conn),
            **{k: row[k] for k in row.keys()},
        }


# ---------------------------------------------------------------------------
# Restocking — Inventory uses these to find who can resupply and how fast.
# ---------------------------------------------------------------------------


@mcp.tool
def find_restock_vendor(sku: str) -> dict[str, Any]:
    """List vendors who could restock a SKU, fastest first, with any evidence they have supplied it before.

    The schema records no SKU-to-vendor mapping, so this tool does not claim
    one. It returns every vendor with its specialty and lead time, plus any
    existing invoice whose description names this SKU — real evidence of who
    has supplied it, as opposed to a guess from the specialty text.

    Args:
        sku: Product code to restock, e.g. "CC-TEE-WHITE".
    """
    with _connect() as conn:
        vendors = conn.execute(
            "SELECT id, name, specialty, lead_days FROM vendors ORDER BY lead_days;"
        ).fetchall()
        prior = conn.execute(
            "SELECT i.id AS invoice_id, i.vendor_id, v.name AS vendor_name, "
            "i.description, i.status, i.amount FROM invoices i "
            "JOIN vendors v ON v.id = i.vendor_id "
            "WHERE i.description LIKE '%' || ? || '%';",
            (sku,),
        ).fetchall()
        enriched = []
        for v in vendors:
            block = _vendor_block(conn, v["id"])
            today = _today(conn)
            eta = conn.execute(
                "SELECT date(?, '+' || ? || ' days');", (today, v["lead_days"])
            ).fetchone()[0]
            enriched.append({
                **dict(v),
                "can_ship": block["can_ship"],
                "blocked_reason": block["reason"],
                "amount_owed_to_vendor": block["amount_owed"],
                "earliest_arrival_if_ordered_today": eta if block["can_ship"] else None,
                "earliest_arrival_once_unblocked": eta,
            })

        return {
            "sku": sku,
            "as_of": _today(conn),
            "vendors": enriched,
            "vendors_able_to_ship": [v["name"] for v in enriched if v["can_ship"]],
            "vendors_blocked": [v["name"] for v in enriched if not v["can_ship"]],
            "prior_supply_evidence": [dict(r) for r in prior],
            "note": (
                "No SKU-to-vendor mapping exists in this database. Vendor specialty "
                "text and prior invoices are the only evidence; choose on that basis "
                "and say which you used. Lead times are the vendors table's own "
                "lead_days. A vendor with an open unpaid invoice will not ship new "
                "product until that invoice is cleared."
            ),
        }


# ---------------------------------------------------------------------------
# Money — Accounting reads these. None of them move money.
# ---------------------------------------------------------------------------


@mcp.tool
def get_invoice(invoice_id: int) -> dict[str, Any]:
    """Read one vendor invoice with its vendor, and say whether it is overdue against the shop's date.

    Args:
        invoice_id: The invoice id, e.g. 501.
    """
    with _connect() as conn:
        row = conn.execute(
            "SELECT i.id, i.vendor_id, v.name AS vendor_name, v.lead_days, "
            "i.amount, i.due_date, i.status, i.description FROM invoices i "
            "JOIN vendors v ON v.id = i.vendor_id WHERE i.id = ?;",
            (invoice_id,),
        ).fetchone()
        if row is None:
            return {
                "found": False,
                "invoice_id": invoice_id,
                "reason": f"No invoice with id {invoice_id}.",
            }
        days = _days_between(conn, row["due_date"])
        return {
            "found": True,
            "invoice_id": row["id"],
            "vendor_id": row["vendor_id"],
            "vendor_name": row["vendor_name"],
            "vendor_lead_days": row["lead_days"],
            "amount": round(row["amount"], 2),
            "due_date": row["due_date"],
            "status": row["status"],
            "description": row["description"],
            "as_of": _today(conn),
            "days_until_due": days,
            "is_overdue": days is not None and days < 0,
        }


@mcp.tool
def get_cash_position() -> dict[str, Any]:
    """Return cash on hand against every known claim on it: open invoices and rent due.

    This is the affordability picture. Every figure is summed from rows; the
    tool does not decide what to pay.
    """
    with _connect() as conn:
        cash = conn.execute(
            "SELECT name, balance, date FROM cash_accounts;"
        ).fetchall()
        invoices = conn.execute(
            "SELECT id, vendor_id, amount, due_date, status FROM invoices "
            "WHERE status = 'open';"
        ).fetchall()
        leases = conn.execute(
            "SELECT id, space_name, monthly_rent, next_due FROM leases;"
        ).fetchall()
        paid = conn.execute("SELECT COALESCE(SUM(amount), 0) AS t FROM payments;").fetchone()

        total_cash = sum(c["balance"] for c in cash)
        open_inv = sum(i["amount"] for i in invoices)
        rent = sum(l["monthly_rent"] for l in leases)
        return {
            "as_of": _today(conn),
            "accounts": [dict(c) for c in cash],
            "total_cash": round(total_cash, 2),
            "open_invoices": [dict(i) for i in invoices],
            "open_invoice_total": round(open_inv, 2),
            "leases_due": [dict(l) for l in leases],
            "rent_total": round(rent, 2),
            "total_committed": round(open_inv + rent, 2),
            "remaining_if_all_paid": round(total_cash - open_inv - rent, 2),
            "can_cover_everything": total_cash >= open_inv + rent,
            "payments_recorded_so_far": round(paid["t"], 2),
            "note": (
                "Cash only leaves this account — no revenue is modelled in this "
                "database, so the balance never rises. Payments are refused rather "
                "than allowed to overdraw it."
            ),
        }


@mcp.tool
def prepare_payment(kind: str, ref_id: int) -> dict[str, Any]:
    """Draft a payment for a human to approve. Moves no money and writes nothing.

    The amount is read from the source row, never supplied by the caller, so a
    draft cannot be inflated by whoever asks for it. The result always carries
    requires_human_approval = true: only a human can authorise the payment, and
    only record_payment can execute it.

    Args:
        kind: "invoice" (pays an invoices row) or "rent" (pays a leases row).
        ref_id: The id in that table, e.g. 501 for an invoice or 1 for a lease.
    """
    kind = kind.strip().lower()
    with _connect() as conn:
        if kind == "invoice":
            row = conn.execute(
                "SELECT i.id, i.amount, i.due_date, i.status, v.name AS payee "
                "FROM invoices i JOIN vendors v ON v.id = i.vendor_id WHERE i.id = ?;",
                (ref_id,),
            ).fetchone()
        elif kind == "rent":
            row = conn.execute(
                "SELECT id, monthly_rent AS amount, next_due AS due_date, "
                "landlord AS payee FROM leases WHERE id = ?;",
                (ref_id,),
            ).fetchone()
        else:
            return {
                "drafted": False,
                "reason": f"Unknown payment kind {kind!r}. Use 'invoice' or 'rent'.",
            }

        if row is None:
            return {
                "drafted": False,
                "reason": f"No {kind} row with id {ref_id}; nothing to pay.",
            }

        amount = round(row["amount"], 2)
        balance = conn.execute(
            "SELECT balance FROM cash_accounts WHERE name = 'checking';"
        ).fetchone()["balance"]
        days = _days_between(conn, row["due_date"])

        return {
            "drafted": True,
            "kind": kind,
            "ref_id": row["id"],
            "payee": row["payee"],
            "amount": amount,
            "amount_source": f"read from {kind} row {row['id']}, not from the caller",
            "due_date": row["due_date"],
            "days_until_due": days,
            "is_overdue": days is not None and days < 0,
            "account": "checking",
            "balance_before": round(balance, 2),
            "balance_after_if_paid": round(balance - amount, 2),
            "affordable": balance >= amount,
            "requires_human_approval": True,
            "would_unblock_vendor": (
                {
                    "vendor_id": (vid := conn.execute(
                        "SELECT vendor_id FROM invoices WHERE id = ?;", (ref_id,)
                    ).fetchone()["vendor_id"]),
                    "vendor_name": conn.execute(
                        "SELECT name FROM vendors WHERE id = ?;", (vid,)
                    ).fetchone()["name"],
                    "can_ship_now": _vendor_block(conn, vid)["can_ship"],
                    "can_ship_after_this_payment": _vendor_block(
                        conn, vid, ignoring_invoice=row["id"]
                    )["can_ship"],
                    "lead_days_then": conn.execute(
                        "SELECT lead_days FROM vendors WHERE id = ?;", (vid,)
                    ).fetchone()["lead_days"],
                }
                if kind == "invoice" else None
            ),
            "status": "DRAFT — not paid. No money has moved and nothing was written.",
            "to_execute": (
                "A human must approve. Only then may record_payment be called, "
                "with the approver's own name."
            ),
        }


@mcp.tool
def prepare_purchase_order(sku: str, size: str, qty: int, vendor_id: int) -> dict[str, Any]:
    """Draft a restock purchase order for a human to approve. Writes nothing and commits to nothing.

    Costs come from the pricing row and the promise date from the vendor's lead
    time, both read from the database. The result is a proposal only.

    Args:
        sku: Product code to order.
        size: Size to order.
        qty: Units to order.
        vendor_id: Vendor to order from, e.g. from find_restock_vendor.
    """
    with _connect() as conn:
        vendor = conn.execute(
            "SELECT id, name, specialty, lead_days FROM vendors WHERE id = ?;",
            (vendor_id,),
        ).fetchone()
        if vendor is None:
            return {"drafted": False, "reason": f"No vendor with id {vendor_id}."}

        block = _vendor_block(conn, vendor_id)
        if not block["can_ship"]:
            return {
                "drafted": False,
                "blocked": True,
                "vendor_id": vendor["id"],
                "vendor_name": vendor["name"],
                "reason": block["reason"],
                "blocking_invoices": block["blocking_invoices"],
                "amount_owed": block["amount_owed"],
                "unblock_by": (
                    "Pay the open invoice first. That payment needs human approval."
                ),
            }

        price = conn.execute(
            "SELECT unit_cost FROM pricing WHERE sku = ?;", (sku,)
        ).fetchone()
        if price is None:
            return {
                "drafted": False,
                "reason": f"No pricing row for {sku}; unit cost is unknown, so no total can be quoted.",
            }

        stock = conn.execute(
            "SELECT qty FROM inventory WHERE sku = ? AND size = ?;", (sku, size)
        ).fetchone()
        today = _today(conn)
        eta = conn.execute(
            "SELECT date(?, '+' || ? || ' days');", (today, vendor["lead_days"])
        ).fetchone()[0]
        balance = conn.execute(
            "SELECT balance FROM cash_accounts WHERE name = 'checking';"
        ).fetchone()["balance"]
        total = round(price["unit_cost"] * qty, 2)

        return {
            "drafted": True,
            "vendor_id": vendor["id"],
            "vendor_name": vendor["name"],
            "vendor_specialty": vendor["specialty"],
            "sku": sku,
            "size": size,
            "qty": qty,
            "unit_cost": round(price["unit_cost"], 2),
            "total_cost": total,
            "current_stock": stock["qty"] if stock else None,
            "lead_days": vendor["lead_days"],
            "ordered_on": today,
            "earliest_arrival": eta,
            "balance_before": round(balance, 2),
            "affordable_today": balance >= total,
            "requires_human_approval": True,
            "status": "DRAFT — not ordered. Nothing was written and no vendor was contacted.",
        }


@mcp.tool
def mark_ticket_resolved(ticket_id: int, resolved_by: str, summary: str = "") -> dict[str, Any]:
    """Close a ticket once its run is finished. Writes to the tickets table.

    Not given to any agent: an agent marking its own work resolved is a
    self-assessment, so this is driven by the board after a run completes.

    Args:
        ticket_id: The ticket to close.
        resolved_by: Who closed it — the board, or a person.
        summary: Optional one-line note appended to the ticket's notes.
    """
    with _connect(readonly=False) as conn:
        row = conn.execute(
            "SELECT id, status, notes FROM tickets WHERE id = ?;", (ticket_id,)
        ).fetchone()
        if row is None:
            return {"resolved": False, "reason": f"No ticket with id {ticket_id}."}
        if row["status"] == "resolved":
            return {"resolved": True, "ticket_id": ticket_id, "already": True}

        notes = row["notes"] or ""
        if summary:
            notes = f"{notes}\n[resolved {_today(conn)} by {resolved_by}] {summary}".strip()
        conn.execute(
            "UPDATE tickets SET status = 'resolved', notes = ? WHERE id = ?;",
            (notes, ticket_id),
        )
        conn.commit()
        return {
            "resolved": True,
            "ticket_id": ticket_id,
            "resolved_by": resolved_by,
            "resolved_on": _today(conn),
            "already": False,
        }


# ---------------------------------------------------------------------------
# The only tool that writes. Human approval is mandatory and checked here.
# ---------------------------------------------------------------------------

# Agents must never appear as an approver. Enforced below, not just documented.
AGENT_NAMES = {
    "boss", "inventory", "accounting", "facilities", "customer_service",
    "customer service", "agent", "ai", "assistant", "system", "bot",
    "campus-customs", "llm", "gpt", "model",
}


@mcp.tool
def record_payment(
    kind: str,
    ref_id: int,
    human_approved: bool,
    approved_by: str,
) -> dict[str, Any]:
    """Execute a payment a human has already approved: write it to payments and decrement cash.

    This is the only tool in the server that writes. It refuses unless a human
    has approved: `human_approved` must be true and `approved_by` must name a
    real person, never an agent. No agent is given this tool — it is reserved
    for the human approval step.

    The amount is read from the source row, so an approver authorises the
    invoice or the lease, not a number the caller chose. The payment row and the
    cash decrement happen in one transaction, since the schema has no trigger
    linking them.

    Args:
        kind: "invoice" or "rent".
        ref_id: The id in that table.
        human_approved: Must be true. Set only by the approving human.
        approved_by: The approving person's name.
    """
    kind = kind.strip().lower()
    who = (approved_by or "").strip()

    if not human_approved:
        return {
            "paid": False,
            "refused": "human_approved is false. A human must approve every payment.",
        }
    if not who:
        return {
            "paid": False,
            "refused": "approved_by is empty. Every payment must record the approving human.",
        }
    if who.lower() in AGENT_NAMES:
        return {
            "paid": False,
            "refused": (
                f"{who!r} is an agent, not a human. Payments must be approved by a person."
            ),
        }

    with _connect(readonly=False) as conn:
        if kind == "invoice":
            row = conn.execute(
                "SELECT id, amount, status FROM invoices WHERE id = ?;", (ref_id,)
            ).fetchone()
            if row and row["status"] == "paid":
                return {"paid": False, "refused": f"Invoice {ref_id} is already paid."}
        elif kind == "rent":
            row = conn.execute(
                "SELECT id, monthly_rent AS amount FROM leases WHERE id = ?;", (ref_id,)
            ).fetchone()
        else:
            return {"paid": False, "refused": f"Unknown payment kind {kind!r}."}

        if row is None:
            return {"paid": False, "refused": f"No {kind} row with id {ref_id}."}

        amount = round(row["amount"], 2)
        if amount <= 0:
            # Cash only goes out in this shop; revenue is not modelled. A zero or
            # negative payment would credit the account, so it cannot be allowed.
            return {
                "paid": False,
                "refused": (
                    f"Refusing a payment of {amount:.2f}. Cash only leaves this "
                    "account — no inbound money is modelled."
                ),
            }

        balance = conn.execute(
            "SELECT balance FROM cash_accounts WHERE name = 'checking';"
        ).fetchone()["balance"]
        if balance < amount:
            return {
                "paid": False,
                "refused": (
                    f"Insufficient funds: balance ${balance:,.2f} is less than "
                    f"${amount:,.2f}. The shop does not go overdrawn, and no "
                    f"revenue is modelled to cover it. Shortfall ${amount - balance:,.2f}."
                ),
                "balance": round(balance, 2),
                "amount": amount,
                "shortfall": round(amount - balance, 2),
            }

        today = _today(conn)
        try:
            cur = conn.execute(
                "INSERT INTO payments (kind, ref_id, amount, account, paid_at, approved_by) "
                "VALUES (?, ?, ?, 'checking', ?, ?);",
                (kind, ref_id, amount, today, who),
            )
            conn.execute(
                "UPDATE cash_accounts SET balance = balance - ? WHERE name = 'checking';",
                (amount,),
            )
            if kind == "invoice":
                conn.execute(
                    "UPDATE invoices SET status = 'paid' WHERE id = ?;", (ref_id,)
                )
            conn.commit()
        except Exception:
            conn.rollback()
            raise

        new_balance = conn.execute(
            "SELECT balance FROM cash_accounts WHERE name = 'checking';"
        ).fetchone()["balance"]
        # The two invariants this shop runs on, checked rather than assumed.
        assert new_balance >= 0, "balance went negative"
        assert new_balance < balance, "cash must only ever decrease"
        return {
            "paid": True,
            "payment_id": cur.lastrowid,
            "kind": kind,
            "ref_id": ref_id,
            "amount": amount,
            "paid_at": today,
            "approved_by": who,
            "balance_before": round(balance, 2),
            "balance_after": round(new_balance, 2),
            "tables_updated": ["payments", "cash_accounts"]
            + (["invoices"] if kind == "invoice" else []),
        }


def main() -> None:
    parser = argparse.ArgumentParser(description="Campus Customs back-office MCP server")
    parser.add_argument(
        "--http", action="store_true", help="serve over HTTP instead of stdio"
    )
    parser.add_argument("--port", type=int, default=8003, help="HTTP port")
    args = parser.parse_args()

    if args.http:
        mcp.run(transport="http", host="127.0.0.1", port=args.port)
    else:
        mcp.run()


if __name__ == "__main__":
    main()
