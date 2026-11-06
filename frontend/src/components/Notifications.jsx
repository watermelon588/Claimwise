// Updates from the insurer and date reminders, with the insurer connection and submission status.
import { useState } from 'react'
import { Bell, CircleAlert, Clock, Plug } from 'lucide-react'
import { Quiet } from './ui.jsx'
import { EYEBROW, ICON } from './tokens.js'

const KIND = {
  update: { Icon: Bell, tile: 'bg-ink text-milk' },
  reminder: { Icon: Clock, tile: 'bg-milk-deep text-muted' },
  warning: { Icon: CircleAlert, tile: 'bg-coral-soft text-coral-ink' },
}
const SUBMISSION = {
  submitted: (s) => `Submitted${s.route === 'connector' ? ' online' : ' by you'} on ${(s.submitted_at ?? '').slice(0, 10)}${s.claim_id ? `, claim ${s.claim_id}` : ''}.`,
  unconfirmed: () => 'Submission not confirmed yet. Use "Check submission" before trying again.',
  refused: () => 'The insurer refused the online submission. Submit it yourself or fix the details.',
}

/** Short local date and time for a notice. */
const when = (iso) => new Date(iso).toLocaleString(undefined, { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' })

/**
 * Updates section. Shows nothing until there is a connection, a submission or a notice.
 * @param {{cw: object}} props
 * @returns {JSX.Element|null}
 */
export default function Notifications({ cw }) {
  const [all, setAll] = useState(false)
  const { notifications: notes, connection, submission } = cw
  if (!notes.length && !connection && !submission) return null
  const unread = notes.filter((n) => !n.read).length
  const shown = all ? notes : notes.slice(0, 4)

  return (
    <section aria-labelledby="dossier-updates" className="mt-12">
      <div className="mb-2 flex items-center justify-between gap-3">
        <h2 id="dossier-updates" className={EYEBROW}>Updates{unread ? ` (${unread} new)` : ''}</h2>
        {unread > 0 && <Quiet onClick={cw.markRead} className="h-8 text-xs">Mark all read</Quiet>}
      </div>
      <div className="flex flex-wrap items-center gap-x-4 gap-y-1 border-y border-line py-3 text-sm">
        <span className="inline-flex items-center gap-2">
          <Plug {...ICON} size={14} />
          {connection?.status === 'active' && 'Insurer account connected (mock)'}
          {connection?.status === 'expired' && <span className="text-coral-ink">Insurer connection expired. Connect again from the buttons below.</span>}
          {!connection && 'No insurer account connected'}
        </span>
        {connection && <Quiet onClick={cw.unlinkConnection} disabled={cw.busy} className="h-8 text-xs">Disconnect</Quiet>}
        {submission && SUBMISSION[submission.status] && <span className="w-full text-muted">{SUBMISSION[submission.status](submission)}</span>}
      </div>
      {notes.length > 0 && (
        <ul className="divide-y divide-line border-b border-line">
          {shown.map((n) => {
            const { Icon, tile } = KIND[n.kind] ?? KIND.update
            return (
              <li key={n.id} className="flex gap-3.5 py-3.5">
                <span className={`grid size-8 shrink-0 place-items-center rounded-lg ${tile}`}><Icon {...ICON} size={15} /></span>
                <div className="min-w-0 flex-1">
                  <p className="text-sm leading-relaxed">
                    {!n.read && <span className="mr-2 inline-block size-1.5 rounded-full bg-coral align-middle" aria-label="New" />}
                    {n.text}
                  </p>
                  <p className="mt-0.5 font-mono text-[10px] uppercase tracking-[0.12em] text-muted">{when(n.at)}</p>
                </div>
              </li>
            )
          })}
        </ul>
      )}
      {notes.length > 4 && <Quiet onClick={() => setAll(!all)} className="mt-1 h-8 text-xs">{all ? 'Show fewer' : `Show all ${notes.length}`}</Quiet>}
    </section>
  )
}
