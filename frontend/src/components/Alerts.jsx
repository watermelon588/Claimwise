// "Needs you" list: what the claim is waiting on, each with the control that resolves it.
// compact stacks the control under the text for narrow side columns.
import { useState } from 'react'
import { ArrowUpRight, CircleAlert, Info } from 'lucide-react'
import { Accent, Button, FilePick, Outline } from './ui.jsx'
import { FIELD, ICON } from './tokens.js'

const TONE = {
  block: { label: 'Must fix', Icon: CircleAlert, tile: 'bg-coral-soft text-coral-ink' },
  ask: { label: 'Action', Icon: ArrowUpRight, tile: 'bg-ink text-milk' },
  note: { label: 'Note', Icon: Info, tile: 'bg-milk-deep text-muted' },
}

/** The server button with one of these ids, when it is offered right now. */
const offered = (cw, ...ids) => cw.actions.find((a) => ids.includes(a.id))

/** Submission date (required) and claim number (optional), recorded by the 'I submitted it' action. */
export function Submitted({ cw }) {
  const [date, setDate] = useState('')
  const [number, setNumber] = useState('')

  /** Record the date (checked on the server) and start the settlement timer. */
  function save(e) {
    e.preventDefault()
    const action = offered(cw, 'submitted_manually')
    if (action) return cw.act(action, { submitted_on: date, claim_number: number.trim() })
    cw.say(`I submitted the claim on ${date}.${number.trim() ? ` The claim number is ${number.trim()}.` : ''}`)
  }

  return (
    <form onSubmit={save} className="grid w-full gap-2 sm:grid-cols-[auto_1fr_auto]">
      <input type="date" required value={date} onChange={(e) => setDate(e.target.value)} aria-label="Date you submitted" className={`${FIELD} h-10`} />
      <input value={number} onChange={(e) => setNumber(e.target.value)} placeholder="Claim number (optional)" aria-label="Claim number" className={`${FIELD} h-10`} />
      <Accent type="submit" disabled={cw.busy || !date}>Save</Accent>
    </form>
  )
}

/** The control that resolves one alert. */
function Action({ alert, cw }) {
  switch (alert.action) {
    case 'upload':
      return <FilePick onFile={cw.upload} disabled={cw.busy} />
    case 'claimType':
      return (
        <div className="flex gap-2">
          <Outline onClick={() => cw.setClaimType('cashless')} disabled={cw.busy}>Cashless</Outline>
          <Outline onClick={() => cw.setClaimType('reimbursement')} disabled={cw.busy}>Reimbursement</Outline>
        </div>
      )
    case 'prepare':
      return <Accent onClick={() => { const a = offered(cw, 'prepare_pack', 'review_pack'); if (a) cw.act(a); else cw.say('Please prepare my claim pack for approval.') }} disabled={cw.busy || Boolean(cw.pending)}>Build claim pack</Accent>
    case 'submitted':
      return <Submitted cw={cw} />
    case 'explain':
      return <Button onClick={() => cw.say('Explain each deduction in the decision and whether I can dispute it.')} disabled={cw.busy}>Explain</Button>
    default:
      return null
  }
}

/**
 * Alert list.
 * @param {{alerts: Array<object>, cw: object, compact?: boolean}} props
 * @returns {JSX.Element}
 */
export default function Alerts({ alerts, cw, compact }) {
  if (!alerts.length) {
    return <p className="text-sm text-muted">Nothing needs you right now.</p>
  }
  return (
    <ul className="divide-y divide-line border-y border-line">
      {alerts.map((a) => {
        const { label, Icon, tile } = TONE[a.tone] ?? TONE.note
        const wide = !compact && a.action !== 'submitted'
        return (
          <li key={a.id} data-reveal={compact ? undefined : ''} className={`flex gap-3.5 py-4 ${wide ? 'sm:items-center' : ''}`}>
            <span className={`grid size-8 shrink-0 place-items-center rounded-lg ${tile}`}><Icon {...ICON} size={15} /></span>
            <div className={`flex min-w-0 flex-1 flex-col gap-3 ${wide ? 'sm:flex-row sm:items-center sm:justify-between' : ''}`}>
              <div className="min-w-0">
                <p className="font-mono text-[10px] font-medium uppercase tracking-[0.16em] text-muted">{label}</p>
                <p className="mt-0.5 text-sm leading-relaxed">{a.text}</p>
              </div>
              {a.action && <Action alert={a} cw={cw} />}
            </div>
          </li>
        )
      })}
    </ul>
  )
}
