# HW5 Harness — Campus Customs Back Office

Working notes for the agents we build in this homework. Section 1 is the database study from Problem 2. Later problems add models, tools, safety and specs.

---

## 1. The Database

**File:** `data/campus_customs.db` — the read source of truth.
**Copy:** `data/campus_customs_new.db` — byte-identical to the original right now (same MD5, `46effb90d8811f03e219ea9b5fbdfa5a`, all nine tables matching row for row). This is the file later problems write to, so the original stays clean as a reference to diff against.

This is **not** the HW4 storefront database. HW4 was the customer-facing shop (catalogue, product images, user logins, chat). HW5 is the **back office**: the money, the stock room, the landlord, the vendors and the work queue. The agents here act on behalf of the shop, not the shopper.

It is deliberately tiny — 9 tables, 24 rows total — so every agent decision is checkable by hand.

| Table | Rows |
|---|---|
| `desk` | 1 |
| `cash_accounts` | 1 |
| `vendors` | 3 |
| `leases` | 1 |
| `invoices` | 1 |
| `pricing` | 4 |
| `inventory` | 10 |
| `tickets` | 3 |
| `payments` | 0 |

`PRAGMA foreign_key_check` returns clean — every declared foreign key resolves.

---

### 1.1 Tables and fields

#### `desk` — what day it is
*Why it matters: it is the agent's clock; "overdue" and "due soon" are meaningless without it, and it must never read the real system date.*

| Field | Type | Why it matters |
|---|---|---|
| `date_today` | TEXT | The simulated current date (`2026-08-31`); every deadline is judged against this, not the wall clock. |
| `notes` | TEXT | Free-text scratch space for the day; currently empty. |

#### `cash_accounts` — what we can actually spend
*Why it matters: this is the hard constraint on every paying agent; no tool should ever approve a payment that drives this negative.*

| Field | Type | Why it matters |
|---|---|---|
| `name` | TEXT (PK) | Account identifier; only `checking` exists, so payments have exactly one source. |
| `balance` | REAL | $3,400.00 available — the ceiling on everything the agents can commit to. |
| `date` | TEXT | When the balance was last true (`2026-08-31`), so a stale figure is detectable. |

#### `vendors` — who can make more stock
*Why it matters: when stock is short, lead time decides whether a restock can beat a customer's deadline at all.*

| Field | Type | Why it matters |
|---|---|---|
| `id` | INTEGER (PK) | Target of `invoices.vendor_id`; links a bill to the supplier who sent it. |
| `name` | TEXT | Who the agent names in a reorder or a payment note. |
| `specialty` | TEXT | Routes a shortage to the vendor who can actually make that item. |
| `lead_days` | INTEGER | The promise-by math — 5, 3 and 1 days respectively. |

Rows: **1** Bulldog Print Co (apparel reprint, 5 days) · **2** Elm City Gifts (mugs and small goods, 3 days) · **3** QuickShip CT (local courier, 1 day).

#### `leases` — the fixed monthly obligation
*Why it matters: rent is the largest single claim on cash and it is non-negotiable, so it sets the floor the agent must reserve.*

| Field | Type | Why it matters |
|---|---|---|
| `id` | INTEGER (PK) | Target of `tickets.lease_id`. |
| `space_name` | TEXT | Which space — "Chapel Street shop". |
| `landlord` | TEXT | Elm City Properties — the counterparty, and the requester on ticket 102. |
| `monthly_rent` | REAL | $2,400.00 — 71% of all available cash. |
| `next_due` | TEXT | `2026-09-02` — **2 days out**. |
| `notes` | TEXT | Terms or exceptions; empty. |

#### `invoices` — what vendors are owed
*Why it matters: an unpaid invoice is both a cash claim and, here, the thing blocking a customer order from being fillable.*

| Field | Type | Why it matters |
|---|---|---|
| `id` | INTEGER (PK) | Target of `tickets.invoice_id`. |
| `vendor_id` | INTEGER (FK→`vendors.id`) | Who to pay. |
| `amount` | REAL | $840.00 — the cash impact. |
| `due_date` | TEXT | `2026-08-28` — **3 days overdue** as of the desk date. |
| `status` | TEXT | `open`; the flag that says this still needs action. |
| `description` | TEXT | "Rush reprint CC-TEE-WHITE S" — ties the money back to a specific SKU and size. |

#### `pricing` — cost and list price per SKU
*Why it matters: it is the only basis for judging a discount request; without unit cost, "20% off" is a guess rather than a margin decision.*

| Field | Type | Why it matters |
|---|---|---|
| `sku` | TEXT (PK) | Joins to `inventory` and to `tickets.sku`. |
| `unit_cost` | REAL | What we pay — the floor below which a discount loses money. |
| `list_price` | REAL | What we charge — the starting point for any override. |

| SKU | Unit cost | List | Margin | Margin % |
|---|---|---|---|---|
| CC-HOOD-NAVY | $22.00 | $58.00 | $36.00 | 62.1% |
| CC-TEE-WHITE | $8.00 | $28.00 | $20.00 | 71.4% |
| CC-HAT-BLUE | $6.00 | $22.00 | $16.00 | 72.7% |
| CC-MUG-CREST | $3.50 | $14.00 | $10.50 | 75.0% |

#### `inventory` — physical stock by SKU and size
*Why it matters: it is the yes/no on whether an order can be filled today, and both stock-related tickets fail that test.*

| Field | Type | Why it matters |
|---|---|---|
| `sku` | TEXT (PK part) | Product identifier shared with `pricing` and `tickets`. |
| `name` | TEXT | Human label for replies. |
| `size` | TEXT (PK part) | Stock is per size — SKU alone never answers "can we ship it". |
| `qty` | INTEGER | Units on hand; `0` means the order cannot be filled from stock. |
| `location` | TEXT | Aisle for picking. |

Primary key is `(sku, size)`. **Two of ten rows are at zero: CC-TEE-WHITE S and CC-MUG-CREST OS.** Note `pricing` has 4 SKUs and `inventory` covers all 4 — no orphans in either direction.

#### `tickets` — the work queue
*Why it matters: this is the agents' inbox; each row is one decision to make, and its nullable link fields say which other tables that decision has to touch.*

| Field | Type | Why it matters |
|---|---|---|
| `id` | INTEGER (PK) | Stable handle for logging what the agent decided. |
| `type` | TEXT | The router key — decides which agent/skill handles it. |
| `requester` | TEXT | Who is waiting on the answer. |
| `subject` | TEXT | One-line summary. |
| `sku` | TEXT (nullable) | Set on stock-related tickets; joins to `inventory`/`pricing`. |
| `size` | TEXT (nullable) | Needed with `sku` to hit the right inventory row. |
| `qty` | INTEGER (nullable) | How many — compared against `inventory.qty`. |
| `lease_id` | INTEGER (nullable, FK→`leases.id`) | Set on rent tickets. |
| `invoice_id` | INTEGER (nullable, FK→`invoices.id`) | Set when a vendor bill is involved. |
| `status` | TEXT | `open` / resolved — stops the agent reworking a finished ticket. |
| `notes` | TEXT | The requester's own words, including asks not captured by any column (e.g. "asking for a bulk discount"). |
| `created_at` | TEXT | ISO-8601 with `-04:00` offset; orders the queue. |

The three link columns are mutually exclusive in practice — **a ticket's type determines which ones are populated**, and that pattern is how the agent knows what to look up.

