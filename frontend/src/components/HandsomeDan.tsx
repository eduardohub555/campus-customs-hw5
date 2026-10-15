import type { AgentKey } from '../types'

/**
 * Handsome Dan, five ways — drawn entirely in HTML and CSS, no images.
 *
 * Each agent is the same bulldog with the props of their job: the Boss in a
 * suit, Accounting in glasses, Inventory in a warehouse cap, Facilities in a
 * hard hat, Customer Service on a headset. The shared base keeps them
 * recognisably the same dog so the differences read as roles, not as five
 * unrelated mascots.
 */

export const AGENT_LOOKS: Record<
  AgentKey,
  { name: string; role: string; prop: string; accent: string }
> = {
  boss: { name: 'Dan the Boss', role: 'Boss', prop: 'pinstripe suit and tie', accent: '#00356b' },
  inventory: { name: 'Stockroom Dan', role: 'Inventory', prop: 'warehouse cap', accent: '#1c6b47' },
  accounting: { name: 'Ledger Dan', role: 'Accounting', prop: 'round glasses', accent: '#7a5a00' },
  facilities: { name: 'Handy Dan', role: 'Facilities', prop: 'hard hat', accent: '#9a5b00' },
  customer_service: { name: 'Friendly Dan', role: 'Customer Service', prop: 'headset and bow tie', accent: '#9b2226' },
}

type Mood = 'idle' | 'working' | 'talking' | 'done'

export default function HandsomeDan({
  agent,
  mood = 'idle',
  size = 96,
}: {
  agent: AgentKey
  mood?: Mood
  size?: number
}) {
  const look = AGENT_LOOKS[agent]
  return (
    <div
      className={`dan dan--${agent} dan--${mood}`}
      style={{ ['--dan-size' as string]: `${size}px`, ['--accent' as string]: look.accent }}
      aria-label={`${look.name}, ${look.role}, wearing ${look.prop}`}
      role="img"
    >
      <div className="dan__body">
        {agent === 'boss' && (
          <>
            <span className="dan__lapel dan__lapel--l" />
            <span className="dan__lapel dan__lapel--r" />
            <span className="dan__tie" />
          </>
        )}
        {agent === 'customer_service' && <span className="dan__bowtie" />}
      </div>

      <div className="dan__head">
        <span className="dan__ear dan__ear--l" />
        <span className="dan__ear dan__ear--r" />

        <span className="dan__brow dan__brow--l" />
        <span className="dan__brow dan__brow--r" />

        <span className="dan__eye dan__eye--l"><i /></span>
        <span className="dan__eye dan__eye--r"><i /></span>

        <span className="dan__muzzle">
          <span className="dan__nose" />
          <span className="dan__mouth" />
          <span className="dan__tooth dan__tooth--l" />
          <span className="dan__tooth dan__tooth--r" />
        </span>

        {agent === 'accounting' && (
          <span className="dan__glasses">
            <i className="dan__lens dan__lens--l" />
            <i className="dan__bridge" />
            <i className="dan__lens dan__lens--r" />
          </span>
        )}
        {agent === 'inventory' && (
          <span className="dan__cap">
            <i className="dan__cap-brim" />
          </span>
        )}
        {agent === 'facilities' && (
          <span className="dan__hardhat">
            <i className="dan__hardhat-brim" />
            <i className="dan__hardhat-ridge" />
          </span>
        )}
        {agent === 'customer_service' && (
          <span className="dan__headset">
            <i className="dan__headset-band" />
            <i className="dan__headset-cup" />
            <i className="dan__headset-mic" />
          </span>
        )}
      </div>

      <span className="dan__collar">
        <i className="dan__tag" />
      </span>

      {mood === 'working' && (
        <span className="dan__think">
          <i /><i /><i />
        </span>
      )}
      {mood === 'done' && <span className="dan__check">✓</span>}
    </div>
  )
}
