# AI Prompts Log — HW5

This file records the prompts I type as a vibe coder. One section per problem, updated as we work. For each problem: the problem number and title, at least one prompt I typed, and a follow-up prompt where I needed one (with one sentence on what was lacking after the first).

## Problem 1 — Vibe Coder Prompts

**Prompt 1 (initial):**
> /folder-joke HW5

**Follow-up prompt:**
> Lets get started. Create AI_prompts.md and keep it updated as we work further in the homework. As in previous homeworks, this file is the log of what is typed to the vibe coder. Put one section for each problem. Each section must include: problem number and title; at least one prompt I typed; one follow-up prompt if was needed (and one sentence on what was lacking after the first)

**What was lacking:** The first prompt only set HW5 as the active workspace and proved it with a joke file; it did not yet ask for the prompt log or state what each section had to contain.

**Evidence:** [AI_prompts.md](AI_prompts.md) itself, which is the log this problem asked for, and [funny_joke.txt](funny_joke.txt), which proved the workspace.

## Problem 2 — Study the Campus Customs Database

**Prompt 1 (initial):**
> Problem 2: Study the campus customs database. open data/campus_customs.db and give me a summary of every table and its fields. Note that data/campus_customs_new.db is just a copy and in later problems we will update that copy. Specifically, tell me about the three open tickets and explain how they link to other tables. Start output/harness.md . For each table, list the fields and one short line on why that table is important for the agents. We will keep growing this harness file in later problems.

**Follow-up prompt:** None needed. The initial prompt named the database file, flagged the copy and its future role, called out the three open tickets and their links as the specific thing to explain, named the harness file to start, and set the per-table format (fields plus one short line on why the table matters for the agents).

**Evidence:** [harness.md](output/harness.md) section 1 — all nine tables, every field with a one-line reason, the three tickets traced to the tables they link to, and the row counts and totals read straight out of the database.

**What the data showed:** This is the back office, not the HW4 storefront — 9 tables, 24 rows total, covering cash, stock, vendors, the lease, invoices and a work queue. `data/campus_customs_new.db` is byte-identical to the original (same MD5), so it is a clean copy to write to later. `PRAGMA foreign_key_check` is clean. The three open tickets are one of each type with a different link pattern each: 101 `customer_order` reaches three tables deep (inventory + pricing + invoice 501 + vendor 1), 102 `rent_notice` links only to lease 1, and 103 `price_override` links to inventory and pricing with no authorising row at all.

**The tension the data sets up:** cash is $3,400; invoice 501 ($840, already 3 days overdue) plus rent ($2,400, due in 2 days) comes to $3,240, leaving $160. `payments` is empty, so nothing has been paid yet. Neither stock ticket can be filled from inventory — ticket 101 wants a size S tee and on-hand is 0 (invoice 501 is the reprint that would fix it, from a vendor with a 5-day lead time), and ticket 103 wants 20 hoodies in size M against 8 on hand.

**Five things written into the harness to guard later:** `payments.ref_id` has no foreign key; the clock lives in `desk.date_today` (2026-08-31) so tools must not read the system date; nothing links a payment to the cash balance, so whatever writes one must also decrement cash; no table expresses approval authority, so that discipline belongs in the agent layer; and an agent that reads `pricing` without `inventory` will promise goods that do not exist.

## Problem 3 — Build the MCP Server

**Prompt 1 (initial):**
> Thank you cc. Problem 3: Build the MCP server. Lets write an MCP server in mcp_server/ using FastMCP. It needs to talk to data/campus_customs_new.db . We do NOT need to connect or run it in this problem 3. Every agent in this homework uses the tools in this MCP server. We will add more tools to it later; for now write three tools only, that we will need for the tickets in the database, and give me a very short reasoning on why those tools. Lets keep the names clear. Never invent any data, and only use information in the database. If there is no information in the database, is ok to flag that, but again dont invent anythign. In output/harness.md , list each of the three MCP tools. For every tool include: which table it reads, which ticket it helps to unlock (either 101, or 102, or 103), and one very brief sentence on why that tool is the right one for that ticket. Please note that lines like "reads inventory" will score low, so lets tie the tool to the specific tool please. Also, lets add a short mcp_server/README.md file that explains what the MCP server is for, which database file it is using, and the three tools it has.

**Follow-up prompt:** None needed. The initial prompt named the folder and framework, the database file to target, the number of tools and that they should map to the tickets, the no-inventing rule and what to do instead, the exact harness format per tool, the warning that a bare "reads inventory" line scores low, and the README with its three required contents.

**Evidence:** [server.py](mcp_server/server.py) (3 tools, 261 lines), [README.md](mcp_server/README.md), and [harness.md](output/harness.md) section 2.

**The three tools and why.** The database has exactly three open tickets, each a different type, each blocked on a different question the ticket row cannot answer by itself — so there is one tool per ticket, scoped to that ticket's actual question. `check_stock` reads `inventory` for ticket 101, because stock is keyed `(sku, size)` and only a size-level lookup answers whether the size S tee ships today (it does not — 0 on hand). `get_lease_payment` reads `leases` for ticket 102, because that ticket is an *email* claiming rent is due, and the amount must come from the lease row ($2,400, due in 2 days) rather than from a message nothing in the schema can verify. `get_price_and_margin` reads `pricing` for ticket 103, giving the floor ($22 cost) and ceiling ($58 list) that a discount decision needs — $1,160 at list for 20 units, $720 of margin available.