#### `payments` — the money actually spent
*Why it matters: it is empty, so it is the write target and the audit trail — every payment an agent approves should land here, and right now nothing has been paid.*

| Field | Type | Why it matters |
|---|---|---|
| `id` | INTEGER (PK) | One row per payment made. |
| `kind` | TEXT | What was paid (invoice, rent, …) — pairs with `ref_id`. |
| `ref_id` | INTEGER (nullable) | The id in the table named by `kind`; **no FK constraint**, so the agent must set it correctly itself. |
| `amount` | REAL | Must be subtracted from `cash_accounts.balance`. |
| `account` | TEXT | Which account paid — only `checking` exists. |
| `paid_at` | TEXT | When; should come from `desk.date_today`, not the real clock. |
| `approved_by` | TEXT | **The accountability field** — names the human or agent who authorised it. |

`kind` + `ref_id` is a loose polymorphic pointer with nothing enforcing it. That is the weakest spot in the schema and worth guarding in the tool layer.

---

### 1.2 The three open tickets

All three are `status = 'open'`, all created on the desk date `2026-08-31`, and each is a **different type with a different link pattern** — together they're a deliberate sample of the three jobs the agents must handle.

#### Ticket 101 — `customer_order` — "Bulldog tee" (Tauhid Zaman, 09:15)
> *"Needs a tee in size S."*

**Links:** `sku='CC-TEE-WHITE'` + `size='S'` → `inventory` (and `pricing`) · `invoice_id=501` → `invoices` → `vendor_id=1` → `vendors`.

This is the only ticket that reaches **three** tables deep, and the only one linking stock to money:

```
ticket 101 ──sku+size──> inventory (CC-TEE-WHITE, S) ── qty = 0
           ──sku───────> pricing   (cost $8, list $28)
           ──invoice_id─> invoice 501 ($840, due 2026-08-28, open)
                             └──vendor_id──> vendor 1 (Bulldog Print Co, 5 lead days)
```

**The catch:** the customer wants 1 unit; on-hand is **0**. The fix is already in flight — invoice 501 *is* the rush reprint of exactly this SKU and size — but that invoice is **3 days overdue and unpaid**, and the vendor's lead time is **5 days**. So the answer to the customer depends on whether the shop pays vendor 1, and the earliest honest promise date is five days after payment clears, not today.

#### Ticket 102 — `rent_notice` — "Rent due" (Elm City Properties, 11:05)
> *"Email: shop rent due in 2 days."*

**Links:** `lease_id=1` → `leases`. No SKU, no size, no qty, no invoice — the simplest shape in the table.

```
ticket 102 ──lease_id──> lease 1 (Chapel Street shop, $2,400.00, next due 2026-09-02)
                            └── landlord = Elm City Properties = the requester
```

**The catch:** the requester string equals `leases.landlord`, so the ticket is self-corroborating — but it arrived as an *email*, and nothing in the schema proves the email is genuine. The amount must be taken from `leases.monthly_rent`, never from the email body. The note's "in 2 days" checks out exactly against `next_due` minus `date_today`.

#### Ticket 103 — `price_override` — "Bulk hoodie discount" (Yale AI Club, 16:55)
> *"Student org wants 20 hoodies, size M, asking for a bulk discount."*

**Links:** `sku='CC-HOOD-NAVY'` + `size='M'` → `inventory` and `pricing`. **No `lease_id`, no `invoice_id`** — nothing authorises the discount, because the authority doesn't exist in the data.

```
ticket 103 ──sku+size──> inventory (CC-HOOD-NAVY, M) ── qty = 8, wants 20
           ──sku───────> pricing   (cost $22, list $58, margin 62.1%)
```

**The catch:** two separate problems in one ticket. First, size M has **8 units against a request for 20** — short by 12, and the other 24 hoodies in stock are S/L/XL, which is the wrong size. Second, the discount ask lives **only in the free-text `notes`** — there is no percentage field, no approval column, and no row anywhere that grants price-override authority. At list, the order is $1,160; at cost it is $440, so there is room to discount, but deciding how much is a judgement the database cannot make for the agent.

---

### 1.3 What the three tickets add up to

The tickets are not independent — they compete for the same $3,400:

| Claim | Amount | Deadline | From |
|---|---|---|---|
| Invoice 501 (vendor 1) | $840.00 | 2026-08-28 — **3 days overdue** | ticket 101 |
| Rent (lease 1) | $2,400.00 | 2026-09-02 — **2 days out** | ticket 102 |
| **Total committed** | **$3,240.00** | | |
| Cash on hand | $3,400.00 | | `cash_accounts` |
| **Remaining** | **$160.00** | | |

Both obligations *can* be paid — with **$160.00**, about 4.7% of the balance, left over. There is no slack for a third commitment, and `payments` is empty, so none of this has been paid yet.

That is the designed tension for the rest of the homework: ticket 103 asks the shop to discount a 20-unit order it cannot fill from stock, at a moment when nearly all its cash is already spoken for, and restocking it would mean a new bill on top of the $3,240.

### 1.4 Things to guard in the tool layer

Noted now because they shape later problems:

1. **`payments.ref_id` has no foreign key.** Nothing stops an agent writing a payment against invoice 999. Validate before insert.
2. **The clock is in the database.** `desk.date_today` is 2026-08-31; any tool calling the real system date will compute the wrong deadlines.
3. **Paying does not update the balance.** No trigger links `payments` to `cash_accounts.balance` — whatever writes a payment must also decrement cash, or the two tables drift apart.
4. **Nothing in the schema expresses authority.** No approval limits, no role table. `payments.approved_by` is a free-text string, so the discipline about who may approve what has to live in the agent layer, not the data.
5. **Neither stock ticket can be filled from inventory** (101 short by 1, 103 short by 12). An agent that only reads `pricing` and skips `inventory` will happily promise goods that do not exist.

---

## 2. The MCP Server

**Location:** `mcp_server/server.py` · **Framework:** FastMCP · **Database:** `data/campus_customs_new.db` (the working copy; the pristine `campus_customs.db` is never opened by the server).

Every agent in this homework reaches the shop's data through this server and nowhere else. One source of truth per ticket, one place to add safety later, and no agent writing its own SQL.

**Why these three tools.** The database has exactly three open tickets, each of a different type, and each blocked on a different question the agent cannot answer from the ticket row alone. So the mapping is strictly **one tool per ticket, and one ticket per tool** — each tool is scoped to the single question its ticket actually asks:

### 2.1 The three tools

| Tool | Reads | Unlocks | Why this is the right tool for that ticket |
|---|---|---|---|
| `check_stock(sku, size, qty_needed)` | `inventory` | **101** | Ticket 101 asks for CC-TEE-WHITE in size **S**, and stock is keyed `(sku, size)` — so only a size-level lookup can answer whether the tee ships today. It returns 0 on hand, `can_fill: false`, shortfall 1. |
| `get_lease_payment(lease_id)` | `leases` (+ `desk` for the date) | **102** | Ticket 102 is an *email* claiming rent is due, and an email is a claim, not a source — this tool returns the $2,400.00 the lease itself records, due 2026-09-02, 2 days out, so the agent pays the lease and not the figure in the message. |
| `get_price_and_margin(sku, qty)` | `pricing` (+ `inventory` for the name) | **103** | Ticket 103 asks for a bulk discount with no percentage and no authority anywhere in the data, so the tool supplies the floor ($22 cost) and ceiling ($58 list) the decision needs — $1,160 at list for 20 units, $720 of margin to spend — and refuses to pick a number itself. |

