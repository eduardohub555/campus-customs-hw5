# Campus Customs — Back-Office Agent Desk (HW5)

A five-agent team that works the Campus Customs back office: it reads tickets,
checks stock, chases vendors, watches cash, and drafts what a human should do —
then stops and asks. **Agents prepare; only a person approves a payment.**

MGT 409 · Yale SOM · every agent runs on `gpt-6-luna` through Portkey.

---

## What is here

| Piece | Where |
|---|---|
| MCP server — 12 tools, the only path to shop data | `mcp_server/server.py` |
| Five agents (Boss, Inventory, Accounting, Facilities, Customer Service) | `backend/` + `backend/prompts/` |
| FastAPI backend the board calls | `backend/main.py` |
| React + Vite + TypeScript dashboard | `frontend/` |
| Working notes, results, audit trail | `output/` |
| Prompt log for the whole assignment | `AI_prompts.md` |

Start with [`output/harness.md`](output/harness.md) — it covers the tables, the
MCP tools, the five agents, the API routes, the dashboard and the safety rules.

---

## Setup

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

```bash
cp .env.example .env
```

Then put your own Portkey key in `.env`. The real `.env` is **not** in this
repository; `backend/settings.py` reads the key at runtime and it is never
hard-coded.

---

## Copy the original database to the working copy for a clean run

Two database files ship with this repo:

- `data/campus_customs.db` — the **original**. Never written to. The reference.
- `data/campus_customs_new.db` — the **working copy**. Everything runs against this.

Whenever you want a clean slate, copy the original over the working copy:

```bash
cp data/campus_customs.db data/campus_customs_new.db
```

That restores checking to $3,400.00, clears `payments`, reopens all three
tickets, and puts invoice 501 back to unpaid.

**The working copy ships clean**, so the app runs out of the box. The results of
the recorded three-ticket run are kept in `output/` — see
`output/resolved_tickets.json`, `output/audit_trail.json` and the Cash tab of
`output/desk_tickets.html`.

---

## 1. Start the MCP server

Every shop fact the agents use comes through here — no agent touches the
database directly.

```bash
.venv/bin/python mcp_server/server.py
```

That speaks MCP over stdio. For HTTP instead:

```bash
.venv/bin/python mcp_server/server.py --http
```

**You usually do not need to start this yourself.** The backend and the agents
launch it as a subprocess on demand. Run it directly only to test the server on
its own. `.mcp.json` registers it as `campus-customs` for editors that read
that file.

Smoke-test the tools against the database:

```bash
.venv/bin/python mcp_server/smoke_test.py
```

---

## 2. Start the FastAPI backend

From the `backend/` folder:

```bash
cd backend
uvicorn main:app --reload --port 8000
```

Serving at **http://localhost:8000**, with interactive docs at `/docs`.

| Route | Does |
|---|---|
| `GET /health` | liveness, model, shop date |
| `GET /tickets` | the three tickets with open/resolved status |
| `POST /tickets/{id}/run` | run the agent team on one ticket |
| `GET /events` | recent agent events, for the board to poll |
| `GET /cash` | checking balance and what is still owed |
| `POST /approvals` | **the human click — the only route that moves money** |
| `POST /reset` | restore the working copy from the original |
| `POST /runs/all` | reset, then run every open ticket |
| `GET /shop-rules` | the rules this backend enforces |

---

## 3. Start the React board

In a second terminal:

```bash
cd frontend
npm install
npm run dev
```

Vite opens the board automatically. It takes port **5173** if free and steps up
if not. The backend accepts any `localhost` origin, so whichever port Vite
picks will work.

Pick a ticket, press **Start the agent team**, and watch the five Handsome Dans
work. When a run needs money, the board asks *"Dear human user, can you please
approve?"* — type your name and approve, and the checking balance drops.

---

## 4. Reset the database before a full three-ticket run

**Always start a full run from the original database**, so all three tickets are
resolved against the same starting cash, stock and invoices, and one run cannot
inherit another's state.

Any one of these does it:

```bash
cp data/campus_customs.db data/campus_customs_new.db
```

```bash
curl -X POST http://localhost:8000/reset
```

Or press **Reset shop** on the board.

Then run all three — from the board, or in one call:

```bash
curl -X POST "http://localhost:8000/runs/all"
```

`/runs/all` resets first by default. Pass `?reset_first=false` only when you
deliberately want to continue from where the last run left off.

The audit trail in `output/audit_trail.json` is **append-only and is never
wiped by a reset** — the reset is recorded in it as an event instead.

---

## What a full run produces

From a clean database, the three tickets resolve like this:

| Ticket | Agents | Outcome | Cash |
|---|---|---|---|
| **101** Bulldog tee | Boss → Inventory → Accounting | 0 in stock; the only vendor who reprints it is blocked by unpaid invoice 501 | −$840.00 once a human approves |
| **102** Rent due | Boss → Facilities | the lease is authoritative, not the email: $2,400.00 due 2026-09-02 | −$2,400.00 once a human approves |
| **103** Bulk discount | Boss → Accounting | $720.00 margin at list on 20 units; **no discount set** — the database records no discount policy or approval authority | no movement |

$3,400.00 − $840.00 − $2,400.00 = **$160.00**, matching `cash_accounts`.

Results are written to `output/resolved_tickets.json`,
`output/desk_tickets.html` (expected vs actual, plus the cash ledger) and
`output/resolved_board.html` (screenshots of the board).

---

## The rules this shop runs on

- **Today is `desk.date_today`** (2026-08-31), not the real date. Overdue is measured against it.
- **Vendor lead times come from the `vendors` table.** Never estimated.
- **A vendor will not ship while one of their invoices is unpaid.** This is what blocks ticket 101.
- **Cash only leaves.** No revenue is modelled, and a payment larger than the balance is refused rather than overdrawing it.
- **Only a human approves a payment.** No agent holds `record_payment`; `POST /approvals` requires an explicit confirmation and a human name, and the tool itself rejects agent names.
- **Nothing is sent.** No customer is emailed and no vendor is contacted — drafts stay on the board.
- **Nothing is invented.** A missing row returns `found: false` and omits the data fields entirely, so there is no fabricated zero to read.

---

## Notes

`backend/` contains a few modules the file list in the assignment does not name
individually but which the app imports to run: `settings.py` (the one place the
model name lives), `agents.py` (the five agents and their delegation wiring),
`audit.py` (the append-only trail), `expectations.py` (the Problem 6 plan, used
to score each run) and three command-line entry points — `run_team.py`,
`verify_team.py` and `approve_payment.py`. `backend/prompts/_shared_rules.md`
holds the house rules appended to all five agent prompts.