**How the no-inventing rule was implemented:** a missing row returns `found: false` with a reason instead of a guess, and the two kinds of miss are distinguished — asking for a size that is not carried returns the sizes that are, while an unknown SKU says so. Where the database has no answer at all, the gap is returned as a flag: `get_price_and_margin` always returns `discount_authority_in_database: false`, because no discount policy or approval table exists anywhere in the schema, so the tool supplies the numbers and refuses to pick the percentage.

**Two harness guards from Problem 2 now enforced in code:** the clock is read from `desk.date_today` (2026-08-31) rather than the system date, so `days_until_due` is computed against the simulated day; and the missing-authority gap is surfaced rather than silently filled.

**Decisions worth naming:** the connection is opened read-only, so a reading tool cannot modify the shop's data even by accident — a write attempt raises `attempt to write a readonly database`, and the helper takes `readonly=False` for the write tools coming later, making that opt-in explicit in the diff. A missing database file raises instead of letting SQLite create an empty one and hand the agent an empty shop that looks like real data. Only `campus_customs_new.db` is ever opened, so the pristine original stays clean to diff against.

**One bug found and fixed while writing it:** `with sqlite3.connect(...)` commits the transaction but does not close the connection, so the original helper leaked one handle per tool call; it was rewritten as a `@contextmanager` that closes in a `finally`.

**Verified, though the problem did not require running it:** the tool logic was exercised against the real database with a stub standing in for FastMCP, since FastMCP is not installed yet. All four ticket-related calls return figures matching section 1 exactly, all four missing-data paths flag rather than invent, the read-only write test is correctly refused, and both database files were byte-identical before and after.

## Problem 4 — Connect the MCP Server and Test Every Tool

**Prompt 1 (initial):**
> Problem 4: add the MCP server to vibe coder and test each tool. Now, please add the MCP server to this project so the vibe coder can call the tools. Save the connection JSON text in .mcp.json at the project root (or however you cc as vibe coder save local MCP server lists). Once the vibe coder is connected, lets test each (and all) of our three MCP tools. Save the evidence in output/mcp_smoke.json . For every tool, include: the promp asked to the vibe coder; the tool name; the tool output (which must match the values in data/campus_customs_new.db)

**Follow-up prompt:**
> 103 must have only one tool. Lets please correct this

**What was lacking:** the first run tested ticket 103 with two tools — `get_price_and_margin` for the discount question and then `check_stock` for the stock shortfall — which broke the one-tool-per-ticket mapping the design is built on.

**What the follow-up changed:** the second call was removed, so the smoke test is now three tickets, three tools, one call each. The test no longer just happens to be 1:1 — it asserts it, comparing the tickets covered and the tools exercised and failing if a ticket is ever served by a second tool, with the result recorded as `tool_ticket_mapping.is_one_to_one` in the evidence file. Harness sections 2.1, 2.4 and 3.3 were corrected to match, and the counts dropped from 22 field comparisons across 4 calls to 19 across 3.

**One consequence worth naming:** ticket 103 asks for 20 hoodies in size M and only 8 are on the shelf, but that shortfall is no longer surfaced by 103's own tool, which answers the pricing question alone. The gap is recorded in harness section 1.2 and is work for a later problem, not something `get_price_and_margin` should quietly take on.

**Evidence:** [mcp_smoke.json](output/mcp_smoke.json), [.mcp.json](../.mcp.json) at the project root, [smoke_test.py](mcp_server/smoke_test.py), and [harness.md](output/harness.md) section 3.

**Registration:** `campus-customs` was added to the root `.mcp.json` next to the existing `yale-som-courses` and `outlook` servers, using the same absolute-path convention. Dependencies went into a new `HW5/.venv` (FastMCP 4.1.0), kept separate from the venv the Outlook server uses.

**One honest limitation, stated rather than papered over:** Claude Code reads `.mcp.json` at startup, so the `campus-customs` tools are not callable from this chat window until the next launch, when the new project server is approved once. Rather than claim a connection that does not exist yet in this session, the smoke test drives the server over the same stdio MCP protocol the editor uses — `list_tools` then `call_tool` against `server.py` spawned as a subprocess. That is a real protocol round trip, not a Python import of the functions, so the tools were exercised the way an agent actually reaches them.

**How "must match the database" was proven:** every value each tool returned was re-read from `data/campus_customs_new.db` with independent SQL and compared field by field, with both numbers recorded side by side in the evidence file. 19 field-level comparisons across 3 calls, all matching. Two are worth singling out — `as_of` was checked against `desk.date_today` specifically, confirming the tool reports the simulated 2026-08-31 rather than the real system date; and `discount_authority_in_database: false` was verified by querying `sqlite_master` for any approval, discount or policy table, so the flag is grounded in the schema rather than hard-coded.

**All three tools tested, one per ticket:** ticket 101 through `check_stock` (0 on hand, cannot ship), ticket 102 through `get_lease_payment` ($2,400 due 2026-09-02, 2 days out), and ticket 103 through `get_price_and_margin` ($22 cost, $58 list, $1,160 at list for 20). Three tickets, three tools, one call each.