### 2.2 Two rules the tools enforce

**Nothing is invented.** Every figure returned comes from a row. A missing row returns `found: false` plus a reason, never a guess — and the two kinds of miss are distinguished, because the agent needs to tell them apart:

| Call | Response |
|---|---|
| `check_stock("CC-HAT-BLUE", "M")` | `found: false`, *"No inventory row for CC-HAT-BLUE in size M"*, `sizes_carried: ["OS"]` |
| `check_stock("CC-FAKE-999", "M")` | `found: false`, *"No inventory rows exist for SKU CC-FAKE-999"*, `sizes_carried: []` |
| `get_lease_payment(99)` | `found: false`, *"No lease with id 99"* |
| `get_price_and_margin("CC-FAKE-999")` | `found: false`, *"...cost and list price are unknown"* |

Where the database has no answer *at all*, the gap is returned as a flag rather than silently filled: `get_price_and_margin` always returns `discount_authority_in_database: false`, because no discount policy and no approval table exist anywhere in the schema. This is guard #4 from section 1.4, now enforced in code.

**The clock comes from the database.** `desk.date_today` is 2026-08-31; the real system date is ignored entirely. This is guard #2 from section 1.4. `get_lease_payment` computes `days_until_due` by SQL `julianday` against the desk row, so every agent measures deadlines against the same simulated day.

### 2.3 Design decisions

- **Read-only connection** (`file:...?mode=ro`). All three tools only read, and a write attempt raises `attempt to write a readonly database`. The helper takes `readonly=False` for the write tools that come later, so the opt-in to writing will be explicit and visible in the diff.
- **Missing file raises, not creates.** SQLite would happily create an empty database from a wrong path and hand the agent an empty shop that looks like real data. The connection helper checks the file exists first.
- **Connections always close**, via a `@contextmanager` — `with sqlite3.connect(...)` alone commits but leaves the handle open, which would leak one connection per tool call.
- **Parameterised SQL everywhere**; no string interpolation of agent-supplied values.
- **Port 8003** for HTTP mode, avoiding the Outlook MCP on 8002.

### 2.4 Verified against the real tickets

Logic checked by calling each tool against `campus_customs_new.db`. Every figure matches section 1:

| Call | Result |
|---|---|
| `check_stock("CC-TEE-WHITE", "S", 1)` | `qty_on_hand: 0`, `can_fill: false`, `shortfall: 1`, Aisle B |
| `get_lease_payment(1)` | `$2,400.00`, due `2026-09-02`, `as_of: 2026-08-31`, `days_until_due: 2` |
| `get_price_and_margin("CC-HOOD-NAVY", 20)` | cost $22 / list $58, margin 62.1%, `$1,160.00` at list, `$440.00` at cost |

Both database files were byte-identical before and after (MD5 unchanged), confirming the read-only path writes nothing.

**Still unservable by these three tools, by design:** ticket 101's full answer also depends on invoice 501 and vendor 1's 5-day lead time, and no tool reads `invoices`, `vendors`, `cash_accounts` or `payments` yet. Those arrive with the later problems.

---

## 3. Connecting and Testing the MCP Server

### 3.1 Registration

The server is registered in `.mcp.json` **at the project root**, alongside the `yale-som-courses` and `outlook` servers already there, following the same absolute-path convention:

```json
"campus-customs": {
  "command": ".../HW5/.venv/bin/python",
  "args": [".../HW5/mcp_server/server.py"]
}
```

Dependencies live in `HW5/.venv` (FastMCP 4.1.0), kept separate from the `mcp_servers/.venv` used by the Outlook server.

**One operational note:** Claude Code reads `.mcp.json` at startup, so the `campus-customs` tools become callable in the chat window on the next launch (the new project server needs approving once). The smoke test below therefore does not wait on that — it drives the server over the same stdio MCP protocol the editor uses, from a script.

### 3.2 How the tools were tested

`mcp_server/smoke_test.py` spawns `server.py` as a subprocess and talks to it with an MCP client. This is a real protocol round trip — `list_tools` then `call_tool` — not a Python import of the functions, so it exercises the tools exactly as an agent reaches them.

Every value returned is then re-read from `data/campus_customs_new.db` with **independent SQL** and compared field by field. A call passes only if the tool and the database agree on every field.

Evidence: **[`output/mcp_smoke.json`](mcp_smoke.json)**.

### 3.3 Results

Discovery returned all three tools: `check_stock`, `get_lease_payment`, `get_price_and_margin`.

| Ticket | Prompt asked | Tool | Key output | Fields checked |
|---|---|---|---|---|
| **101** | *"Tauhid Zaman wants a Classic Bulldog Tee in size S. Can we ship it today?"* | `check_stock` | `qty_on_hand: 0`, `can_fill: false`, shortfall 1, Aisle B | 5 ✓ |
| **102** | *"We got an email saying the shop rent is due. How much do we actually owe on lease 1?"* | `get_lease_payment` | `$2,400.00`, due `2026-09-02`, `as_of: 2026-08-31`, 2 days out | 7 ✓ |
| **103** | *"Yale AI Club wants 20 navy hoodies in M with a bulk discount. Cost, list, margin?"* | `get_price_and_margin` | cost $22 / list $58, `$1,160.00` at list, `$440.00` at cost, `discount_authority_in_database: false` | 7 ✓ |

Three tickets, three tools, one call each — the test asserts this 1:1 mapping (`tool_ticket_mapping.is_one_to_one`) and fails if a ticket is ever served by a second tool.

**19 field-level comparisons, all matching the database.** Two are worth singling out:

- `as_of` was checked against `desk.date_today` specifically, confirming the tool reports 2026-08-31 and not the real system date.
- `discount_authority_in_database: false` was verified by querying `sqlite_master` for any table whose name resembles an approval, discount or policy table. There are none, so the flag is grounded in the schema rather than hard-coded optimism.

### 3.4 The never-invent rule, tested

Four calls for data that is not in the database. All four flagged the gap instead of filling it:

| Prompt asked | Tool | Result |
|---|---|---|
| *"Do we have a blue cap in size M?"* | `check_stock` | `found: false` — and `sizes_carried: ["OS"]` matched the sizes actually in the table |
| *"How many CC-FAKE-999 in size M?"* | `check_stock` | `found: false`, no `qty_on_hand` field invented |
| *"What is the rent on lease 99?"* | `get_lease_payment` | `found: false`, no `amount_due` field invented |
| *"What does CC-FAKE-999 cost?"* | `get_price_and_margin` | `found: false`, no `list_price` field invented |

The absent fields matter as much as the flag: a caller cannot read a fabricated zero out of these responses, because the key is not there at all.

### 3.5 Database integrity

MD5 of `campus_customs_new.db` identical before and after the run (`46effb90d8811f03e219ea9b5fbdfa5a`), confirming the read-only connection wrote nothing. The file still matches the pristine `campus_customs.db` — the working copy stays untouched until a later problem starts writing to it.

**All checks passed:** 3/3 ticket calls match the database, 19/19 field comparisons, 4/4 never-invent checks, 1:1 tool-to-ticket mapping confirmed, database unchanged.

---

## 4. The Agent Team

**Framework:** PydanticAI · **Model:** `gpt-6-luna` for every agent, through Portkey · **Data:** only via the `campus-customs` MCP server.

The model name appears exactly once in the codebase — `backend/settings.MODEL_NAME` — so no second model can drift into a run, and every run asserts at the end that the set of models used is exactly `{gpt-6-luna}`. The Portkey key is read from the root `.env` and never hard-coded.

