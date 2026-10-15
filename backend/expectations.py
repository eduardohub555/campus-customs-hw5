"""The Problem 6 plan, as data.

output/desk_tickets.html states what the team is expected to do on each ticket.
Holding the same plan here lets the backend do two things the HTML cannot: put
the routing rule into the brief the Boss actually receives, and report expected
against actual after a run, so the gap is measured rather than eyeballed.

The rule, in one line: call the one specialist whose job the ticket is, then at
most one more if the first cannot finish alone. Never every specialist.
"""

from __future__ import annotations

from models import AgentName

MAX_SPECIALISTS_PER_TICKET = 2

EXPECTED: dict[int, dict] = {
    101: {
        "ticket_type": "customer_order",
        "first": AgentName.INVENTORY,
        "then": AgentName.ACCOUNTING,
        "not_expected": {
            AgentName.FACILITIES: "This is a t-shirt, not the building.",
        },
        # Not wrong to involve, but premature: a reply can only be honest once
        # the restock question is settled, and drafting earlier risks promising
        # a date the tools have not given.
        "deferred": {
            AgentName.CUSTOMER_SERVICE: (
                "Draft the reply once a restock date exists. Replying before that "
                "either says nothing new or invents a date."
            ),
        },
        "tools_expected": [
            "get_ticket",
            "check_stock",
            "find_restock_vendor",
            "get_invoice",
            "prepare_payment",
        ],
        "tools_not_expected": ["get_lease_payment", "get_price_and_margin"],
        "expected_outcome": (
            "0 on hand. The reprint vendor, Bulldog Print Co, will not ship while "
            "invoice 501 ($840, 3 days overdue) is unpaid, so the restock is blocked "
            "on that payment. Accounting drafts it; a human approves. Earliest "
            "arrival 2026-09-05, five days after payment clears."
        ),
        "expects_human_approval": True,
    },
    102: {
        "ticket_type": "rent_notice",
        "first": AgentName.FACILITIES,
        "then": AgentName.ACCOUNTING,
        "not_expected": {
            AgentName.INVENTORY: "No SKU, no size, no stock.",
            AgentName.CUSTOMER_SERVICE: "The landlord is not a customer; nobody awaits a reply.",
        },
        "deferred": {},
        "tools_expected": [
            "get_ticket",
            "get_lease_payment",
            "get_cash_position",
            "prepare_payment",
        ],
        "tools_not_expected": [
            "check_stock",
            "find_restock_vendor",
            "get_price_and_margin",
        ],
        "expected_outcome": "$2,400.00 due 2026-09-02 confirmed from the lease; payment drafted.",
        "expects_human_approval": True,
    },
    103: {
        "ticket_type": "price_override",
        "first": AgentName.ACCOUNTING,
        "then": AgentName.CUSTOMER_SERVICE,
        "not_expected": {
            AgentName.FACILITIES: "Nothing here concerns the premises.",
            AgentName.INVENTORY: (
                "The item exists and is already priced; the ask is what it should "
                "cost. Size M is short of 20, but that is a second conversation "
                "once a price is agreed — flagged by Accounting, not delegated."
            ),
        },
        "deferred": {},
        "tools_expected": ["get_ticket", "get_price_and_margin"],
        "tools_not_expected": [
            "get_lease_payment",
            "check_stock",
            "find_restock_vendor",
            "prepare_payment",
        ],
        "expected_outcome": "$720.00 margin at list on 20 units; no discount chosen, escalated to a human.",
        "expects_human_approval": True,
    },
}

#: No agent may ever call this, on any ticket.
NEVER_EXPECTED = ["record_payment"]


def brief_for(ticket_id: int) -> str:
    """The instruction the Boss receives, carrying the routing rule into the run."""
    plan = EXPECTED.get(ticket_id)
    if plan is None:
        return (
            f"Ticket {ticket_id} is open. Read it with get_ticket, delegate it to the "
            "one specialist best suited, and give your final decision. Keep it brief."
        )
    return (
        f"Ticket {ticket_id} is open. Read it with get_ticket, then delegate to the "
        f"single specialist whose job this is. Bring in a second only if the first "
        f"genuinely cannot finish alone — never more than "
        f"{MAX_SPECIALISTS_PER_TICKET}, and never every specialist.\n\n"
        "Shop rules that may change the answer: today is desk.date_today; vendor "
        "lead times come from the vendors table; a vendor will not ship while one "
        "of their invoices is unpaid; cash only leaves the shop and a payment is "
        "refused rather than overdrawing it; and nothing is ever sent — drafts stay "
        "on the board for a human.\n\n"
        "Give your final decision briefly."
    )


def compare(ticket_id: int, agents_used: list[str], tools_used: list[str]) -> dict:
    """Score one run against the plan. Used by the API and, later, the Reflection tab."""
    plan = EXPECTED.get(ticket_id)
    if plan is None:
        return {"has_expectation": False}

    specialists = [a for a in dict.fromkeys(agents_used) if a != AgentName.BOSS.value]
    forbidden = {a.value for a in plan["not_expected"]}
    deferred = {a.value for a in plan.get("deferred", {})}
    unexpected_agents = sorted(set(specialists) & forbidden)
    unexpected_tools = sorted(
        set(tools_used) & (set(plan["tools_not_expected"]) | set(NEVER_EXPECTED))
    )

    return {
        "has_expectation": True,
        "expected_first": plan["first"].value,
        "expected_then": plan["then"].value,
        "actual_specialists": specialists,
        "first_matched": bool(specialists) and specialists[0] == plan["first"].value,
        "within_specialist_budget": len(specialists) <= MAX_SPECIALISTS_PER_TICKET,
        "no_forbidden_agents": not unexpected_agents,
        "unexpected_agents": unexpected_agents,
        "deferred_agents_involved": sorted(set(specialists) & deferred),
        "expected_tools": plan["tools_expected"],
        "actual_tools": sorted(set(tools_used)),
        "unexpected_tools": unexpected_tools,
        "no_forbidden_tools": not unexpected_tools,
        "record_payment_called": "record_payment" in tools_used,
    }