**The never-invent rule was tested, not just asserted:** four calls for data that is not in the database — a cap in a size it does not come in, an unknown SKU, lease 99, and an unpriced SKU. All four returned `found: false` with a reason, and the absent fields matter as much as the flag, since a caller cannot read a fabricated zero out of a response where the key is simply not present.

**Database untouched:** MD5 identical before and after the run, confirming the read-only connection wrote nothing and the working copy still matches the pristine original.

## Problem 5 — The Agent Team and the Grown MCP Toolset

**Prompt 1 (initial):**
> Problem 5: build the agent team and grow the MCP tools. Lets now build the agentic team for campus customs using PydanticAI: Boss, Inventory, Accounting, Facilities, and Customer Service. include prompts, models, and agent loops so they can delegate work to each other with full connectivity. Lets put the agent prompts in backend/prompts/ and create one file per agent. Include the data types in backend/models.py , and the agent files under backend/ (layout can vary as long as the five roles are clear). Use your PORTKEY_API_KEY and only gpt-6-luna for every agent (this step is extremely important because if any other model shows up in my code and/or runs, I will be deducted points. So, again, please only use gpt-6-luna through portkey for every agent, as multi-agent chats consume tokens very fast!) [...] Add any tools that the agents need to my MCP server so they can work on the open tickets. Shop facts come from the MCP server over data/campus_customs_new.db (do not invent a second shop-tools layer that bypasses MCP). Write the agents so they append to output/audit_trail.json as they run [...] in output/harness.md , list each agent and each MCP tool (including the ones added in this problem) along with which table the tool uses. Also add a short safety section [...] Update mcp_server/README.md so the tool list matches what we have now. GO!

**Follow-up prompt:** None needed. The initial prompt named the framework, the five roles, the file layout, the single model and why it mattered, the five shop rules per agent, the no-second-tools-layer constraint, the append-only audit file, the two documents to update and what each needed, and the five safety rules to write down.

**Evidence:** [audit_trail.json](output/audit_trail.json) (3 runs), [harness.md](output/harness.md) section 4, [README.md](mcp_server/README.md), [server.py](mcp_server/server.py) (11 tools), and `backend/` — [models.py](backend/models.py), [settings.py](backend/settings.py), [agents.py](backend/agents.py), [audit.py](backend/audit.py), [run_team.py](backend/run_team.py), [verify_team.py](backend/verify_team.py), [approve_payment.py](backend/approve_payment.py), and five prompt files in [backend/prompts/](backend/prompts/).

**One model, made structurally impossible to break:** `gpt-6-luna` appears exactly once in the whole codebase, as `settings.MODEL_NAME`, and every agent is built from that one constant. Each run collects the model recorded on every step and exits with a failure if the set is anything other than `{gpt-6-luna}`. Across all three runs the recorded set was exactly that. The Portkey key is read from the root `.env` and never hard-coded.

**A conflict worth flagging:** the project's own AGENTS.md says to use `gpt-5.6-luna`, while this prompt said `gpt-6-luna` twice and tied it to grading. Both names resolve through Portkey, so this was a real choice rather than a typo to silently fix; the explicit instruction was followed and the discrepancy raised rather than buried.

**Eight new MCP tools, taking the server from 3 to 11:** `list_open_tickets` and `get_ticket` (tickets) so the Boss can read the queue; `find_restock_vendor` (vendors, invoices) so Inventory can find a supplier; `get_invoice` (invoices, vendors) and `get_cash_position` (cash_accounts, invoices, leases, payments) so Accounting can see what is owed against what exists; `prepare_payment` and `prepare_purchase_order`, both drafts that write nothing; and `record_payment`, the only writing tool. No second tools layer was built — no agent has a database connection, so every claim an agent makes traces to an MCP call in the audit trail.

**`find_restock_vendor` is where the no-inventing rule bit hardest.** The obvious design is to map a SKU to a vendor, but the schema records no such mapping, so any mapping would be invented. The tool instead returns every vendor with its specialty and lead time plus any prior invoice naming that SKU — real evidence, since invoice 501's description names CC-TEE-WHITE — and tells the agent to say which evidence it used.

**Human approval is enforced three times over, not just in a prompt:** `record_payment` itself refuses unless `human_approved` is true and `approved_by` names a person, rejecting any agent name outright; the tool is filtered out of every agent's toolset, so an agent cannot call it even if its prompt is ignored; and each run asserts afterwards that agents executed zero payments. The refusal paths were tested directly — no approval, empty approver, and 'Accounting' and 'boss' as approver were all refused with the database unchanged. `backend/approve_payment.py` is the human path and requires typed confirmation.

**Full connectivity, with loops made impossible:** all five agents hold an `ask_<role>` tool for each of the other four, registered programmatically because twenty hand-written tools would be twenty chances to miswire one. A hop budget of 3 per ticket and a call stack that refuses re-entry stop a chain from running away, and both refusals are written to the audit trail so a reader sees the guard fire.

**What ran:** the Boss routed all three tickets correctly and unprompted — 101 to Inventory (out of stock, blocked pending restock), 102 to Facilities ($2,400 due 2026-09-02, lease authoritative, no payment initiated), and 103 to Accounting ($720 margin at list, no discount policy in the database, awaiting human approval). A separate wiring verification passed 13 of 13 checks, including a live Inventory-to-Customer-Service delegation with no Boss in the chain, proving the graph is complete rather than a star.