There is deliberately **no second tools layer**: no agent opens the database directly. Everything an agent says is traceable to an MCP call recorded in the audit trail.

### 4.1 The five agents

| Agent | Job | Prompt | MCP tools it leans on |
|---|---|---|---|
| **Boss** | Reads each ticket, routes it to one specialist with a short courteous brief, and makes the final call. Never approves payments — recommends them to a human. | `backend/prompts/boss.md` | `get_ticket`, `list_open_tickets` |
| **Inventory** | Checks stock by SKU **and size**, names the shortfall in units, finds who can restock and how fast, and drafts the wording of the vendor request with the date it is needed by. | `backend/prompts/inventory.md` | `check_stock`, `find_restock_vendor` |
| **Accounting** | Watches cash and invoices, checks margins, and prepares payments and purchase orders as **drafts** for a human to approve. Cannot execute a payment — it does not hold the tool. | `backend/prompts/accounting.md` | `get_cash_position`, `get_invoice`, `get_price_and_margin`, `prepare_payment`, `prepare_purchase_order` |
| **Facilities** | Looks after the shop space — lease, rent, landlord. Warm and a little fun in tone, never at the expense of a number or a date. Reads the lease, not the email. | `backend/prompts/facilities.md` | `get_lease_payment` |
| **Customer Service** | Drafts what the customer reads, in an elegant and genuinely appreciative voice. Never invents a date, discount or policy. | `backend/prompts/customer_service.md` | `get_ticket`, `check_stock` |

`backend/prompts/_shared_rules.md` is appended to all five system prompts, so the house rules are stated identically to everyone rather than drifting per agent.

### 4.2 Connectivity and the agent loop

The delegation graph is **complete**: each agent holds an `ask_<role>` tool for each of the other four — 20 delegation tools, registered programmatically so the graph cannot be miswired by hand. A specialist can go straight to another specialist without the Boss in the chain; this is verified live, not just asserted (§4.5).

Two guards stop full connectivity from becoming a loop:

1. **A hop budget** (`MAX_DELEGATION_HOPS = 3`) shared across one ticket. At zero, further delegation is refused and the agent must answer with what it has.
2. **A call stack.** Delegating to an agent already working higher up the chain is refused, so A→B→A cannot happen.

Both refusals are themselves written to the audit trail, so a reader can see the guard fire rather than just seeing a chain stop.

Per-agent ceilings (`settings.AGENT_USAGE_LIMITS`): 8 requests, 10 tool calls, 120k tokens. Reasoning effort is set to `none` — required by this endpoint for function tools, and the right setting anyway for lookups this small.

### 4.3 Every MCP tool and the table it reads

Eleven tools. The three from Problem 3 plus eight added here.

| # | Tool | Tables used | Added | Who uses it |
|---|---|---|---|---|
| 1 | `list_open_tickets()` | `tickets` | P5 | Boss |
| 2 | `get_ticket(ticket_id)` | `tickets` | P5 | Boss, Customer Service |
| 3 | `check_stock(sku, size, qty_needed)` | `inventory` | P3 | Inventory, Customer Service |
| 4 | `find_restock_vendor(sku)` | `vendors`, `invoices` | P5 | Inventory |
| 5 | `get_price_and_margin(sku, qty)` | `pricing`, `inventory` | P3 | Accounting |
| 6 | `get_invoice(invoice_id)` | `invoices`, `vendors` | P5 | Accounting |
| 7 | `get_cash_position()` | `cash_accounts`, `invoices`, `leases`, `payments` | P5 | Accounting |
| 8 | `get_lease_payment(lease_id)` | `leases`, `desk` | P3 | Facilities |
| 9 | `prepare_payment(kind, ref_id)` | `invoices` / `leases`, `cash_accounts` | P5 | Accounting — **draft only** |
| 10 | `prepare_purchase_order(sku, size, qty, vendor_id)` | `vendors`, `pricing`, `inventory`, `cash_accounts` | P5 | Accounting — **draft only** |
| 11 | `record_payment(kind, ref_id, human_approved, approved_by)` | **writes** `payments`, `cash_accounts`, `invoices` | P5 | **No agent. Humans only.** |

Every tool reads `desk` when it needs the date. Tools 1–10 open the database read-only; only 11 can write.

### 4.4 Safety

**Agents cannot lie or invent.** Every fact an agent states must come from an MCP tool result in its own conversation. The tools make this enforceable rather than aspirational: a missing row returns `found: false` with a reason and *omits* the data fields entirely, so there is no fabricated zero to read. Where the database has no answer at all — there is no discount policy and no approval authority anywhere in the schema — the tool returns that gap as an explicit flag (`discount_authority_in_database: false`) and the agent must escalate. `SpecialistReport.facts_used` requires each agent to name the tool behind each figure, and `blocked_on_missing_data` gives it a place to report a gap instead of filling one.

**Agents cannot mock each other's reasoning.** The shared rules instruct every agent to assume good faith, never to belittle or second-guess a colleague's reasoning, and to take a disagreement to the Boss with evidence rather than ridicule. Structured outputs help here too: specialists report findings and a recommendation, not commentary on each other.

**Agents cannot be unkind to each other.** Delegation is written as asking a colleague for help — each `ask_<role>` tool tells the caller to be kind and specific and to say what they need and why. Facilities is explicitly warm and a bit of fun; Customer Service is elegant and appreciative; the Boss asks rather than orders.

**Agents take information only from the database.** The MCP server is the sole data path. No agent has a direct database connection, a web tool, or any other source, and the shared rules state that outside knowledge about prices, vendors or retail in general does not apply here.

**Only a human approves a payment.** This is enforced in three independent places, so no single failure undoes it:
1. `record_payment` refuses unless `human_approved` is true **and** `approved_by` names a person — any agent name is rejected by the tool itself.
2. The tool is **filtered out of every agent's toolset**, so an agent cannot call it even if a prompt is ignored or injected.
3. Each run asserts afterwards that zero payments were executed by agents, and fails loudly otherwise.
Agents produce drafts; `backend/approve_payment.py` is the human path, and it shows the draft and requires typed confirmation before writing.

**Agents are efficient with tokens.** These problems are small and the rules say so plainly: call the fewest tools that answer the question, never re-check a known fact, and keep answers to two or three sentences. Reasoning effort is off, outputs are small fixed structures rather than prose, usage ceilings are set per agent, and the Boss delegates to **one** specialist per ticket unless a second is genuinely required. In practice a ticket costs roughly 12k input and 500 output tokens.

### 4.5 What actually ran

Three runs, all appended to `output/audit_trail.json`.

**Tickets, routed and decided** — the Boss picked the right specialist for all three, unprompted:

| Ticket | Routed to | Decision |
|---|---|---|
| 101 `customer_order` | Inventory | Cannot fill today; the tee is out of stock and the order is blocked pending restock. |
| 102 `rent_notice` | Facilities | The email matches the lease: $2,400 due 2026-09-02. The lease is authoritative; no payment initiated. |
| 103 `price_override` | Accounting | $720 total margin at list on 20 hoodies. No discount policy or approval authority exists in the database, so no percentage was proposed — **awaiting human approval**. |

**Wiring verification** (`backend/verify_team.py`) — 13/13 checks passed:

