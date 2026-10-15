# Campus Customs MCP Server

## What it is for

This is the only way the HW5 agents touch the shop's data. Rather than letting
each agent open the database and write its own SQL, every lookup goes through a
named tool defined here. That buys three things:

- **One source of truth.** Each agent sees the same numbers for the same ticket.
- **No invented data.** The tools return only what is in a row. When a row does
  not exist they return `found: false` with a reason, and where the database has
  no answer at all they return that gap as a flag so the agent escalates instead
  of guessing.
- **One place to put the safety rules.** The human-approval rule for payments is
  enforced here, in the tool, not left to a prompt.

Built with [FastMCP](https://github.com/jlowin/fastmcp).

## Which database it uses

    data/campus_customs_new.db

This is the working copy. `data/campus_customs.db` is the pristine original and
is never opened by this server, so it stays clean to diff against.

Connections are **read-only by default**. Exactly one tool (`record_payment`)
opens the database for writing, and only after a human has approved.

One detail worth knowing: **the clock lives in the database.** The shop's
current date is `desk.date_today` (2026-08-31), not the real system date. Every
tool that reports "due in N days" or "overdue" measures against the desk date.

## The eleven tools

### Reading the work queue

| Tool | Table(s) | What it answers |
|---|---|---|
| `list_open_tickets()` | `tickets` | Everything still open, with the link fields that say which other tables each ticket touches. |
| `get_ticket(ticket_id)` | `tickets` | One ticket in full, including the free-text `notes` where the real ask often lives. |

### Stock and restocking

| Tool | Table(s) | What it answers |
|---|---|---|
| `check_stock(sku, size, qty_needed)` | `inventory` | Units on hand for that exact SKU-and-size row, with `can_fill` and `shortfall`. Stock is keyed `(sku, size)`, so a SKU alone can never say whether an order ships. If the size is not carried, it lists the sizes that are — without inventing one. |
| `find_restock_vendor(sku)` | `vendors`, `invoices` | Every vendor with specialty and lead time, fastest first, plus any prior invoice naming that SKU. The schema records **no** SKU-to-vendor mapping, so the tool returns the evidence rather than asserting a match. |

### Money — reading and drafting

| Tool | Table(s) | What it answers |
|---|---|---|
| `get_price_and_margin(sku, qty)` | `pricing`, `inventory` | Unit cost, list price, per-unit and order margin. Deliberately proposes **no** discount: it returns `discount_authority_in_database: false`, because no policy or approval table exists. |
| `get_invoice(invoice_id)` | `invoices`, `vendors` | One vendor bill with its vendor and lead time, and whether it is overdue against the desk date. |
| `get_cash_position()` | `cash_accounts`, `invoices`, `leases`, `payments` | Cash on hand against every known claim on it, and what would be left if all were paid. |
| `get_lease_payment(lease_id)` | `leases`, `desk` | The rent the lease actually records, the due date, and days remaining. A rent email is a claim; this is the source. |
| `prepare_payment(kind, ref_id)` | `invoices` or `leases`, `cash_accounts` | **Drafts** a payment. Writes nothing. The amount is read from the source row, never supplied by the caller, so a draft cannot be inflated by whoever asks for it. Always returns `requires_human_approval: true`. |
| `prepare_purchase_order(sku, size, qty, vendor_id)` | `vendors`, `pricing`, `inventory`, `cash_accounts` | **Drafts** a restock order with cost and arrival date from the vendor's lead time. Writes nothing, contacts nobody. |

### Money — the one tool that writes

| Tool | Table(s) | What it does |
|---|---|---|
| `record_payment(kind, ref_id, human_approved, approved_by)` | **writes** `payments`, `cash_accounts`, `invoices` | Executes a payment a human has already approved. |

`record_payment` is the only writing tool in the server, and it refuses unless:

- `human_approved` is true, **and**
- `approved_by` names a person — any agent name (`boss`, `accounting`, `ai`,
  `assistant`, …) is rejected outright, **and**
- the invoice is not already paid, and the balance covers the amount.

**No agent is given this tool.** It is filtered out of every agent's toolset in
`backend/agents.py`, so the restriction holds even if a prompt is ignored.
Agents prepare; a human runs `backend/approve_payment.py`.

The write is one transaction: the `payments` row, the cash decrement and the
invoice status move together, because the schema has no trigger linking them.

## Running it

Registered in the project-root `.mcp.json` as `campus-customs`.

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

```bash
.venv/bin/python mcp_server/server.py          # stdio
.venv/bin/python mcp_server/server.py --http   # http://127.0.0.1:8003/mcp
```

Port 8003 avoids the Outlook MCP already on 8002.

## Testing

```bash
.venv/bin/python mcp_server/smoke_test.py
```

Drives every ticket-facing tool over a real MCP session and checks each returned
value against the database with independent SQL. Writes `output/mcp_smoke.json`.