**The best evidence that the safety rules hold** is the Customer Service draft from that run: told to write to a customer whose tee is out of stock, it said *"We don't yet have a restock date to share"* rather than inventing the five-day lead time it would have been easy to assume.

**Two bugs found and fixed while building:** `gpt-6-luna` rejects function tools on this endpoint unless reasoning effort is set to `none`, which turned out to be the right setting anyway for lookups this small; and `RunResult.usage` is a property in PydanticAI 2.56, not a method, which broke token accounting on the first run.

**Token cost, since the prompt raised it:** roughly 12k input and 500 output tokens per ticket. Reasoning is off, outputs are small fixed structures rather than prose, per-agent ceilings are set at 8 requests and 10 tool calls, and the Boss delegates to one specialist per ticket unless a second is genuinely needed.

**Database untouched:** MD5 of `campus_customs_new.db` unchanged across all three runs, `payments` still empty, balance still $3,400 — because no human has approved anything yet.

## Problem 6 — Plan the Three Tickets

**Prompt 1 (initial):**
> Problem 6: Plan the three tickets. Before we wire the backend, lets write down what we expect the team to do on each open ticket. Build output/desk_tickets.html (a page that we can double-click with one tab per ticket (101, 102, and 103). Also, add empty Cash and Reflection tabs for later problems (leave them blank for now, you can also add a "coming later" note for now). On each ticket tab, fill an Expected section only (leave room for an Actual section to fill after the agents run). For each ticket's Expected section, lets write: the Boss should call first the agent that is related to the problem faced, for example if there is a problem with paying rent, it should first call Facilities and then Accounting (and that's it), Following up, we expect to delegate efficiently, for example if the matter is on a size, it should not expect to call Facilities. If a discount is requested on an existing item, Boss is not expected to call neither Facilities nor inventory. The MCP tools expected that run to use are the ones related to the specific problem itself as shown in the previous two examples. NEVER send every specialist on every ticket, as I will lose points.

**Follow-up prompt:** None needed. The initial prompt named the file, the five tabs and which two to leave blank, that only the Expected section was to be filled, the routing pattern with two worked examples, the rule that expected tools follow the specific problem, and the hard constraint that every specialist must never be sent to every ticket.

**Evidence:** [desk_tickets.html](output/desk_tickets.html) and [harness.md](output/harness.md) section 5.

**The routing written down, following the examples given:** 101 is a size question, so Inventory first and then Customer Service, with Facilities and Accounting explicitly excluded. 102 follows the rent example exactly — Facilities first, then Accounting, and that is it. 103 is a discount on an existing item, so neither Facilities nor Inventory, leaving Accounting first and then Customer Service. Two agents per ticket, never more.

**The part that carries the weight is the exclusion list.** Each tab names who should *not* be called and why, because that is where the discipline actually shows — a plan that only lists who to call does not prove anyone was left out on purpose. The same applies to tools: each ticket lists the tools expected *and* the tools not expected, so for instance 103 expects `get_price_and_margin` and explicitly not `check_stock`, `get_lease_payment` or `prepare_payment`.

**Two honest tensions recorded rather than smoothed over.** Ticket 101's restock is blocked by invoice 501 being overdue, which is Accounting's business — but calling Accounting here would be a second money errand on a customer's question, so the page says Inventory should flag it to the Boss instead. Ticket 103 asks for 20 hoodies when only 8 are in stock, which is a genuine Inventory matter — but the instruction is explicit that a discount request should not reach Inventory, so the page records the shortfall as something Accounting flags once a price is agreed. Both are written as deliberate choices with reasons, not omissions.

**Verified with 33 automated checks, all passing:** the page has zero `src`/`href` references and no http(s) anywhere, so it genuinely opens by double-click with no server; five tabs map to five panels with exactly one active at load; all three ticket tabs have an Expected section, an empty Actual placeholder and a "who should not be called" list; Cash and Reflection have neither. Every figure on the page was compared against a live database query — rent, due date, cash, hoodie cost and list, order total, margin, tee stock and the shop date all match.

**One thing not verified, stated plainly:** how the page looks rendered. The desktop preview sandbox cannot read files under the homework folder — the same limitation recorded in HW4 — and no browser is connected to drive a `file://` URL, so the markup and the facts are checked but the visual result is not. The preview scaffolding that was tried was removed rather than left cluttering `output/`.

## Problem 7 — Backend Routes

**Prompt 1 (initial):**
> Problem 7: Backend routes. In the next problem, our React frontend dashboard needs a backend it can call. In backend/main.py, use FastAPI and add routes that do the following: return the three tickets and whether each is either open or resolved; take a ticket id and run the agent team on that ticket (of course, be mindful of what we discussed in Problem 6); return recent agent events (what each agent is saying and which tools they are actually using) so the board can refresh; approve a payment or purchase after a human clicks approve (remember, agents only prepare the pay; this route is what actually changes cash. Please remember a payment MUST be approved by a human or I will be deducted points); return the current checking balance from cash_accounts; reset the database to the original values when you want to try a new or fresh run. From the backend/ folder, start the server with: uvicorn main:app --reload --port 8000 [...] In output/harness.md , list each route in one line (what URL and what it does).

**Follow-up prompt:** None needed. The initial prompt listed all six routes and what each had to return, named the file and framework, restated the human-approval rule and why it mattered, gave the exact start command and port, and said the harness needed one line per route.