- All five agents hold `ask_*` tools for all four peers (complete graph, not a star).
- The server exposes `record_payment`; the agents' toolset filters out exactly that one and keeps the other ten.
- The hop budget refuses when exhausted; re-entry into a busy agent is refused.
- **Inventory delegated straight to Customer Service with no Boss in the chain** — full connectivity proven live, not just in the tool list.
- Only `gpt-6-luna` appeared in any step.

The Customer Service draft from that run is worth quoting as evidence of the no-invention rule holding under pressure: it tells the customer the tee is unavailable, and says *"We don't yet have a restock date to share"* rather than inventing the five-day lead time it would have been easy to assume.

**Database untouched:** MD5 of `campus_customs_new.db` unchanged across all three runs; `payments` still empty and the balance still $3,400, because no human has approved anything yet.

### 4.6 Audit trail

`output/audit_trail.json` is append-only. Each run is an entry under `audit_trail.runs` with its own ordered `steps`; earlier runs are never rewritten, and a file that cannot be parsed is copied aside rather than replaced.

Each step records: step number, timestamp, which agent acted, the event type (`agent_run` / `tool_call` / `delegation` / `refusal`), the ticket, who asked, the instruction given, the tool name with its **actual arguments and actual result**, the agent's structured output, the model, and token counts.

Tool results are captured by intercepting the MCP call itself, so the trail holds what the tool really returned — not an agent's account of it. That is what makes a later audit able to catch an agent misreporting a number.

---

## 5. The Ticket Desk Page — Expected Plans

**File:** `output/desk_tickets.html` — a single self-contained page. No build step, no server, no external fonts or scripts: double-click it and it opens. Blue-and-white, five tabs.

Written **before** comparing against any run, so the expectations are a prediction rather than a description of what already happened.

### 5.1 The routing rule

The rule the page is built around: **the Boss calls the one specialist whose job the ticket actually is, then at most one more if the first cannot finish alone. Two agents, maximum.**

Sending every specialist to every ticket is a failure, not thoroughness — it burns tokens and dilutes ownership. So each ticket tab names not only who *should* be called but who should **not**, with the reason, since the second list is where the discipline actually shows.

### 5.2 Expected routing, by ticket

| Ticket | 1st | 2nd | Explicitly **not** called | Why not |
|---|---|---|---|---|
| **101** customer_order | **Inventory** | **Customer Service** | Facilities | It is a t-shirt, not the building. |
| | | | Accounting | No price is disputed and nothing is being spent. Invoice 501 is overdue and is Accounting's business, but it belongs in the cash queue — Inventory flags it to the Boss rather than the Boss sending a second money errand. |
| **102** rent_notice | **Facilities** | **Accounting** | Inventory | No SKU, no size, no stock. |
| | | | Customer Service | The landlord is not a customer; nobody is waiting on a reply. |
| **103** price_override | **Accounting** | **Customer Service** | Facilities | Nothing concerns the premises. |
| | | | Inventory | The item exists and is already priced; the ask is what it should cost. Size M *is* short of 20, and that is real — but it is a second conversation to have once a price is agreed, flagged by Accounting rather than delegated. |

### 5.3 Expected tools, by ticket

Only the tools the specific problem needs. The "not expected" column is the part that matters.

| Ticket | Expected | Not expected |
|---|---|---|
| **101** | `get_ticket`, `check_stock`, `find_restock_vendor` | `get_lease_payment`, `get_price_and_margin`, `get_cash_position`, `prepare_payment` |
| **102** | `get_ticket`, `get_lease_payment`, `get_cash_position`, `prepare_payment` | `check_stock`, `find_restock_vendor`, `get_price_and_margin` |
| **103** | `get_ticket`, `get_price_and_margin` | `get_lease_payment`, `check_stock`, `find_restock_vendor`, `prepare_payment` |

`record_payment` must never appear on any ticket — no agent holds it.

### 5.4 Expected outcomes

- **101** — 0 on hand, shortfall 1, cannot ship today. Bulldog Print Co is the vendor the evidence points to (invoice 501 names this SKU), 5-day lead. Customer Service drafts an honest reply that promises no date the tools have not given. **No human approval needed** — nothing is spent.
- **102** — the lease records $2,400.00 due 2026-09-02, two days out, and the email's claim matches it. Cash $3,400 covers it, leaving $1,000 before invoice 501. A drafted payment. **Human approval required.**
- **103** — cost $22, list $58, $1,160.00 at list for 20 units with $720.00 of margin available. No discount policy and no approval authority exist in the database, so Accounting returns the numbers and refuses to pick a percentage. **Human approval required.**

### 5.5 Page structure

Five tabs: **101**, **102**, **103**, **Cash**, **Reflection**.

Each ticket tab carries the ticket itself (type, requester, link fields, the verbatim notes), then an **Expected** section — routing, who not to call, tools expected and not expected, expected findings, expected outcome — and an empty **Actual** card reserved for after the agents run.

Cash and Reflection are deliberately blank, each marked "coming later" for a future problem.

### 5.6 Verified

33 automated checks, all passing:

- **Opens standalone:** zero `src`/`href` references and no `http://` or `https://` anywhere, so `file://` works on double-click.
- **Tabs:** five tabs, five panels, every tab maps to a panel, exactly one active at load.
- **Sections:** all three ticket tabs have an Expected section, an empty Actual placeholder, and a "who should not be called" list; Cash and Reflection have neither Expected nor Actual.
- **Every figure traced to the database:** rent $2,400.00 and due 2026-09-02, cash $3,400.00, hoodie cost $22.00 and list $58.00, order total $1,160.00, margin $720.00, tee 0 on hand, shop date 2026-08-31 — each compared against a live query.

**Not verified:** how the page looks when rendered. The desktop preview sandbox cannot read files under the homework folder — the same limitation recorded in HW4 — and no browser is connected to drive a `file://` URL. The markup and the facts are checked; the visual result is worth a glance on first open.

---

## 6. Backend Routes

**File:** `backend/main.py` · **Framework:** FastAPI · **Started from `backend/`:**

```
uvicorn main:app --reload --port 8000
```

Serving at `http://localhost:8000`, with interactive docs at `/docs`. CORS is open to the Vite dev ports (5173/5174) so the dashboard in the next problem can call it.

### 6.1 The routes

| Method | URL | What it does |
|---|---|---|
| `GET` | `/health` | Liveness for the dashboard: returns `ok`, the model in use, the database file, and the shop date. |
| `GET` | `/tickets` | All three tickets with `status` (`open` / `resolved`), `is_open`, and every link field the board needs. |
| `GET` | `/tickets/{id}` | One ticket, same shape. 404 if it does not exist. |
| `POST` | `/tickets/{id}/run` | Runs the agent team on that ticket and returns the decision, the agents involved, every tool actually called, the delegations, token cost — and a scorecard against the Problem 6 plan. |
| `GET` | `/events?limit=&ticket_id=` | Recent agent events newest first: what each agent said, and the real tool calls with their arguments and results. This is what the board polls to refresh. |
| `GET` | `/cash` | The current `cash_accounts` checking balance, with open invoices, rent owed, what would remain, and every payment made so far. |
| `POST` | `/approvals` | **The human click.** Approves a payment or purchase and actually changes cash. The only route in the API that moves money. |
| `POST` | `/reset` | Restores `campus_customs_new.db` from the pristine original for a fresh run. Does **not** wipe the audit trail. |

### 6.2 Routing obeys the Problem 6 plan, and proves it

`backend/expectations.py` holds the Problem 6 plan as data. It does two things the HTML page cannot:

