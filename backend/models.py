"""Data types for the Campus Customs agent team.

Structured outputs keep the agents brief: each one fills a small, fixed shape
rather than writing prose that then has to be parsed. That is a token decision
as much as a typing one.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class AgentName(str, Enum):
    """The five roles on the team. Used for routing and for the audit trail."""

    BOSS = "boss"
    INVENTORY = "inventory"
    ACCOUNTING = "accounting"
    FACILITIES = "facilities"
    CUSTOMER_SERVICE = "customer_service"


class TicketType(str, Enum):
    """Ticket types as they appear in the tickets table."""

    CUSTOMER_ORDER = "customer_order"
    RENT_NOTICE = "rent_notice"
    PRICE_OVERRIDE = "price_override"


class SpecialistReport(BaseModel):
    """What a specialist hands back to whoever asked.

    `facts_used` is the anti-invention check: every figure in the summary must
    be traceable to a tool result the agent can name here.
    """

    summary: str = Field(description="Two or three sentences. The answer, not the journey.")
    facts_used: list[str] = Field(
        default_factory=list,
        description="Each fact that shaped this answer, with the MCP tool it came from.",
    )
    recommended_action: str = Field(
        description="The single next step you recommend. Say 'none' if there is nothing to do."
    )
    needs_human_approval: bool = Field(
        default=False,
        description="True if acting on this needs a person to approve, e.g. any payment or order.",
    )
    blocked_on_missing_data: str | None = Field(
        default=None,
        description="What the database does not contain, if that stopped you. Null if nothing was missing.",
    )
    draft_message: str | None = Field(
        default=None,
        description="Customer-facing or vendor-facing text, when the task was to draft one.",
    )


class BossDecision(BaseModel):
    """The Boss's final call on one ticket."""

    ticket_id: int
    assigned_to: AgentName = Field(description="The specialist the Boss delegated this ticket to.")
    instruction_given: str = Field(description="The brief the Boss sent, in the Boss's own words.")
    decision: str = Field(description="The final call, in two or three sentences.")
    rationale: str = Field(description="What the decision rests on. Facts only.")
    needs_human_approval: bool = Field(
        default=False, description="True if a person must approve before anything happens."
    )
    awaiting_human: str | None = Field(
        default=None, description="Exactly what the human is being asked to approve, if anything."
    )


class AuditStep(BaseModel):
    """One recorded step of an agent loop.

    Written for someone auditing later who was not there: who acted, what they
    were asked, which tools they called with which arguments, what came back,
    and what it cost.
    """

    step: int
    at: datetime
    agent: AgentName
    event: str = Field(description="agent_run | tool_call | delegation | refusal | error")
    ticket_id: int | None = None
    asked_by: AgentName | str | None = Field(
        default=None, description="Who prompted this step — an agent, or 'human'."
    )
    prompt: str | None = Field(default=None, description="The instruction this agent received.")
    tool_name: str | None = None
    tool_args: dict[str, Any] | None = None
    tool_result: Any | None = None
    output: dict[str, Any] | None = Field(default=None, description="The agent's structured result.")
    model: str | None = Field(default=None, description="The model that produced this step.")
    input_tokens: int | None = None
    output_tokens: int | None = None
    duration_ms: int | None = None
    note: str | None = None


class TeamRun(BaseModel):
    """One end-to-end run of the team over a set of tickets."""

    run_id: str
    started_at: datetime
    finished_at: datetime | None = None
    model: str = Field(description="The single model every agent in this run used.")
    tickets_handled: list[int] = Field(default_factory=list)
    decisions: list[BossDecision] = Field(default_factory=list)
    steps: list[AuditStep] = Field(default_factory=list)
    total_input_tokens: int = 0
    total_output_tokens: int = 0
    payments_made: int = Field(
        default=0, description="Payments executed by agents. Must always be 0 — only humans pay."
    )
    notes: str | None = None
