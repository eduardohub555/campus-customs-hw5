"""Model and connection configuration — the single place the model name lives.

Every agent on the team uses one model, `gpt-6-luna`, reached through Portkey
with the OpenAI-compatible API. The name appears exactly once in this codebase,
here, so there is no way for a second model to drift into a run.

The API key is read from the root .env file and never hard-coded.
"""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv
from pydantic_ai.models.openai import OpenAIChatModel, OpenAIChatModelSettings
from pydantic_ai.providers.openai import OpenAIProvider
from pydantic_ai.usage import UsageLimits

HW5 = Path(__file__).resolve().parent.parent
PROJECT_ROOT = HW5.parent

load_dotenv(PROJECT_ROOT / ".env")

#: The only model this project may use. Nothing else is permitted in a run.
MODEL_NAME = "gpt-6-luna"

PORTKEY_BASE_URL = "https://api.portkey.ai/v1"

#: gpt-6-luna rejects function tools unless reasoning is off on this endpoint,
#: and these tickets are small lookups that need no deliberation anyway — so
#: this is both the API requirement and the cheap setting.
MODEL_SETTINGS = OpenAIChatModelSettings(openai_reasoning_effort="none")

DB_PATH = HW5 / "data" / "campus_customs_new.db"
SERVER_PATH = HW5 / "mcp_server" / "server.py"
VENV_PYTHON = HW5 / ".venv" / "bin" / "python"
AUDIT_PATH = HW5 / "output" / "audit_trail.json"

#: Tools no agent may ever hold.
#:   record_payment      — moves money; only a human runs it.
#:   mark_ticket_resolved — closing your own ticket is a self-assessment;
#:                          the board does it once a run finishes.
HUMAN_ONLY_TOOLS = frozenset({"record_payment", "mark_ticket_resolved"})

#: The problems here are small. These ceilings stop a delegation loop from
#: quietly burning the budget, and fail loudly if one ever tries.
#:
#: The budget is shared across a whole ticket chain, not per agent. Ticket 101
#: is the demanding one under the shop rules — Inventory checks stock, finds the
#: vendor blocked by an unpaid invoice, and hands to Accounting to read that
#: invoice and draft the payment — so the ceiling has to clear that honestly
#: rather than cutting a correct chain short.
AGENT_USAGE_LIMITS = UsageLimits(
    request_limit=16,
    tool_calls_limit=20,
    total_tokens_limit=150_000,
)

#: How many times a ticket may be handed from one agent to another.
MAX_DELEGATION_HOPS = 3


def get_model() -> OpenAIChatModel:
    """Build the one model every agent shares.

    Raises if the key is missing rather than letting a run start and fail
    halfway through with half a ticket processed.
    """
    key = os.getenv("PORTKEY_API_KEY")
    if not key:
        raise RuntimeError(
            "PORTKEY_API_KEY is not set. Add it to the project root .env file."
        )
    return OpenAIChatModel(
        MODEL_NAME,
        provider=OpenAIProvider(api_key=key, base_url=PORTKEY_BASE_URL),
    )


def load_prompt(name: str) -> str:
    """Load an agent's prompt and append the house rules shared by the whole team."""
    prompts = Path(__file__).resolve().parent / "prompts"
    role = (prompts / f"{name}.md").read_text(encoding="utf-8")
    shared = (prompts / "_shared_rules.md").read_text(encoding="utf-8")
    return f"{role.strip()}\n\n{shared.strip()}"