**Evidence:** [main.py](backend/main.py), [expectations.py](backend/expectations.py), and [harness.md](output/harness.md) section 6. The server runs at `http://localhost:8000` with docs at `/docs`.

**"Be mindful of Problem 6" was made mechanical rather than hoped for.** The Problem 6 plan now lives as data in `backend/expectations.py`, which does two things the HTML page cannot: it puts the routing rule into the brief the Boss actually receives, and it scores each run afterwards. Every `/tickets/{id}/run` response carries a `vs_expected` block reporting whether the first specialist matched, whether the two-specialist budget held, and whether any forbidden agent or tool appeared. All three tickets routed correctly — 101 to Inventory, 102 to Facilities, 103 to Accounting — with no forbidden agents, no forbidden tools, and `record_payment` never called.

**One result reported honestly in the other direction:** each run stopped after the first specialist rather than continuing to the planned second. That is under-delegation against the plan, not over — it stays within the rule that matters for grading, but it does not complete it. The scorecard records the gap rather than hiding it, and it is the obvious thing for the Reflection tab to pick up later.

**Human approval is enforced at four independent layers:** no agent holds `record_payment` at all; `POST /approvals` requires an explicit `confirm: true`; the MCP tool itself rejects agent names in `approved_by`; and every run asserts afterwards that agents executed zero payments. All five refusal paths were tested through the real API — missing confirmation, and 'Accounting', 'boss' and 'ai' as approver, plus a non-existent invoice — and cash stayed at $3,400 through every one. A genuine human approval then moved it to $1,000 and wrote payment row 1, proving the route really does change cash. The amount came from the lease row rather than the request body, so approving means approving the obligation and not a number typed into a browser. That test payment was rolled back with `/reset`.

**One honest limitation written into the response itself:** approving a *purchase order* records it in the audit trail and nothing else, because this database has no `purchase_orders` table. No cash moves, which is also correct accounting — nothing is owed until the vendor invoices. The route says so rather than implying a write happened.

**Reset verified properly:** after approving a $2,400 payment and calling `/reset`, the working database was byte-identical to the pristine original again, balance back to $3,400 and payments back to 0. The audit trail is deliberately not wiped — it is append-only, and erasing the record of what happened before a reset would defeat its purpose — so the reset is appended to it as an event instead.

**One thing that needed your decision:** port 8000 was already held by the HW4 Campus Customs API, still running from a week earlier, and the assignment requires that exact port. Rather than killing a process from your previous coursework unasked, this was raised and stopped with your approval. Other local servers on 8010 and 8020 were left untouched.

## Problem 5b — Additional Shop Rules (retrofitted through Problems 6 and 7)

**Prompt (follow-up to Problem 5, given after Problem 7):**
> Before I forget, for problem 5 there were additional rules of the shop: the field desk.date_today is "today" for the shop (we need this date to determine what is overdue); vendor lead times come from the vendors table; a vendor will not ship new product while they still have an open unpaid invoice; if there is not enough cash, the pay tool must refuse (so no negative balances please); cash only goes out in this homework (we didnt model revenue, so no money comes in); again, before a full run to resolve the tickets, lets make sure to reset the database to the original values; again, please do not email customers or call real vendors (drafts stay on the board). Update problems 6 and 7 as necessary (and of course lets continue onwards with these additional rules of the shop)

**What was lacking:** the original Problem 5 prompt set out each agent's job but not the shop's own operating rules, so three of these — the vendor-blocking rule, the overdraft refusal and the cash-direction rule — had no implementation at all, and one of them turned out to change a ticket's answer.

**Evidence:** [server.py](mcp_server/server.py), [_shared_rules.md](backend/prompts/_shared_rules.md), [expectations.py](backend/expectations.py), [main.py](backend/main.py), [desk_tickets.html](output/desk_tickets.html), and [harness.md](output/harness.md) section 7.

**Three rules were already true and were verified rather than assumed.** The desk date was already the only clock — tools return it as `as_of` and compute overdue from it in SQL, ignoring the real date of 2026-10-14. Lead times already came from `vendors.lead_days`, checked tool-against-table for all three vendors. And agents already had no way to send anything: an audit of every tool available to them returns ten, none of which emails, orders or contacts anyone. That last one was worth checking rather than assuming, because this project does have an Outlook MCP server with a `send_email` tool — it is simply not in the agents' toolset.

**Three rules were genuinely missing and are now enforced in code.** A new `_vendor_block()` helper means `find_restock_vendor` marks blocked vendors and `prepare_purchase_order` refuses outright to draft for one. `record_payment` now refuses a payment larger than the balance, returning the shortfall, and asserts afterwards that the balance stayed non-negative and strictly fell. It also refuses any amount at or below zero, since crediting the account would contradict a shop where cash only goes out.

**The vendor rule changed a ticket, which is why it mattered.** Bulldog Print Co is the only apparel reprinter and the vendor named on invoice 501 — the exact SKU ticket 101 wants — and it is blocked by that same unpaid $840. So ticket 101's chain became: no stock, needs a reprint, the one vendor who can do it will not ship while owed, pay invoice 501 with human approval, and only then does the 5-day lead start, giving an earliest arrival of 2026-09-05. The expected second agent for 101 therefore changed from Customer Service to **Accounting**, and Customer Service was reclassified as **deferred rather than forbidden** — not wrong to involve, just premature, since a reply drafted before the restock is settled either says nothing new or invents a date. The scorecard now distinguishes deferred agents from forbidden ones so this does not read as a routing failure.