1. **Carries the rule into the run.** The Boss's brief says to delegate to the single specialist whose job the ticket is, a second only if the first genuinely cannot finish, never more than two and never every specialist.
2. **Scores the run afterwards.** Every `/tickets/{id}/run` response includes `vs_expected`: whether the first specialist matched, whether the specialist budget held, and whether any forbidden agent or tool appeared.

All three tickets, run through the API:

| Ticket | Expected first | Actual | Tools called | Forbidden agents | Forbidden tools | `record_payment` |
|---|---|---|---|---|---|---|
| 101 | Inventory | **Inventory** ✓ | `get_ticket`, `check_stock` | none | none | never |
| 102 | Facilities | **Facilities** ✓ | `get_ticket`, `get_lease_payment` | none | none | never |
| 103 | Accounting | **Accounting** ✓ | `get_ticket`, `get_price_and_margin` | none | none | never |

**No ticket drew every specialist**, which was the thing to avoid. Worth noting honestly in the other direction: each run stopped after the *first* specialist rather than continuing to the planned second (Customer Service on 101 and 103, Accounting on 102). That is under-delegation against the plan, not over — within the rule, but short of it. The scorecard records it rather than hiding it, and it is the obvious thing for the Reflection tab to pick up.

### 6.3 Only a human moves cash

Enforced at four layers, each independent:

1. **No agent holds `record_payment`** — it is filtered out of every agent's toolset.
2. **`POST /approvals` requires `confirm: true`** — an explicit click, not a default.
3. **`record_payment` itself rejects agent names.** `approved_by` must be a person; `"Accounting"`, `"boss"`, `"ai"` and friends are refused by the tool.
4. **Every run asserts zero agent payments afterwards** and returns HTTP 500 if that is ever violated.

Verified end to end:

| Attempt | Result | Cash |
|---|---|---|
| `confirm: false` | 400 — *"confirm must be true. A payment needs an explicit human click."* | $3,400 unchanged |
| `approved_by: "Accounting"` | 400 — *"'Accounting' is an agent, not a human."* | unchanged |
| `approved_by: "boss"` | 400 — same | unchanged |
| `approved_by: "ai"` | 400 — same | unchanged |
| `invoice 999` | 400 — *"No invoice row with id 999."* | unchanged |
| **Genuine human approval of rent** | `paid: true`, payment id 1 | **$3,400 → $1,000** |

The successful case wrote the `payments` row and decremented `cash_accounts` in one transaction, and the amount came from the lease row rather than from the request body — approving means approving the obligation, not a number typed into the browser. That test payment was then rolled back with `/reset`.

**One honest limitation:** approving a *purchase order* records the approved order in the audit trail and nothing else, because this database has no `purchase_orders` table. No cash moves, which is also correct accounting — nothing is owed until the vendor invoices. The response says so explicitly rather than implying something was written.

### 6.4 Reset

`POST /reset` copies `data/campus_customs.db` over `data/campus_customs_new.db`. Verified: after approving a $2,400 rent payment and resetting, the working copy was **byte-identical to the original again** (MD5 `46effb90…`), balance back to $3,400, payments back to 0.

The audit trail is deliberately left alone — it is append-only, and erasing the record of what happened before a reset would defeat its purpose. The reset is itself appended to it as an event, so the trail shows the slate being cleaned rather than quietly skipping from one state to another.

### 6.5 Note on port 8000

Port 8000 was held by the HW4 Campus Customs API, still running from a week earlier. It was stopped with the user's approval so the HW5 backend could bind the port the assignment requires. HW4's server can be restarted from its own folder whenever needed; other local servers on 8010 and 8020 were left untouched.

---

## 7. Shop Rules

Six rules that govern the shop. Each is enforced in code, not just stated in a prompt, and each is listed at `GET /shop-rules` so the dashboard can show what it is operating under.

### 7.1 The rules and where each is enforced

| # | Rule | Enforced in |
|---|---|---|
| 1 | **`desk.date_today` is today.** Overdue is measured against it, never the real clock. | Every tool reads it and returns it as `as_of`; `_days_between` computes from it in SQL. |
| 2 | **Vendor lead times come from the `vendors` table.** Never estimated. | `find_restock_vendor` and `prepare_purchase_order` return `lead_days` and derive arrival dates from it. |
| 3 | **A vendor will not ship while one of their invoices is unpaid.** | `_vendor_block()`; `find_restock_vendor` flags blocked vendors; `prepare_purchase_order` **refuses** to draft for one. |
| 4 | **Not enough cash → the pay tool refuses. No negative balances.** | `record_payment` compares balance to amount and refuses with the shortfall; a post-write assertion re-checks `balance >= 0`. |
| 5 | **Cash only goes out.** No revenue is modelled. | `record_payment` refuses any amount ≤ 0 (which would credit the account) and asserts the balance strictly fell. |
| 6 | **Nothing is sent.** No customer email, no vendor contact — drafts stay on the board. | No agent holds any sending tool; the shared prompt forbids claiming anything was sent. |

Rule 7, procedural: **a full run resets the database first**, so tickets are always resolved from the same starting cash, stock and invoices. `POST /runs/all` does this by default.

### 7.2 Rule 3 is the one that changes an answer

Checked against the data, only one vendor is blocked — and it is the one that matters:

