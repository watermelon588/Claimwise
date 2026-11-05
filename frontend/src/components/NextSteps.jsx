// Next-step buttons under the latest agent reply. The list comes from the server and follows the claim state.
import { useState } from 'react'
import { Download, ExternalLink, Link2 } from 'lucide-react'
import { Submitted } from './Alerts.jsx'
import { Button, FilePick, Outline, Quiet } from './ui.jsx'
import { FIELD, ICON } from './tokens.js'

/** Open the connector page, then paste the connection code it shows. */
function Connect({ action, cw }) {
  const [open, setOpen] = useState(false)
  const [code, setCode] = useState('')

  /** Link the code; keep the field open if the server refuses it. */
  async function link(e) {
    e.preventDefault()
    if (await cw.linkConnection(code)) setOpen(false)
  }

  if (!open) {
    return (
      <Button onClick={() => { window.open(action.href, '_blank', 'noopener'); setOpen(true) }}>
        <ExternalLink {...ICON} />{action.label}
      </Button>
    )
  }
  return (
    <form onSubmit={link} className="flex w-full gap-2">
      <input value={code} onChange={(e) => setCode(e.target.value)} required pattern="[A-Za-z0-9_\-]{8,64}"
        placeholder="Connection code from the connector page" aria-label="Connection code" className={`${FIELD} h-10`} />
      <Button type="submit" disabled={cw.busy || !code.trim()}><Link2 {...ICON} />Link</Button>
    </form>
  )
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
      <Button type="submit" disabled={cw.busy || !date}>Save</Button>
    </form>
  )
}

/** One button, by kind: send (server action), upload, download, form, connect or focus. */
function Step({ action, cw, onForm }) {
  switch (action.kind) {
    case 'upload':
      return <FilePick onFile={cw.upload} disabled={cw.busy}>{action.label}</FilePick>
    case 'download':
      return (
        <a href={`/api/pack/${encodeURIComponent(cw.threadId)}/${action.format}`} download
          className="inline-flex h-10 items-center gap-2 rounded-lg border border-line bg-paper px-4 text-sm font-medium transition-colors hover:border-ink">
          <Download {...ICON} />{action.label}
        </a>
      )
    case 'connect':
      return <Connect action={action} cw={cw} />
    case 'form':
      return <Outline onClick={() => onForm(action)} disabled={cw.busy}>{action.label}</Outline>
    case 'focus':
      return <Quiet onClick={() => document.querySelector('input[aria-label="Message"]')?.focus()}>{action.label}</Quiet>
    default:
      // Some buttons carry their own data (which document or policy); the server checks it was offered.
      return <Outline onClick={() => cw.act(action, action.data)} disabled={cw.busy}>{action.label}</Outline>
  }
}

/**
 * Button row for what the user can do next. Hidden while busy or while a card waits for an answer.
 * @param {{cw: object}} props
 * @returns {JSX.Element|null}
 */
export default function NextSteps({ cw }) {
  const [formId, setFormId] = useState(null)
  if (cw.busy || cw.pending || !cw.actions.length) return null
  const form = cw.actions.find((a) => a.kind === 'form' && a.id === formId)
  return (
    <div data-reveal className="space-y-3 pl-11">
      <div role="group" aria-label="Next steps" className="flex flex-wrap gap-2">
        {cw.actions.map((a) => (
          <Step key={`${a.id}:${a.data?.doc_id ?? ''}`} action={a} cw={cw} onForm={(f) => setFormId(f.id)} />
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