**Problem 6 updated:** the HTML page gained a shop-rules banner and ticket 101's Expected section was rewritten around the blocked vendor, including the five-step chain, the revised routing, the deferred Customer Service row, and two added tools (`get_invoice`, `prepare_payment`). Tickets 102 and 103 gained the rules that bear on them — the overdraft note on 102, the nothing-is-sent note on 103.

**Problem 7 updated:** `POST /runs/all` resets to the original database and then runs every open ticket, so a full run always starts from the same state; `GET /shop-rules` reports the rules and which vendors are currently blocked; and the Boss's brief now carries the rules that can change an answer.

**Verified against the live system, not just asserted:** the blocked vendor is refused a purchase order while an unblocked one drafts normally; paying invoice 501 reports `can_ship_now: false` and `can_ship_after_this_payment: true`; and with the balance temporarily set to $100, a $2,400 rent payment was refused with a $2,300 shortfall and the balance did not move. The database was then restored byte-identical with `/reset`.

**The full run under the new rules routed correctly** — 101 to Inventory then Accounting, 102 to Facilities, 103 to Accounting — with no forbidden agent or tool anywhere, `record_payment` never called, and cash still at $3,400 with zero payments. Ticket 101's decision now reads *"Restocking is blocked until invoice 501 is paid"*, which is the new rule showing up in the agents' own reasoning.

**Two bugs the new rules exposed and that are now fixed:** the shared usage ceiling of 8 requests cut ticket 101's longer-but-correct chain off mid-run, so it was raised to 16 and a `UsageLimitExceeded` now returns HTTP 429 with the partial steps recorded instead of crashing; and the routing scorecard was ordering agents by when they *finished*, so a nested delegate appeared first and a correctly-routed ticket reported `first_matched: false`. It now orders by when each agent was *asked*.

## Problem 8 — Agent Dashboard