| Vendor | Lead | Open invoices | Owed | Can ship? |
|---|---|---|---|---|
| Bulldog Print Co | 5 days | 1 (#501) | $840.00 | **No — blocked** |
| Elm City Gifts | 3 days | 0 | — | Yes |
| QuickShip CT | 1 day | 0 | — | Yes |

Bulldog Print Co is the apparel reprinter, and invoice 501's description names `CC-TEE-WHITE S` — the exact item ticket 101 wants. So ticket 101's real chain is:

> 0 in stock → needs a reprint → only Bulldog Print Co can do it → **they will not ship while $840 is owed** → pay invoice 501 (human approval) → *then* the 5-day lead starts → earliest arrival **2026-09-05**.

The other two vendors can ship, but neither does apparel reprints, so being unblocked does not help.

**This changed the Problem 6 plan.** Ticket 101's expected second agent was Customer Service; it is now **Accounting**, because the ticket cannot be answered at all until the invoice question is settled. Customer Service is now marked **deferred rather than forbidden** — not wrong to involve, just premature, since a reply drafted before the restock is settled either says nothing new or risks promising a date the tools have not given. `expectations.py` scores deferred agents separately from forbidden ones.

### 7.3 Verified

| Rule | Test | Result |
|---|---|---|
| 1 | Tool `as_of` vs `desk.date_today` | both `2026-08-31`; real date (2026-10-14) ignored |
| 2 | Tool `lead_days` vs `vendors` table | 5/3/1 — all three match exactly |
| 3 | `find_restock_vendor("CC-TEE-WHITE")` | blocked: `["Bulldog Print Co"]`, able: the other two |
| 3 | `prepare_purchase_order(..., vendor_id=1)` | **refused** — *"will not ship while 1 unpaid invoice(s) totalling $840.00 remain open. Clear invoice 501 first."* |
| 3 | Same call for unblocked vendor 2 | drafts normally — $35.00, 3-day lead, arrives 2026-09-03 |
| 3 | `prepare_payment(invoice 501)` | reports `can_ship_now: false`, `can_ship_after_this_payment: true` |
| 4 | Balance set to $100, pay rent $2,400 | **refused** — *"balance $100.00 is less than $2,400.00… Shortfall $2,300.00"*; balance stayed $100, no payment row |
| 5 | Any payment ≤ 0 | refused — would credit an account that only ever pays out |
| 6 | Audit of every tool available to agents | 10 tools, none that send, email, order or contact |

After the overdraft test, `POST /reset` restored the database byte-identical to the original.

### 7.4 The full run, under the new rules

`POST /runs/all` — reset first, then all three tickets:

| Ticket | Agents (in the order they were asked) | Decision |
|---|---|---|
| **101** | Inventory → Accounting | *"cannot be filled today: size S is out of stock. Restocking is blocked until invoice 501 is paid; no restock order has been placed."* |
| **102** | Facilities | *"$2,400 due on 2026-09-02, matching the email's two-day timing. Recommend preparing a rent payment draft for human approval; no payment has been made."* |
| **103** | Accounting | *"Do not set a discount from the available records… $22 unit cost and $58 list price ($440 cost and $1,160 list for 20)."* |

Awaiting a human on all three: $840 for invoice 501 (101), $2,400 rent (102), and the discount decision (103). Cash stayed at **$3,400 with zero payments** — agents cannot move it.

Routing held: no forbidden agent or tool on any ticket, no ticket drew every specialist, `record_payment` never called. Total 58.7k input / 2.2k output tokens for the full run.

### 7.5 Two fixes the new rules forced

**The usage ceiling was too tight.** Ticket 101's correct chain is now longer — stock, vendor, blocked, invoice, draft payment — and the shared 8-request budget cut it off mid-run. Raised to 16 requests / 20 tool calls, and `UsageLimitExceeded` now returns HTTP 429 with the partial steps recorded, rather than crashing the route.

**Agent order was reported backwards.** The scorecard derived the order from when each agent *finished*, so a nested delegate (Accounting, called inside Inventory) appeared first and `first_matched` read `False` on a correctly-routed ticket. It now orders by when each agent was *asked*, from the delegation records. Ticket 101 reports `boss → inventory → accounting` and `first_matched: true`.

---

## 8. The Dashboard

**Folder:** `frontend/` · **Stack:** React 18 + Vite 5 + TypeScript (strict) · **Design notes:** [`output/design.md`](design.md)

```bash
cd frontend && npm install && npm run dev
```

Vite opens the board automatically. It tries port 5173 and steps up if busy — on this machine 5173–5175 are other course projects, so it lands on **5176**. The backend now accepts **any localhost origin** rather than a pinned port, so whichever Vite picks works without edits.

### 8.1 What the board does

| Requirement | How it is met |
|---|---|
| List all three tickets | Cards from `GET /tickets`, in Yale navy on white with the requester, type and a plain-English blurb. |
| Pick one and start the team | Each card has its own *Start the agent team* button → `POST /tickets/{id}/run`. |
| Shine on hover | A gold-white gradient sweeps across the card in 0.7s while it lifts 3px. |
| Show each agent saying/doing | The stage of five Handsome Dans, plus a live feed polling `GET /events` every 1.2s with each agent's words and every real tool call and its arguments. |
| Agents move | Four moods — idle, talking, working, done. The working Dan bounces, flaps its ears, moves its mouth and shows a "…" bubble; its seat lifts and warms. |
| Mark resolved with a checkmark | A new `mark_ticket_resolved` MCP tool writes `tickets.status`; the chip flips to **✓ resolved** and the card tints green. |
| Short summary per agent | One row per agent that acted: what they concluded, the tools they used as chips, and any customer draft quoted. |
| Human approves a pay | A gold card headed *"Dear human user, can you please approve?"* → `POST /approvals`. |
| Show checking balance, dropping after a pay | Masthead figure and a cash card from `GET /cash`; verified $3,400.00 → $1,000.00 after an approved rent payment. |

### 8.2 Handsome Dan, in CSS

Per the project rule, the mascots are **built in HTML and CSS, not generated images** — verified by asserting the rendered DOM contains no `<img>` and no `background-image: url(...)`.

One shared bulldog (cream head, floppy ears, heavy brow, underbite, navy collar with a gold tag) with the props of each job: **Boss** in a pinstripe suit and gold tie, **Accounting** in round wire glasses, **Inventory** in a green warehouse cap, **Facilities** in an orange hard hat, **Customer Service** on a headset with a red bow tie. Each has an `aria-label` so the stage is not silent to a screen reader, and the whole thing freezes under `prefers-reduced-motion: reduce`.

### 8.3 One backend change this needed

A ticket had no way to become `resolved`. Added `mark_ticket_resolved(ticket_id, resolved_by, summary)` to the MCP server — the 12th tool — and it is **filtered out of every agent's toolset** alongside `record_payment`, because an agent closing its own ticket is a self-assessment. The board calls it after a run finishes, and `POST /reset` puts tickets back to open.

### 8.4 Verified

Rendering could not be screenshotted — the preview sandbox cannot read under the homework folder and no browser is connected — so the board was mounted in **jsdom and driven against the live backend**, which tests more than a screenshot would.

**Build:** `tsc -b` clean under `strict` with `noUnusedLocals`; `vite build` succeeds (154 kB JS / 15 kB CSS).

**Render — 31 checks, all passing:** three ticket cards with the real subjects; the $3,400.00 balance fetched from `/cash`; five Dans each wearing the right props while sharing the bulldog base; no images; all mascots labelled; the navy/gold tokens, the hover shine, the serif/sans split and the reduced-motion block all present.

**Full interaction flow — clicked through end to end, with a real agent run:**

| Step | Result |
|---|---|
| Before | #102 open, no approval card, $3,400.00 |
| Click *Start the agent team* | Ticket breathes gold, "running…" appears |
| Run completes | Summary rendered, **✓ resolved** chip, card tinted, 2 agents reported with their tools, 25 events in the feed, done ✓ on the Dans |
| Approval card | Appears headed *"Dear human user, can you please approve?"*, states **$3,400.00 → $1,000.00**, button disabled until a name is typed |
| Type a name, approve | Button enables; **balance drops to $1,000.00**; the payment row shows the approver |
| *Reset shop* | Balance back to $3,400.00, #102 back to open, payment log cleared |

One assertion failed on the first pass — the confirmation flash — and it was the test racing the banner's own 5-second auto-dismiss, not a bug. Re-checked immediately after an action, the flash renders correctly.

### 8.5 Ports on this machine

| Port | Serving |
|---|---|
| 8000 | HW5 backend (FastAPI) |
| 5176 | HW5 dashboard (Vite) |
| 5173 | Lecture 11 tokenomics frontend — left running |
| 5174 | another course frontend — left running |
| 8010, 8020 | other course backends — left running |

Only the stale HW4 API on 8000 was stopped, with approval. Everything else was left alone, which is why CORS matches any localhost origin rather than a fixed port.

---

## 9. The Resolved Run

Three live runs driven from the dashboard by a human, from a database reset immediately beforehand. Every step appended to `output/audit_trail.json`, which now holds 30 runs and has never been wiped.

Full record: [`output/resolved_tickets.json`](resolved_tickets.json) · Board screenshots: [`output/resolved_board.html`](resolved_board.html) · Expected vs actual, per ticket: [`output/desk_tickets.html`](desk_tickets.html)

### 9.1 What happened

| Ticket | Agents (in order asked) | Tools used | Outcome | Human approved |
|---|---|---|---|---|
| **101** customer_order | Boss → **Inventory** → **Accounting** | `get_ticket`, `check_stock`, `find_restock_vendor`, `get_invoice`, `get_cash_position`, `prepare_payment` | 0 on hand; the only vendor who reprints it was blocked by unpaid invoice 501, so no restock could be ordered | **$840.00** invoice 501 |
| **102** rent_notice | Boss → **Facilities** | `get_ticket`, `get_lease_payment` | The lease is authoritative, not the email: $2,400.00 due 2026-09-02 | **$2,400.00** rent |
| **103** price_override | Boss → **Accounting** | `get_ticket`, `get_price_and_margin` | $720.00 margin at list on 20 units; **no discount chosen** — no policy or authority exists in the data | none — a pricing decision, not a payment |

**Routing held on all three.** The right specialist was first every time, no forbidden agent or tool appeared anywhere, no ticket drew every specialist, and `record_payment` was never called by an agent.

**Two tickets stopped one hop short of the plan.** 102 never reached Accounting (Facilities answered completely and recommended the draft instead of delegating it) and 103 never reached Customer Service (so no reply to the Yale AI Club was drafted). That is under-delegation, not over — the rule that carried the grading risk held — and it is recorded on each ticket's Actual section rather than smoothed over.

### 9.2 The money

| | | Change | Balance |
|---|---|---:|---:|
| | Starting, after reset | — | **$3,400.00** |
| 101 | Invoice 501 → Bulldog Print Co — unblocked the only vendor who could reprint the tee | −$840.00 | $2,560.00 |
| 102 | Rent → Elm City Properties, lease 1, due 2026-09-02 | −$2,400.00 | $160.00 |
| 103 | No movement — a discount request; money would come *in*, and none was granted | $0.00 | $160.00 |
| | **Ending** | **−$3,240.00** | **$160.00** |

$3,400.00 − $840.00 − $2,400.00 = **$160.00**, matching `cash_accounts.balance` in the working database, with two rows in `payments` totalling $3,240.00. Both were approved by a person through `POST /approvals`; **agents executed zero payments**.

### 9.3 The best evidence the safety rules held

Asked for a bulk discount with **$720.00 of margin visibly available**, Accounting returned the numbers and refused to pick a percentage, recording the reason in its own words: *"The database records no discount policy or approval authority and does not specify an allowable discount percentage."* The never-invent rule held at exactly the moment inventing something would have been most useful.

On 101, Inventory drafted the vendor request — *"Could you please restock 1 unit of CC-TEE-WHITE in size S, needed by 2026-09-05?"* — and stated plainly that **no restock request or order had been sent or placed**. The date in it is not invented: it is the desk date plus the vendor's recorded 5-day lead.

### 9.4 One bug the run exposed

The human's screenshots caught a display bug the automated tests had missed. After a payment went through, the approval card stayed on screen and priced itself from a *running total* rather than from the bill itself — so ticket 101 read *"Paying $0.00"*, and ticket 102 offered to pay rent a second time, showing a projected balance of **−$2,240.00**.

The database was never wrong: $160.00, two payments, no double charge. Only the display was. `GET /cash` now returns each obligation with its own amount and a `paid` flag, the card disappears once an obligation is settled, and the arithmetic can no longer go negative. Verified after the fix: all three tickets resolved, balance $160.00, no negative figure, no approval card on a paid ticket.

The screenshots were kept as taken rather than retaken, and `resolved_board.html` says what they show and what was fixed afterwards.

---

## 10. Reference

Everything this harness covers, in one place.

### 10.1 Database — `data/campus_customs_new.db`

Nine tables (§1). `desk` holds the clock; `cash_accounts` the money; `vendors`, `leases`, `invoices`, `pricing`, `inventory` the shop; `tickets` the work queue; `payments` the record of what was spent. `data/campus_customs.db` is the pristine original, used only to reset.

### 10.2 MCP tools — twelve, in `mcp_server/server.py`

| Tool | Tables | Who |
|---|---|---|
| `list_open_tickets` | `tickets` | Boss |
| `get_ticket` | `tickets` | Boss, any specialist |
| `check_stock` | `inventory` | Inventory, Customer Service |
| `find_restock_vendor` | `vendors`, `invoices` | Inventory |
| `get_price_and_margin` | `pricing`, `inventory` | Accounting |
| `get_invoice` | `invoices`, `vendors` | Accounting |
| `get_cash_position` | `cash_accounts`, `invoices`, `leases`, `payments` | Accounting |
| `get_lease_payment` | `leases`, `desk` | Facilities |
| `prepare_payment` | `invoices`/`leases`, `cash_accounts` | Accounting — draft only |
| `prepare_purchase_order` | `vendors`, `pricing`, `inventory`, `cash_accounts` | Accounting — draft only |
| `record_payment` | **writes** `payments`, `cash_accounts`, `invoices` | **no agent — humans only** |
| `mark_ticket_resolved` | **writes** `tickets` | **no agent — the board, after a run** |

Ten are read-only and available to agents. Two write, and both are filtered out of every agent's toolset.

### 10.3 The five agents

**Boss** routes and decides · **Inventory** stock, shortfalls, vendors and lead times · **Accounting** cash, invoices, margins, payment and purchase drafts · **Facilities** the lease, rent and landlord · **Customer Service** anything a customer reads. Prompts in `backend/prompts/`, one file per agent plus shared house rules. All five on `gpt-6-luna` through Portkey, with full peer-to-peer delegation bounded by a 3-hop budget and a re-entry guard.

### 10.4 API routes — `backend/main.py`, port 8000

`GET /health` · `GET /tickets` · `GET /tickets/{id}` · `POST /tickets/{id}/run` · `GET /events` · `GET /cash` · `POST /approvals` · `POST /reset` · `POST /runs/all` · `GET /shop-rules`

### 10.5 Dashboard — `frontend/`, Vite on 5176

React + Vite + TypeScript. Yale navy and white after the Yale Club of New York. Five Handsome Dans built in CSS, one per agent, who move while they work. Tickets shine on hover, flip to ✓ resolved, and show a per-agent summary. The human is asked *"Dear human user, can you please approve?"* and the balance drops when they do. Design notes in `output/design.md`.

### 10.6 Safety rules, and where each is enforced

| Rule | Enforcement |
|---|---|
| Agents cannot lie or invent | Tools return `found: false` and omit the fields entirely; gaps returned as flags (`discount_authority_in_database: false`); `facts_used` makes each agent cite its source |
| Agents take information only from the database | MCP is the sole data path; no agent has a database connection, a web tool, or any other source |
| Agents cannot mock each other's reasoning | Shared house rules; structured outputs carry findings, not commentary |
| Agents cannot be unkind to each other | Delegation is written as asking a colleague; each role has its own courteous voice |
| **Only a human approves a payment** | Agents do not hold `record_payment`; `POST /approvals` needs explicit confirmation; the tool rejects agent names; every run asserts zero agent payments |
| No overdraft, cash out only | `record_payment` refuses an unaffordable or non-positive amount and asserts the balance fell but stayed ≥ 0 |
| A vendor will not ship while owed | `find_restock_vendor` flags blocked vendors; `prepare_purchase_order` refuses to draft for one |
| Today is `desk.date_today` | Every tool reads it and returns `as_of`; deadlines computed from it in SQL |
| Lead times come from `vendors` | Returned as `lead_days`, never estimated |
| Nothing is sent | Agents hold no sending tool; prompts forbid claiming anything was sent; drafts stay on the board |
| Agents are token-efficient | Reasoning off, small structured outputs, per-agent ceilings, one specialist per ticket by default — about 12–30k tokens per ticket |
