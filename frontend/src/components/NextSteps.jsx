// Next-step buttons under the latest agent reply. The list comes from the server and follows the claim state.
import { useState } from 'react'
import { ArrowRight, Download } from 'lucide-react'
import { Submitted } from './Alerts.jsx'
import { Accent, FilePick, Outline, Quiet } from './ui.jsx'
import { FIELD, ICON } from './tokens.js'

// Buttons that move the claim forward, most urgent first; the first one offered is the next step.
// 'missing_document' stands for the upload of a required document that is still missing.
const NEXT = ['check_submission', 'submit_connector', 'send_query_reply', 'review_pack', 'prepare_pack', 'upload_fix',
  'missing_document', 'upload_requested', 'upload_statement', 'grievance_sent', 'ombudsman_sent']
// Upload buttons that are not a missing required document.
const OTHER_UPLOADS = ['upload_fix', 'upload_letter', 'upload_requested', 'upload_statement']
// Equal choices the user must make first (which version, which policy); none of them is preselected.
const CHOICES = ['replace_version', 'keep_version', 'choose_policy']

/**
 * The action to show in the accent colour, or null while an equal choice is open or nothing is required (waiting).
 * @param {Array<{id: string, kind: string}>} actions server buttons, in server order
 * @returns {object|null}
 */
function nextStep(actions) {
  if (actions.some((a) => CHOICES.includes(a.id))) return null
  for (const id of NEXT) {
    const found = id === 'missing_document'
      ? actions.find((a) => a.kind === 'upload' && !OTHER_UPLOADS.includes(a.id))
      : actions.find((a) => a.id === id)
    if (found) return found
  }
  return null
}

/** "I sent it" form for a grievance or Ombudsman complaint: the date (checked on the server) and any reference. */
function Dated({ action, cw }) {
  const [date, setDate] = useState('')
  const [reference, setReference] = useState('')
  return (
    <form onSubmit={(e) => { e.preventDefault(); cw.act(action, { date, reference: reference.trim() }) }}
      className="grid w-full gap-2 sm:grid-cols-[auto_1fr_auto]">
      <input type="date" required value={date} onChange={(e) => setDate(e.target.value)} aria-label="Date you sent it" className={`${FIELD} h-10`} />
      <input value={reference} onChange={(e) => setReference(e.target.value)} maxLength={60} placeholder="Reference or complaint number (optional)" aria-label="Reference" className={`${FIELD} h-10`} />
      <Accent type="submit" disabled={cw.busy || !date}>Save</Accent>
    </form>
  )
}

/** One button, by kind: send (server action), upload, download, form or focus. primary shows it as the next step. */
function Step({ action, cw, onForm, primary }) {
  // The arrow repeats the accent colour's meaning for people who cannot tell the colours apart.
  const label = primary ? <>{action.label}<ArrowRight {...ICON} /></> : action.label
  const Press = primary ? Accent : Outline
  switch (action.kind) {
    case 'upload':
      return <FilePick onFile={cw.upload} disabled={cw.busy} accent={primary}>{action.label}</FilePick>
    case 'download':
      return (
        <a href={`/api/pack/${encodeURIComponent(cw.threadId)}/${action.format}`} download
          className="inline-flex h-10 items-center gap-2 rounded-lg border border-line bg-paper px-4 text-sm font-medium transition-colors hover:border-ink">
          <Download {...ICON} />{action.label}
        </a>
      )
    case 'form':
      return <Press onClick={() => onForm(action)} disabled={cw.busy}>{label}</Press>
    case 'focus':
      return <Quiet onClick={() => document.querySelector('input[aria-label="Message"]')?.focus()}>{action.label}</Quiet>
    default:
      // Some buttons carry their own data (which document or policy); the server checks it was offered.
      return <Press onClick={() => cw.act(action, action.data)} disabled={cw.busy}>{label}</Press>
  }
}

/**
 * Button row for what the user can do next. Hidden while busy or while a card waits for an answer.
 * @param {{cw: object}} props
 * @returns {JSX.Element|null}
 */
export default function NextSteps({ cw }) {
  const [formId, setFormId] = useState(null)
  const { actions } = cw
  if (cw.busy || cw.pending || !actions.length) return null
  const form = cw.actions.find((a) => a.kind === 'form' && a.id === formId)
  const next = nextStep(actions)
  return (
    <div data-reveal className="space-y-3 pl-11">
      <div role="group" aria-label="Next steps" className="flex flex-wrap gap-2">
        {actions.map((a) => (
          <Step key={`${a.id}:${a.data?.doc_id ?? ''}`} action={a} cw={cw} onForm={(f) => setFormId(f.id)} primary={a === next} />
        ))}
      </div>
      {form && (
        <div className="space-y-1.5">
          <p className="text-xs text-muted">{form.label}? Enter the date you sent it.</p>
          {form.form === 'dated' ? <Dated action={form} cw={cw} /> : <Submitted cw={cw} />}
        </div>
      )}
    </div>
  )
}