**Prompt 1 (initial):**
> Problem 8: Agent dashboard. Thank you cc! now, lets build the frontend dashboard in frontend/ with React + Vite + TypeScript. The page should call the routes built in Problem 7. At minimum the board should: list all the three tickets (use yale elegant colors like white and blue); let us pick one ticket and start the agent team on it (when you pass the mouse by it, let it shine!); show each agent and what they are saying / doing while the ticket runs (each agent interacting should move. Maybe each agent can be handsome dan with a different look and feel, for example the accountant can have glasses, the boss a suit); mark a ticket resolved when the run finishes (include a checkmark), show a short summary of what each agent did on that ticket; let a human approve a pay or purchase when asked (ask: dear human user, can you please approve?); show the checking balance (it should drop after an approved pay, so lets do the math correctly, its quite direct). [...] Write output/design.md with what we chose above for the dashboard look (also, for the layout consider a blue/white elegant such as the Yale Club NYC webpage https://www.yaleclubnyc.org). It should be easy and fun to use.

**Follow-up prompt:** None needed. The initial prompt named the stack and folder, every feature the board had to have, the exact approval wording, the mascot idea with two worked examples, the design reference site, and the design document to write.

**Evidence:** [design.md](output/design.md), [harness.md](output/harness.md) section 8, and `frontend/` — [App.tsx](frontend/src/App.tsx), [HandsomeDan.tsx](frontend/src/components/HandsomeDan.tsx), [styles.css](frontend/src/styles.css), [api.ts](frontend/src/api.ts), [types.ts](frontend/src/types.ts).

**Handsome Dan is built in CSS, not generated as an image,** following the project rule for creatures in web apps. One shared bulldog — cream head, floppy ears, heavy brow, underbite with two teeth, navy collar with a gold tag — and each agent gets the props of their job: the Boss a pinstripe suit and gold tie, Accounting round wire glasses, Inventory a green warehouse cap, Facilities an orange hard hat, Customer Service a headset and red bow tie. Keeping one base and changing only the props makes the differences read as roles rather than as five unrelated mascots. The no-images rule was verified by asserting the rendered DOM contains no `img` tag and no `background-image: url(...)`.

**The movement carries information rather than decorating.** Four moods: idle breathes slowly, talking breathes faster, working bounces and tilts with ears flapping, a mouth that opens and closes and a thinking bubble, and done settles with a green checkmark. The working agent's seat also lifts and warms to pale gold, so you can see who is acting from across the room. Everything freezes under `prefers-reduced-motion`.

**The design follows the Yale Club of New York as asked:** navy and white, serif headings over a sans-serif interface, thin gold rules, generous whitespace, and gold rationed to a single accent used four times. Serif for what you read, sans for what you click.

**The approval card uses the exact wording requested** and then does the arithmetic in plain words — paying $2,400.00 takes checking from $3,400.00 to $1,000.00 — with the button disabled until a human types their name, and fine print saying the quiet part out loud: only a person can approve, the agents prepared this and cannot pay it.

**One backend change this problem needed:** tickets had no way to become resolved, so a twelfth MCP tool, `mark_ticket_resolved`, was added — and filtered out of every agent's toolset alongside `record_payment`, because an agent closing its own ticket is a self-assessment. The board calls it once a run finishes, and `/reset` puts tickets back to open.

**CORS was widened rather than pinned.** This machine already runs course projects on 5173, 5174 and 5175, so Vite lands on 5176. Rather than killing another project's server or hard-coding a port that would break, the backend now accepts any localhost origin.

**Verified by mounting the board in jsdom and driving it against the live backend,** since the preview sandbox cannot read under the homework folder and no browser is connected — which tested more than a screenshot would have. The production build is clean under TypeScript strict mode. Thirty-one render checks passed, including the real ticket subjects, the $3,400.00 balance fetched from the API, five correctly-dressed Dans sharing one bulldog base, and the hover shine, colour tokens and reduced-motion block. Then the whole flow was clicked through with a real agent run: starting ticket 102, watching 25 events stream in, the ✓ resolved chip appearing, the approval card asking in the specified words, the button enabling only after a name was typed, the balance dropping to $1,000.00, the approver appearing in the payment log, and Reset shop restoring everything.

**One test failure worth naming as a test bug, not a product bug:** the confirmation banner assertion failed on the first pass because the test waited exactly as long as the banner's own five-second auto-dismiss. Re-checked immediately after an action, it renders correctly.

## Problem 9 — Resolve the Tickets

**Prompt 1 (initial):**
> Problem 9: Resolve the tickets. Before we test the agents on a full run over the three tickets, lets reset the working database data/campus_customs_new.db again so we start clean. I will run all three tickets until each is resolved, so please see and keep track of the three runs I'm about to do next. Once the three runs are done, I will tell you "I completed the three runs cc". Then, please open output/desk_tickets.html from Problem 6. On each ticket tab, fill the Actual section from this run [...] On the Cash tab [...] itemize the money [...] Also save: output/resolved_tickets.json [...] and output/resolved_board.html which is a page you can double-click with a screenshot of the React board for each resolved ticket [...] Append the real runs to output/audit_trail.json . And finish output/harness.md so it covers the tables, MCP tools, the five agents, API routes, the dashboard, and safety rules.

**Follow-up prompt:**
> I completed the three runs cc

**What was lacking:** nothing in the first prompt — it was a two-part instruction by design, with the second half deliberately held until the runs were done. The only thing raised before starting was that board screenshots could not be captured from here, so the human took them during the runs.

**Evidence:** [desk_tickets.html](output/desk_tickets.html) (Actual sections and Cash tab filled), [resolved_tickets.json](output/resolved_tickets.json), [resolved_board.html](output/resolved_board.html), [audit_trail.json](output/audit_trail.json), [harness.md](output/harness.md) sections 9 and 10, and six screenshots in [output/screenshots/](output/screenshots/).

**The runs were tracked rather than reconstructed.** Before the reset, the audit trail's run count was recorded as a baseline, so the human's three runs and two approvals could be identified exactly rather than guessed at from timestamps.

**All three tickets resolved, and routing held on every one.** 101 went Boss to Inventory to Accounting; 102 Boss to Facilities; 103 Boss to Accounting. The right specialist was first every time, no forbidden agent or tool appeared anywhere, no ticket drew every specialist, and no agent ever called `record_payment`. Two tickets stopped one hop short of the plan — 102 never reached Accounting and 103 never reached Customer Service — which is under-delegation rather than over, and is written into each Actual section instead of being smoothed over.

**The money reconciles exactly:** $3,400.00 starting, minus $840.00 for invoice 501 on ticket 101, minus $2,400.00 rent on ticket 102, nothing on ticket 103, ending at $160.00 — matching `cash_accounts` in the working database with two payment rows. Both payments were approved by the human through the board; agents executed zero.

**The best evidence the safety rules held** came from ticket 103: asked for a bulk discount with $720.00 of margin visibly available, Accounting returned the numbers and refused to pick a percentage, recording why in its own words — the database holds no discount policy and no approval authority. The never-invent rule held precisely when inventing something would have been most useful.

**One real bug, caught by the human's screenshots rather than by the automated tests.** After a payment went through, the approval card stayed on screen and priced itself from a running total rather than from the bill itself, so ticket 101 read "Paying $0.00" and ticket 102 offered to pay rent again with a projected balance of −$2,240.00. The database was never wrong; only the display was. `GET /cash` now returns each obligation with its own amount and a paid flag, the card disappears once settled, and the arithmetic cannot go negative. The screenshots were kept as taken rather than retaken, and `resolved_board.html` states plainly what they show and what was fixed afterwards.

**On the screenshots:** they arrived inside a `.docx` and a `.pdf` rather than as loose images, so the six PNGs were extracted from the Word package, identified one by one, and renamed by ticket. Two views per ticket — the board and the per-agent detail — are shown on the page.

## Problem 10 — Reflection

**Prompt 1 (initial):**
> Problem 10: Reflection. Open output/desk_tickets.html and fill the Reflection tab. So: for 101, it ran smoothly, but thinking in more detail I would have also called customer service because we need to actually give an answer to the customer! For 102 it actually ran pretty good, so no comments here. But for 103 I think a human should have had to approve the discount because it counts as "money going out of the company", this is the main comment, another comment would be that customer service should have been involved [...] It would have been simpler with one agent as it would have had more criterion [...] but it would have been more costly so having 5 is more efficient. It couls also solve problems on not only size but understanding what customers like like "blue shirts" [...] Also, it could send reminders to pay rent before the due date. And also understand which products customers want discounts [...] Maybe it could not solve the problem of making this process completely automatic, because it would need humans to approve the expenses [...] Tie every answer to this app and the three tickets you ran. Use the ticket tabs and cash tab on the same page as my evidence.

**Follow-up prompt:** None needed. The prompt supplied the reflection itself, said which tab to fill, and set the rule that every point be tied to this app and evidenced from the other tabs on the same page.

**Evidence:** [desk_tickets.html](output/desk_tickets.html), Reflection tab.

**Each of your points was grounded in a number from the run rather than restated.** The 101 observation is evidenced by the Actual section showing the only outbound text was a *vendor* request, so the customer who opened the ticket got nothing — and by noting the restock date existed by the end of the run, so the reason for deferring Customer Service no longer held. The 103 point is sharpened with the arithmetic already on the page: a 20% discount on $1,160.00 at list hands back $232.00 of the $720.00 margin, more than a quarter of the $840.00 invoice a human *was* required to approve — the same person clicked to approve $840.00 and $2,400.00 but could have given away $232.00 with no click, purely because the money was forgone rather than paid. The Cash tab's "No movement" row against 103 is cited as the visible symptom.

**The one-agent-versus-five trade-off was evidenced with the token counts from the three runs:** 103 cost 14,265 input tokens with two tools, 102 cost 13,971, and only 101 — which genuinely crossed stock and money — cost 30,432 across three agents. A single generalist would pay close to the 101 price on every ticket, which supports your conclusion that five is more efficient, and the cost of that efficiency is exactly the failure visible on two tabs: a narrow specialist answers its own question and stops.

**One correction worth making on the "blue shirts" idea:** colour exists only inside the SKU string in this database — `CC-HOOD-NAVY`, `CC-HAT-BLUE` — and not as a field, and `check_stock` is keyed on `(sku, size)`. So a customer asking for something blue cannot be served from the data as it stands; the inventory table would need real attributes first. That is written into the tab rather than left as an assumption.

**Nothing else on the page was altered** — the three ticket tabs and the Cash tab were verified untouched after the edit, and the page still opens by double-click with no external resources.

## Problem 11 — Submit to GitHub

**Prompt 1 (initial):**
> Problem 11: Submit to GitHub. Finally, lets push the code to a public GitHub repository so graders can clone it. I need you to give me (as in the previous homework) the repo URL for me to post to Canvas, and I need you to also put it in output/github_url.txt. Do NOT push my real .env to the GitHub repo. But DO include both database files under data/ (the original and your working copy) so graders can run my app easily. The expected file layout is in the attached pictures: Please match it EXACTLY AS IS and double check. README should explain: copy original DB to the working copy when you need a clean run, start MCP server, start FastAPI backend, start the React board, reset the DB before a full three-ticket run. Lets go!

**Follow-up prompt:** None needed. The prompt gave the layout as images, the secret to exclude, the files to include, the five things the README had to explain, and where to write the URL.

**Repo:** https://github.com/eduardohub555/campus-customs-hw5 — public, matching the `campus-customs-hw4` naming from last time. Also written to [github_url.txt](output/github_url.txt).

**Six files the layout required did not exist yet** and were created: `requirements.txt` at the root (pinning fastmcp, pydantic-ai-slim, python-dotenv, fastapi and uvicorn), `.env.example`, `.gitignore`, a `.mcp.json` with **relative** paths so a cloned copy works rather than the absolute ones in the project-root config, `README.md`, and `output/github_url.txt`. All 26 paths in the diagram were then verified present, both before pushing and again in a fresh clone.

**Two redundancies were removed to tighten the match:** `mcp_server/requirements.txt`, now superseded by the root one (its README reference was updated), and a leftover `.gitkeep`. The source `.docx` and `.pdf` the screenshots arrived in were also dropped, since the six extracted PNGs are what `resolved_board.html` actually uses.

**What was kept despite not being named in the diagram, and why:** the diagram shows `frontend/` with no children at all, so it lists key files rather than every file. `backend/` keeps `settings.py`, `agents.py`, `audit.py`, `expectations.py` and three entry points because `main.py` cannot import without them — deleting them to match a picture would leave graders a repo that does not run. `backend/prompts/_shared_rules.md` is loaded into all five agent prompts, `mcp_server/smoke_test.py` is referenced by the README, the six screenshots are what `resolved_board.html` displays, and `funny_joke.txt` is the Problem 1 proof file cited in this log. The README names the backend modules explicitly so nothing looks unexplained.

**The working copy ships clean rather than resolved.** It held the finished run — $160.00, two payments, three resolved tickets — which would have greeted a grader with an app that looks already done. It was reset to match the original so the app runs out of the box, and the README says so. The evidence of the real run is not lost: it lives in `resolved_tickets.json`, `audit_trail.json`, the Cash tab of `desk_tickets.html`, and the screenshots.

**Secret safety was checked three ways, not assumed:** `.env` is gitignored and absent from the push, absent from the entire git history, and a regex search for a real-looking key across every committed file returns nothing but the `your-portkey-api-key-here` placeholder in `.env.example`.

**Verified by cloning the public repo fresh** rather than trusting the local folder: 26/26 required paths present, no `.env` anywhere in the history, both databases present and byte-identical, all six screenshots resolving for `resolved_board.html`, and the README containing all five workflows the prompt asked for.

<!-- Sections for the remaining problems are appended here as each one is worked. -->
