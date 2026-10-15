"""Append-only audit trail for agent runs.

Every run adds to output/audit_trail.json and nothing is ever removed. The file
holds a list of runs, each with its own ordered steps, so a later reader can
reconstruct who did what, on whose instruction, with which tool arguments, and
what came back.

If the file is ever unreadable it is moved aside with a timestamp rather than
overwritten — losing an audit trail to a parse error would defeat the point.
"""

from __future__ import annotations

import json
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from models import AgentName, AuditStep, TeamRun

SCHEMA_NOTE = (
    "Append-only audit trail for the Campus Customs agent team. Each entry in "
    "'runs' is one end-to-end run; 'steps' within it are ordered agent actions, "
    "delegations and MCP tool calls. Never truncated between runs."
)


class AuditTrail:
    """Collects steps during a run, then appends the run to the JSON file."""

    def __init__(self, path: Path, run_id: str, model: str) -> None:
        self.path = path
        self.run = TeamRun(
            run_id=run_id,
            started_at=datetime.now(timezone.utc).astimezone(),
            model=model,
        )
        self._step_no = 0

    def record(
        self,
        agent: AgentName,
        event: str,
        **fields: Any,
    ) -> AuditStep:
        """Add one step. Returns it so a caller can fill in timings afterwards."""
        self._step_no += 1
        step = AuditStep(
            step=self._step_no,
            at=datetime.now(timezone.utc).astimezone(),
            agent=agent,
            event=event,
            **fields,
        )
        self.run.steps.append(step)
        return step

    def tool_call(
        self,
        agent: AgentName,
        tool_name: str,
        tool_args: dict[str, Any],
        tool_result: Any,
        ticket_id: int | None = None,
        duration_ms: int | None = None,
    ) -> AuditStep:
        return self.record(
            agent,
            "tool_call",
            tool_name=tool_name,
            tool_args=tool_args,
            tool_result=tool_result,
            ticket_id=ticket_id,
            duration_ms=duration_ms,
        )

    def finish(self, notes: str | None = None) -> TeamRun:
        """Close the run and append it to the file, preserving every earlier run."""
        self.run.finished_at = datetime.now(timezone.utc).astimezone()
        self.run.notes = notes

        existing = self._read_existing()
        existing["audit_trail"]["runs"].append(
            json.loads(self.run.model_dump_json())
        )
        existing["audit_trail"]["run_count"] = len(existing["audit_trail"]["runs"])
        existing["audit_trail"]["last_updated"] = datetime.now(
            timezone.utc
        ).astimezone().isoformat(timespec="seconds")

        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(existing, indent=2, default=str) + "\n")
        return self.run

    def _read_existing(self) -> dict[str, Any]:
        """Load the trail so far. Never wipes: a bad file is set aside, not replaced."""
        if not self.path.exists():
            return {
                "audit_trail": {
                    "description": SCHEMA_NOTE,
                    "run_count": 0,
                    "runs": [],
                }
            }
        try:
            data = json.loads(self.path.read_text())
            if "audit_trail" in data and isinstance(
                data["audit_trail"].get("runs"), list
            ):
                data["audit_trail"]["description"] = SCHEMA_NOTE
                return data
            raise ValueError("unexpected shape")
        except Exception:
            stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
            shutil.copy2(self.path, self.path.with_suffix(f".corrupt-{stamp}.json"))
            return {
                "audit_trail": {
                    "description": SCHEMA_NOTE,
                    "run_count": 0,
                    "runs": [],
                    "note": (
                        f"Previous file could not be parsed; preserved alongside as "
                        f"audit_trail.corrupt-{stamp}.json"
                    ),
                }
            }
