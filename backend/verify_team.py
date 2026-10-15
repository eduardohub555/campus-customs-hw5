"""Verify the team's wiring: full connectivity, the loop guards, and the money rule.

Two kinds of check.

Structural checks make no model calls at all — they inspect the toolsets and
drive the delegation guard directly, so they are free and deterministic.

One live check spends tokens to prove the graph is genuinely complete: a
specialist delegating to another specialist with no Boss in the chain.

    .venv/bin/python backend/verify_team.py
"""

from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone
from typing import Any

from fastmcp import Client
from fastmcp.client.transports import StdioTransport

import settings
from agents import AGENTS, MCP_TOOLS, TeamDeps, _delegate, inventory
from audit import AuditTrail
from models import AgentName

results: list[dict[str, Any]] = []


def check(name: str, passed: bool, detail: Any) -> None:
    results.append({"check": name, "passed": bool(passed), "detail": detail})
    print(f"  [{'PASS' if passed else 'FAIL'}] {name}: {detail}")


class _FakeTool:
    """Just enough of a tool definition to run the toolset's filter predicate."""

    def __init__(self, name: str) -> None:
        self.name = name


class _Ctx:
    """Minimal stand-in for RunContext, enough to drive the delegation guard."""

    def __init__(self, deps: TeamDeps) -> None:
        self.deps = deps
        self.usage = None


async def main() -> None:
    run_id = f"verify-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}"
    audit = AuditTrail(settings.AUDIT_PATH, run_id, settings.MODEL_NAME)

    print("STRUCTURAL CHECKS (no model calls)\n")

    # 1. Every agent can reach every other agent: a complete graph, not a star.
    for name, agent in AGENTS.items():
        peers = set(agent._function_toolset.tools)
        expected = {f"ask_{o.value}" for o in AGENTS if o is not name}
        check(
            f"{name.value} can reach all 4 peers",
            expected <= peers,
            sorted(expected & peers),
        )

    # 2. The server really does expose the money tool...
    transport = StdioTransport(
        command=str(settings.VENV_PYTHON), args=[str(settings.SERVER_PATH)]
    )
    async with Client(transport) as c:
        server_tools = sorted(t.name for t in await c.list_tools())
    check(
        "server exposes record_payment",
        "record_payment" in server_tools,
        f"{len(server_tools)} tools on the server",
    )

    # ...and the agents' shared toolset filters it out, leaving the rest.
    keep = MCP_TOOLS.filter_func
    blocked = [t for t in server_tools if not keep(None, _FakeTool(t))]
    allowed = [t for t in server_tools if keep(None, _FakeTool(t))]
    check("agents cannot call record_payment", blocked == ["record_payment"], blocked)
    check(
        "agents keep every read/draft tool",
        len(allowed) == len(server_tools) - 1,
        f"{len(allowed)} tools available to agents",
    )

    # 3. The hop budget stops a runaway chain.
    deps = TeamDeps(audit=audit, ticket_id=101, hops_remaining=0,
                    call_stack=[AgentName.BOSS])
    out = await _delegate(_Ctx(deps), AgentName.INVENTORY, "please help")
    check("hop budget refuses when exhausted", "refused" in out, out.get("refused"))

    # 4. Re-entering an agent already in the chain is refused.
    deps = TeamDeps(audit=audit, ticket_id=101,
                    call_stack=[AgentName.BOSS, AgentName.INVENTORY])
    out = await _delegate(_Ctx(deps), AgentName.INVENTORY, "please help again")
    check("re-entry into a busy agent refused", "refused" in out, out.get("refused"))

    print("\nLIVE CHECK (one real delegation, specialist -> specialist)\n")

    deps = TeamDeps(audit=audit, ticket_id=101,
                    call_stack=[AgentName.INVENTORY])
    async with inventory:
        result = await inventory.run(
            "Ticket 101: the size S tee is out of stock. Check the stock figure, then "
            "ask Customer Service to draft the reply to Tauhid Zaman. Do not involve "
            "the Boss. Return their draft as your draft_message.",
            deps=deps,
            usage_limits=settings.AGENT_USAGE_LIMITS,
        )

    usage = result.usage
    audit.record(
        AgentName.INVENTORY,
        "agent_run",
        ticket_id=101,
        asked_by="human",
        output=result.output.model_dump(mode="json"),
        model=settings.MODEL_NAME,
        input_tokens=getattr(usage, "input_tokens", None),
        output_tokens=getattr(usage, "output_tokens", None),
        note="Connectivity check: specialist delegating to specialist, no Boss in the chain.",
    )

    peer_hops = [
        s for s in audit.run.steps
        if s.event == "delegation" and s.note == "inventory -> customer_service"
    ]
    check(
        "inventory delegated straight to customer_service",
        bool(peer_hops),
        peer_hops[0].note if peer_hops else "no peer-to-peer delegation recorded",
    )
    check(
        "customer_service produced a draft",
        bool(result.output.draft_message),
        (result.output.draft_message or "")[:90] + "...",
    )

    models = {s.model for s in audit.run.steps if s.model}
    check("only gpt-6-luna was used", models <= {settings.MODEL_NAME}, sorted(models))

    audit.finish(notes=f"Wiring verification: {sum(r['passed'] for r in results)}/{len(results)} passed.")

    passed = sum(r["passed"] for r in results)
    print(f"\n{'=' * 58}")
    print(f"{passed}/{len(results)} checks passed")
    print(f"tokens in/out: {getattr(usage, 'input_tokens', 0)} / {getattr(usage, 'output_tokens', 0)}")
    if result.output.draft_message:
        print(f"\nCustomer Service draft:\n{result.output.draft_message}")
    if passed != len(results):
        raise SystemExit("FAIL: see above.")


if __name__ == "__main__":
    asyncio.run(main())
