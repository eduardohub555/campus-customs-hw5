import { useCallback, useEffect, useRef, useState } from 'react'
import HandsomeDan, { AGENT_LOOKS } from './components/HandsomeDan'
import { api } from './api'
import type { AgentEvent, AgentKey, CashState, RunResult, Ticket } from './types'

const AGENTS: AgentKey[] = ['boss', 'inventory', 'accounting', 'facilities', 'customer_service']

const TICKET_BLURB: Record<number, string> = {
  101: 'A customer wants one tee in size S.',
  102: 'The landlord says rent is due.',
  103: 'A student club wants 20 hoodies at a discount.',
}

const money = (n: number) =>
  n.toLocaleString('en-US', { style: 'currency', currency: 'USD' })

export default function App() {
  const [tickets, setTickets] = useState<Ticket[]>([])
  const [cash, setCash] = useState<CashState | null>(null)
  const [selected, setSelected] = useState<number | null>(null)
  const [running, setRunning] = useState<number | null>(null)
  const [events, setEvents] = useState<AgentEvent[]>([])
  const [results, setResults] = useState<Record<number, RunResult>>({})
  const [error, setError] = useState<string | null>(null)
  const [approver, setApprover] = useState('')
  const [approving, setApproving] = useState(false)
  const [flash, setFlash] = useState<string | null>(null)
  const [shopDate, setShopDate] = useState('')
  const pollRef = useRef<number | null>(null)

  const refresh = useCallback(async () => {
    try {
      const [t, c] = await Promise.all([api.tickets(), api.cash()])
      setTickets(t)
      setCash(c)
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    }
  }, [])

  useEffect(() => {
    api.health().then((h) => setShopDate(h.shop_date)).catch(() => {})
    refresh()
  }, [refresh])

  // While a ticket runs, poll the audit trail so the board shows each agent
  // speaking and each tool firing as it happens, not only at the end.
  useEffect(() => {
    if (running === null) {
      if (pollRef.current) window.clearInterval(pollRef.current)
      pollRef.current = null
      return
    }
    const tick = async () => {
      try {
        const { events: e } = await api.events(running)
        setEvents(e)
      } catch { /* a dropped poll is not worth surfacing */ }
    }
    tick()
    pollRef.current = window.setInterval(tick, 1200)
    return () => { if (pollRef.current) window.clearInterval(pollRef.current) }
  }, [running])

  const start = async (id: number) => {
    setSelected(id); setRunning(id); setError(null); setEvents([])
    try {
      const result = await api.runTicket(id)
      setResults((r) => ({ ...r, [id]: result }))
      const { events: e } = await api.events(id)
      setEvents(e)
      await refresh()
      setFlash(`Ticket ${id} resolved`)
      window.setTimeout(() => setFlash(null), 3200)
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setRunning(null)
    }
  }

  const doReset = async () => {
    setError(null)
    try {
      await api.reset()
      setResults({}); setEvents([]); setSelected(null)
      await refresh()
      setFlash('Board reset to the original shop')
      window.setTimeout(() => setFlash(null), 3200)
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    }
  }

  const approve = async (kind: 'invoice' | 'rent', refId: number, ticketId: number) => {
    if (!approver.trim()) { setError('Please type your name before approving.'); return }
    setApproving(true); setError(null)
    try {
      const before = cash?.balance ?? 0
      const res = await api.approve({
        kind, ref_id: refId, approved_by: approver.trim(), confirm: true, ticket_id: ticketId,
      })
      await refresh()
      setFlash(
        `Thank you. ${money(res.amount ?? 0)} paid — balance ${money(before)} → ${money(res.balance_after ?? 0)}`,
      )
      window.setTimeout(() => setFlash(null), 5000)
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setApproving(false)
    }
  }

  // Which Dan is on his feet right now, from the newest event in the feed.
  const activeAgent = events.find((e) => e.event === 'agent_run' || e.event === 'tool_call')?.agent
  const involved = new Set<AgentKey>(
    (selected !== null ? results[selected]?.agents_involved : undefined) ??
      events.map((e) => e.agent),
  )

  const current = selected !== null ? results[selected] : undefined
  const selectedTicket = tickets.find((t) => t.id === selected)

  // What a human is being asked to approve on this ticket, if anything.
  // Taken from the obligation itself — its own amount, and whether it is
  // already settled — so the ask disappears once paid and is never priced from
  // a running total that moves when something else is paid.
  const askFor = (() => {
    if (!current?.needs_human_approval || !selectedTicket || !cash) return null
    const wanted =
      selectedTicket.lease_id != null
        ? { kind: 'rent' as const, ref: selectedTicket.lease_id }
        : selectedTicket.invoice_id != null
          ? { kind: 'invoice' as const, ref: selectedTicket.invoice_id }
          : null
    if (!wanted) return null
    const ob = cash.obligations.find((o) => o.kind === wanted.kind && o.ref_id === wanted.ref)
    if (!ob || ob.paid) return null
    return { kind: ob.kind, refId: ob.ref_id, label: ob.label, amount: ob.amount }
  })()

  // Anything on this ticket that a human already approved.
  const settled =
    selectedTicket && cash
      ? cash.obligations.filter(
          (o) =>
            o.paid &&
            ((selectedTicket.lease_id != null && o.kind === 'rent' && o.ref_id === selectedTicket.lease_id) ||
              (selectedTicket.invoice_id != null && o.kind === 'invoice' && o.ref_id === selectedTicket.invoice_id)),
        )
      : []

  return (
    <div className="app">
      <header className="masthead">
        <div className="masthead__inner">
          <div className="crest" aria-hidden="true"><span>CC</span></div>
          <div>
            <h1>Campus Customs</h1>
            <p>Back-office agent desk{shopDate && <> · shop date {shopDate}</>}</p>
          </div>
          <div className="masthead__cash">
            <span className="masthead__cash-label">Checking</span>
            <strong className={cash && cash.payment_count > 0 ? 'is-changed' : ''}>
              {cash ? money(cash.balance) : '—'}
            </strong>
            {cash && cash.payment_count > 0 && (
              <small>{cash.payment_count} payment{cash.payment_count > 1 ? 's' : ''} made</small>
            )}
          </div>
        </div>
      </header>

      {flash && <div className="flash">{flash}</div>}
      {error && <div className="flash flash--bad">{error} <button onClick={() => setError(null)}>dismiss</button></div>}

      <main className="grid">
        <section className="col">
          <div className="col__head">
            <h2>Tickets</h2>
            <button className="btn btn--ghost" onClick={doReset} disabled={running !== null}>
              Reset shop
            </button>
          </div>

          {tickets.map((t) => {
            const done = t.status === 'resolved'
            const busy = running === t.id
            return (
              <article
                key={t.id}
                className={`ticket ${selected === t.id ? 'is-selected' : ''} ${done ? 'is-done' : ''} ${busy ? 'is-busy' : ''}`}
                onClick={() => setSelected(t.id)}
              >
                <div className="ticket__top">
                  <span className="ticket__id">#{t.id}</span>
                  <span className={`chip ${done ? 'chip--done' : 'chip--open'}`}>
                    {done ? '✓ resolved' : 'open'}
                  </span>
                </div>
                <h3>{t.subject}</h3>
                <p className="ticket__who">{t.requester} · {t.type.replace('_', ' ')}</p>
                <p className="ticket__blurb">{TICKET_BLURB[t.id] ?? t.notes}</p>
                <button
                  className="btn btn--run"
                  onClick={(e) => { e.stopPropagation(); start(t.id) }}
                  disabled={running !== null}
                >
                  {busy ? 'Team is working…' : done ? 'Run again' : 'Start the agent team'}
                </button>
              </article>
            )
          })}

          {cash && (
            <div className="cashcard">
              <h2>Cash</h2>
              <div className="cashcard__big">{money(cash.balance)}</div>
              <dl>
                {cash.obligations.map((o) => (
                  <div key={`${o.kind}-${o.ref_id}`} className={o.paid ? 'is-paid' : ''}>
                    <dt>{o.paid ? '✓ ' : ''}{o.label}</dt>
                    <dd>{money(o.amount)}</dd>
                  </div>
                ))}
                <div className="is-total">
                  <dt>{cash.outstanding_total > 0 ? 'Still to pay' : 'Nothing outstanding'}</dt>
                  <dd>{money(cash.outstanding_total)}</dd>
                </div>
              </dl>
              {cash.payments.length > 0 && (
                <ul className="cashcard__log">
                  {cash.payments.map((p) => (
                    <li key={p.id}>
                      <span>−{money(p.amount)}</span> {p.kind} · approved by {p.approved_by}
                    </li>
                  ))}
                </ul>
              )}
              <p className="cashcard__note">Cash only leaves the shop. Agents cannot move it.</p>
            </div>
          )}
        </section>

        <section className="col col--wide">
          <div className="col__head"><h2>The team</h2></div>

          <div className="stage">
            {AGENTS.map((a) => {
              const look = AGENT_LOOKS[a]
              const isActive = running !== null && activeAgent === a
              const didWork = involved.has(a)
              const mood = isActive ? 'working' : didWork && running === null ? 'done' : didWork ? 'talking' : 'idle'
              return (
                <div key={a} className={`seat ${isActive ? 'is-active' : ''} ${didWork ? 'is-involved' : ''}`}>
                  <HandsomeDan agent={a} mood={mood} />
                  <strong>{look.role}</strong>
                  <small>{look.name}</small>
                </div>
              )
            })}
          </div>

          {askFor && (
            <div className="approve">
              <h3>Dear human user, can you please approve?</h3>
              <p className="approve__what">{current?.awaiting_human}</p>
              <p className="approve__sum">
                Paying <strong>{money(askFor.amount)}</strong> for {askFor.label} would take
                checking from <strong>{money(cash?.balance ?? 0)}</strong> to{' '}
                <strong>{money((cash?.balance ?? 0) - askFor.amount)}</strong>.
              </p>
              <div className="approve__row">
                <input
                  value={approver}
                  onChange={(e) => setApprover(e.target.value)}
                  placeholder="Your name (not an agent's)"
                  aria-label="Approver name"
                />
                <button
                  className="btn btn--approve"
                  disabled={approving || !approver.trim()}
                  onClick={() => approve(askFor.kind, askFor.refId, selectedTicket!.id)}
                >
                  {approving ? 'Approving…' : 'Yes, I approve'}
                </button>
              </div>
              <small className="approve__fine">
                Only a person can approve a payment — the agents prepared this, they cannot pay it.
              </small>
            </div>
          )}

          {!askFor && settled.length > 0 && current && (
            <div className="settled">
              {settled.map((o) => (
                <p key={`${o.kind}-${o.ref_id}`}>
                  <span className="settled__tick">✓</span> You approved{' '}
                  <strong>{money(o.amount)}</strong> for {o.label}. Paid and recorded —
                  nothing further is needed here.
                </p>
              ))}
            </div>
          )}

          {current && (
            <div className="summary">
              <div className="summary__head">
                <h3>What each agent did on #{current.ticket_id}</h3>
                {current.resolved && <span className="chip chip--done">✓ resolved</span>}
              </div>
              {current.agent_summaries.map((s, i) => (
                <div className="summary__row" key={i}>
                  <HandsomeDan agent={s.agent} size={46} mood="done" />
                  <div>
                    <strong>{AGENT_LOOKS[s.agent].role}</strong>
                    <p>{s.says}</p>
                    {s.tools.length > 0 && (
                      <p className="summary__tools">
                        {Array.from(new Set(s.tools)).map((t) => <code key={t}>{t}</code>)}
                      </p>
                    )}
                    {s.draft && <blockquote>{s.draft}</blockquote>}
                  </div>
                </div>
              ))}
              <p className="summary__meta">
                {current.delegations.join(' · ')} — {current.tokens.input.toLocaleString()} in /{' '}
                {current.tokens.output.toLocaleString()} out tokens, {(current.duration_ms / 1000).toFixed(1)}s,
                model {current.model}
              </p>
            </div>
          )}

          <div className="feed">
            <div className="col__head"><h2>Live feed</h2>{running !== null && <span className="pulse">running…</span>}</div>
            {events.length === 0 && <p className="feed__empty">Pick a ticket and start the team to watch them work.</p>}
            <ul>
              {events.map((e, i) => (
                <li key={`${e.run_id}-${e.step}-${i}`} className={`feed__${e.event}`}>
                  <span className="feed__who">{AGENT_LOOKS[e.agent]?.role ?? e.agent}</span>
                  {e.event === 'tool_call' && (
                    <span>called <code>{e.tool_name}</code>{e.tool_args && Object.keys(e.tool_args).length > 0 && (
                      <em> ({Object.entries(e.tool_args).map(([k, v]) => `${k}=${v}`).join(', ')})</em>
                    )}</span>
                  )}
                  {e.event === 'agent_run' && <span>{e.says}</span>}
                  {e.event === 'delegation' && <span className="feed__deleg">{e.note}</span>}
                  {e.event === 'refusal' && <span className="feed__refuse">{e.note}</span>}
                  {(e.event === 'approval' || e.event === 'reset') && <span>{e.note}</span>}
                </li>
              ))}
            </ul>
          </div>
        </section>
      </main>

      <footer className="foot">
        Agents prepare · a human approves · nothing is sent. Shop facts come from the
        campus-customs MCP server.
      </footer>
    </div>
  )
}
