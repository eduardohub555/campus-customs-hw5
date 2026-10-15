# Dashboard Design — Campus Customs Agent Desk

What the board looks like and why, for `frontend/` (React + Vite + TypeScript).

---

## 1. The feeling we were after

A desk you would not mind sitting at. The work underneath is serious — money, vendors, a customer waiting — so the chrome stays quiet and the *content* does the talking. The fun lives in one place: five bulldogs who visibly get up and do the work.

Two rules held the whole way:

- **Nothing moves that shouldn't.** Animation marks *state* — who is working, what finished, what changed — never decoration for its own sake.
- **The board never implies something happened that didn't.** No "sent", no "ordered". Agents prepare; a person approves.

## 2. Colour and type — after the Yale Club of New York

Taking the cues from [yaleclubnyc.org](https://www.yaleclubnyc.org): navy and white, serif over sans, thin gold rules, and a lot of air.

| Token | Value | Where |
|---|---|---|
| `--navy` | `#00356b` | Masthead, headings, primary buttons — Yale blue |
| `--navy-600` / `--navy-800` | `#124a85` / `#002a54` | Hovers, crest gradient |
| `--blue-50` / `--blue-100` / `--blue-200` | `#f4f8fc` / `#e6eef7` / `#cfe0f0` | Page ground, chips, hairlines |
| `--gold` | `#c9a227` | The single accent: masthead rule, section underlines, collar tag, approval card |
| `--good` / `--bad` / `--warn` | `#1c6b47` / `#9b2226` / `#9a5b00` | Resolved, refused, awaiting |

**Type:** Iowan Old Style / Palatino / Georgia for headings and figures; the system sans for everything you *operate*. Serif for what you read, sans for what you click — the Yale Club's own split.

**Gold is rationed.** One accent, used four times. Everything else is navy, white, or a blue-grey in between.

## 3. Layout

A two-column desk under a navy masthead:

```
┌──────────────────────────────────────────────────────────┐
│  [crest]  Campus Customs                   Checking      │
│           Back-office agent desk · date    $3,400.00     │  ← gold rule
├────────────────────┬─────────────────────────────────────┤
│ Tickets            │ The team                            │
│  ┌──────────────┐  │  ┌───────────────────────────────┐  │
│  │ #101  open   │  │  │ 🐶  🐶  🐶  🐶  🐶            │  │
│  │ Bulldog tee  │  │  │ Boss Inv Acct Fac  CS         │  │
│  │ [ Start ]    │  │  └───────────────────────────────┘  │
│  └──────────────┘  │  ┌───────────────────────────────┐  │
│  … #102  #103      │  │ Dear human user, can you      │  │
│                    │  │ please approve?               │  │
│  ┌──────────────┐  │  └───────────────────────────────┘  │
│  │ Cash         │  │  What each agent did · Live feed    │
│  └──────────────┘  │                                     │
└────────────────────┴─────────────────────────────────────┘
```

Left is **what to do** (tickets, money). Right is **what is happening** (the team, the ask, the record). Cards are white on pale blue with a 1px blue-200 hairline, 11px radius, and a soft navy-tinted shadow. One column below 1000px.

## 4. Handsome Dan, five ways — in pure CSS

Per the project rule, the mascots are **built in HTML and CSS, not generated images**. One shared bulldog — cream head, floppy ears, heavy brow, wide muzzle, underbite with two teeth, navy collar with a gold tag — and each agent gets the props of their job:

| Agent | Look | Built from |
|---|---|---|
| **Boss** | Pinstripe suit, white lapels, gold tie | CSS triangles for lapels, rounded bar for the tie |
| **Accounting** | Round wire glasses | Two bordered circles + a bridge, tinted lens fill |
| **Inventory** | Green warehouse cap | Half-ellipse crown + brim |
| **Facilities** | Orange hard hat | Dome, brim, centre ridge |
| **Customer Service** | Headset and red bow tie | Arc band, ear cup, curved mic arm; clip-path bow |

Keeping one base and changing only the props means the differences read as *roles*, not as five unrelated mascots. Each carries an `aria-label` ("Ledger Dan, Accounting, wearing round glasses") so the stage is not silent to a screen reader.

### Four moods, so the stage tells you the state

| Mood | What it means | Motion |
|---|---|---|
| `idle` | Not on this ticket | Slow 3.6s breathing |
| `talking` | Involved, waiting | Quicker 2.4s breathing |
| `working` | Acting right now | Bounces and tilts, **ears flap**, mouth opens and closes, a "…" thought bubble |
| `done` | Finished | Settles, occasional blink, green ✓ pops on |

The active Dan's seat also lifts and warms to a pale gold. You can tell who is working from across the room without reading a word.

## 5. The interactions asked for

**Tickets shine on hover.** A gold-white gradient sweeps diagonally across the card over 0.7s (`translateX(-120%) → 120%`), while the card lifts 3px and its border deepens to navy. Playful, once, and gone — not a loop.

**Pick one and start the team.** Each card has its own *Start the agent team* button. The running ticket breathes a gold ring; a "running…" pulse appears by the feed.

**Watch them work.** While a run is live the board polls `/events` every 1.2s and streams what each agent says and every tool call with its real arguments — read from the audit trail, so it is the recorded truth rather than an agent's account of it.

**Resolved gets a checkmark.** On completion the chip flips to a green **✓ resolved**, the card tints faintly green, and the Dans who worked get their ✓ badge.

**A short summary per agent.** Each agent that acted gets a row: small Dan, role, what they concluded, the tools they used as little navy code chips, and any customer draft in a quoted block.

**The human is asked, politely.** When a run needs approval, a gold-bordered card appears, headed exactly *"Dear human user, can you please approve?"*. It states what is being approved, then the arithmetic in plain words — *"Paying $2,400.00 … would take checking from $3,400.00 to $1,000.00"*. The button stays disabled until a name is typed, and the fine print says the quiet part out loud: *"Only a person can approve a payment — the agents prepared this, they cannot pay it."*

**The balance drops, visibly.** The masthead figure turns gold once a payment exists, the cash card lists each payment with its approver, and the maths is simply the backend's: $3,400.00 − $2,400.00 = $1,000.00.

**Reset shop** puts everything back to the original database for a fresh demo.

## 6. Easy and fun, deliberately

- **One obvious verb per card.** No menus, no modals, no settings.
- **Numbers always in full.** `$3,400.00`, never `3.4k`.
- **Plain language.** "A customer wants one tee in size S" beats `customer_order · CC-TEE-WHITE · S · 1`.
- **Errors are readable.** FastAPI's `detail` is surfaced, so a refused approval says *"'Accounting' is an agent, not a human"*, not `400`.
- **Accessible.** Mascots labelled; focus rings kept; and the whole stage freezes under `prefers-reduced-motion: reduce` — the fun is optional, the information is not.

## 7. Running it

```bash
cd frontend
npm install
npm run dev
```

Vite opens the board automatically. It tries **5173** first and steps up if busy — on this machine 5173–5175 are other course projects, so it lands on **5176**. The backend accepts any `localhost` origin, so whichever port Vite picks works. The backend must be up:

```bash
cd backend && uvicorn main:app --reload --port 8000
```
