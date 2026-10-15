"""The five Campus Customs agents, and the wiring that lets them delegate.

Roles: Boss, Inventory, Accounting, Facilities, Customer Service.

Every agent runs on the same model (see settings.MODEL_NAME) and reaches shop
data only through the MCP server — there is deliberately no second tools layer
that touches the database directly, so everything an agent says is traceable to
an MCP call recorded in the audit trail.

Connectivity is full: every agent holds an `ask_<role>` tool for each of the
other four. Two guards keep that from becoming a loop — a hop budget shared
across the run, and a call stack that refuses re-entry to an agent already
working higher up the chain.

`record_payment` is filtered out of every agent's toolset. Agents prepare
payments; a human executes them.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

from fastmcp import Client
from fastmcp.client.transports import StdioTransport
from pydantic_ai import Agent, RunContext
from pydantic_ai.mcp import MCPToolset

import settings
from audit import AuditTrail
from models import AgentName, BossDecision, SpecialistReport


@dataclass
class TeamDeps:
    """Shared state for one ticket, passed to every agent in the chain."""

    audit: AuditTrail
    ticket_id: int | None = None
    hops_remaining: int = settings.MAX_DELEGATION_HOPS
    call_stack: list[AgentName] = field(default_factory=list)


def _build_toolset(deps_getter) -> MCPToolset:
    """Connect to the campus-customs MCP server, minus the tools humans keep.

    Every call is logged to the audit trail through process_tool_call, which
    sees the real arguments and the real result — so the trail records what the
    tools actually returned, not what an agent said they returned.
    """
    client = Client(
        StdioTransport(
            command=str(settings.VENV_PYTHON), args=[str(settings.SERVER_PATH)]
        )
    )

    async def logged_call(ctx: RunContext[TeamDeps], call_tool, name: str, args: dict, *rest):
        started = time.perf_counter()
        result = await call_tool(name, args, *rest)
        deps = ctx.deps
        if deps is not None:
            agent = deps.call_stack[-1] if deps.call_stack else AgentName.BOSS
            deps.audit.tool_call(
                agent=agent,
                tool_name=name,
                tool_args=args,
                tool_result=getattr(result, "data", result),
                ticket_id=deps.ticket_id,
                duration_ms=int((time.perf_counter() - started) * 1000),
            )
        return result

    toolset = MCPToolset(client=client, process_tool_call=logged_call)
    # Agents never hold the tool that moves money.
    return toolset.filtered(
        lambda ctx, tool: tool.name not in settings.HUMAN_ONLY_TOOLS
    )


MCP_TOOLS = _build_toolset(None)
MODEL = settings.get_model()


def _make_agent(name: str, output_type) -> Agent:
    return Agent(
        MODEL,
        name=name,
        deps_type=TeamDeps,
        output_type=output_type,
        instructions=settings.load_prompt(name),
        model_settings=settings.MODEL_SETTINGS,
        toolsets=[MCP_TOOLS],
        retries=2,
    )


boss = _make_agent("boss", BossDecision)
inventory = _make_agent("inventory", SpecialistReport)
accounting = _make_agent("accounting", SpecialistReport)
facilities = _make_agent("facilities", SpecialistReport)
customer_service = _make_agent("customer_service", SpecialistReport)

AGENTS: dict[AgentName, Agent] = {
    AgentName.BOSS: boss,
    AgentName.INVENTORY: inventory,
    AgentName.ACCOUNTING: accounting,
    AgentName.FACILITIES: facilities,
    AgentName.CUSTOMER_SERVICE: customer_service,
}

DESCRIPTIONS = {
    AgentName.BOSS: "the Boss, who routes tickets and makes the final decision",
    AgentName.INVENTORY: "Inventory, for stock levels, shortfalls, vendors and lead times",
    AgentName.ACCOUNTING: "Accounting, for cash, invoices, margins and payment drafts",
    AgentName.FACILITIES: "Facilities, for the shop space, the lease and rent",
    AgentName.CUSTOMER_SERVICE: "Customer Service, for any message a customer will read",
}


async def _delegate(
    ctx: RunContext[TeamDeps], target: AgentName, request: str
) -> SpecialistReport | BossDecision | dict[str, Any]:
    """Hand work to a colleague, with the loop guards applied."""
    deps = ctx.deps
    caller = deps.call_stack[-1] if deps.call_stack else AgentName.BOSS

    if deps.hops_remaining <= 0:
        deps.audit.record(
            caller,
            "refusal",
            ticket_id=deps.ticket_id,
            note=f"Delegation budget exhausted; refused to ask {target.value}.",
        )
        return {
            "refused": "No delegation budget left for this ticket. Answer with what you have."
        }

    if target in deps.call_stack:
        deps.audit.record(
            caller,
            "refusal",
            ticket_id=deps.ticket_id,
            note=f"{target.value} is already working on this ticket; refused to re-enter.",
        )
        return {
            "refused": (
                f"{target.value} is already handling this ticket further up the chain. "
                "Answer with what you have rather than looping."
            )
        }

    deps.hops_remaining -= 1
    deps.call_stack.append(target)
    deps.audit.record(
        caller,
        "delegation",
        ticket_id=deps.ticket_id,
        asked_by=caller,
        prompt=request,
        note=f"{caller.value} -> {target.value}",
    )

    started = time.perf_counter()
    try:
        result = await AGENTS[target].run(
            request,
            deps=deps,
            usage=ctx.usage,
            usage_limits=settings.AGENT_USAGE_LIMITS,
        )
    finally:
        deps.call_stack.pop()

    usage = result.usage
    deps.audit.record(
        target,
        "agent_run",
        ticket_id=deps.ticket_id,
        asked_by=caller,
        prompt=request,
        output=result.output.model_dump(mode="json"),
        model=settings.MODEL_NAME,
        input_tokens=getattr(usage, "input_tokens", None),
        output_tokens=getattr(usage, "output_tokens", None),
        duration_ms=int((time.perf_counter() - started) * 1000),
    )
    return result.output


def _register_delegation_tools() -> None:
    """Give every agent a way to reach every other agent.

    Registered programmatically because the graph is complete — five agents,
    four peers each, twenty tools — and writing them out by hand would be
    twenty chances to wire one wrongly.
    """
    for owner_name, owner_agent in AGENTS.items():
        for target_name in AGENTS:
            if target_name is owner_name:
                continue

            def make(target: AgentName):
                async def ask(ctx: RunContext[TeamDeps], request: str):
                    return await _delegate(ctx, target, request)

                ask.__name__ = f"ask_{target.value}"
                ask.__doc__ = (
                    f"Ask {DESCRIPTIONS[target]} to help with this ticket.\n\n"
                    "Be kind and specific: say what you need and why, in one or two "
                    "sentences. They can see the same MCP tools you can.\n\n"
                    "Args:\n"
                    "    request: Your brief for them, in your own words."
                )
                return ask

            owner_agent.tool(make(target_name))


_register_delegation_tools()
