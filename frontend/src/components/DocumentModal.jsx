// Document review dialog: original upload alongside the facts Claimwise extracted.
import { useEffect, useRef } from 'react'
import { CircleAlert, ExternalLink, FileImage, FileText, LoaderCircle, X } from 'lucide-react'
import { docLabel, money } from '../flow.js'
import { lockScroll } from '../motion.js'
import { EYEBROW, ICON } from './tokens.js'

// Labels for known scalar facts; any other scalar is shown with a humanised key.
const LABELS = {
  patient_name: 'Patient', hospital_name: 'Hospital', admission_date: 'Admitted', discharge_date: 'Discharged',
  total_amount: 'Bill total', diagnosis: 'Diagnosis', letter_kind: 'Letter type', letter_date: 'Letter date',
  outcome: 'Outcome', claimed_amount: 'Claimed', approved_amount: 'Approved', insurer: 'Insurer', policy_number: 'Policy number',
  paid_amount: 'Paid', utr: 'Transfer ref (UTR)', paid_on: 'Paid on', statement_from: 'Statement from', statement_to: 'Statement to',
  sum_insured: 'Sum insured', tpa: 'TPA', members: 'Covered members', period_start: 'Cover starts', period_end: 'Cover ends',
  policy_type: 'Policy type',
}

/** Display text for one fact value: rupees for amounts, words for codes. */
function show(key, value) {
  if (key.endsWith('amount') || key === 'sum_insured') return money(value)
  return String(value).replaceAll('_', ' ')
}

/** Small table for line items or line decisions. */
function Lines({ title, rows, cols }) {
  return (
    <section className="space-y-2">
      <h3 className={EYEBROW}>{title}</h3>
      <div className="overflow-x-auto rounded-xl border border-line">
        <table className="w-full text-left text-sm">
          <thead className="border-b border-line bg-milk/60 text-xs text-muted">
            <tr>{cols.map(([, label, right]) => <th key={label} className={`px-3 py-2 font-medium ${right ? 'text-right' : ''}`}>{label}</th>)}</tr>
          </thead>
          <tbody className="divide-y divide-line">
            {rows.map((r, i) => (
              <tr key={i}>
                {cols.map(([key, label, right]) => (
                  <td key={label} className={`px-3 py-2 ${right ? 'text-right font-mono text-[13px]' : ''}`}>
                    {right ? money(r[key]) : (r[key] ?? '-')}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  )
}

/** Show the original file with the browser's native PDF or image viewer. */
function OriginalPreview({ url, mimeType }) {
  return (
    <section aria-labelledby="original-document-title" className="min-w-0 space-y-3 border-b border-line bg-milk/65 p-4 sm:p-5 md:overflow-y-auto md:border-r md:border-b-0">
      <div className="flex flex-wrap items-center justify-between gap-x-3 gap-y-1">
        <h3 id="original-document-title" className={EYEBROW}>Original document</h3>
        <a href={url} target="_blank" rel="noreferrer" className="inline-flex min-h-8 items-center gap-1.5 rounded text-xs font-semibold text-coral-ink hover:underline">
          Open in new tab <ExternalLink {...ICON} size={13} />
        </a>
      </div>
      <div className="h-[min(52dvh,32rem)] overflow-hidden rounded-xl border border-line bg-paper md:h-[min(66dvh,42rem)]">
        {mimeType === 'application/pdf'
          ? <iframe src={`${url}#navpanes=0&view=FitH`} title="Original PDF preview" className="block h-full w-full border-0" />
          : <img src={url} alt="Original uploaded document" className="block h-full w-full object-contain" />}
      </div>
    </section>
  )
}

/**
 * Document dialog.
 * @param {{doc: object, policy?: object, previewUrl?: string, onClose: () => void}} props
 * @returns {JSX.Element}
 */
export default function DocumentModal({ doc, policy, previewUrl, onClose }) {
  const panel = useRef(null)
  // The policy review stores its extracted data in the pending policy rather than document facts.
  const facts = policy ? {
    insurer: policy.insurer, policy_number: policy.policy_number, policy_type: policy.policy_type,
    members: policy.members?.join(', '), sum_insured: policy.sum_insured, tpa: policy.tpa,
    period_start: policy.period_start, period_end: policy.period_end,
  } : (doc.facts ?? {})
  const scalars = Object.entries(facts).filter(([, v]) => v != null && typeof v !== 'object')
  const Icon = doc.mime_type?.startsWith('image/') ? FileImage : FileText

  // Native modal keeps keyboard focus inside and restores it to the trigger on close.
  useEffect(() => {
    const dialog = panel.current
    dialog.showModal()
    lockScroll(true)
    return () => {
      dialog.close()
      lockScroll(false)
    }
  }, [])

  /** Close before unmounting so the browser can return focus to the opener. */
  function close() {
    panel.current.close()
    onClose()
  }

  return (
    <dialog
      ref={panel}
      aria-labelledby="doc-title"
      onCancel={(event) => { event.preventDefault(); close() }}
      onClick={(event) => { if (event.target === event.currentTarget) close() }}
      className={`m-auto max-h-[calc(100dvh-1.5rem)] w-[calc(100%-1.5rem)] flex-col overflow-hidden rounded-2xl border border-line bg-paper text-ink shadow-[0_24px_60px_-20px_rgb(17_17_17/0.35)] backdrop:bg-ink/45 backdrop:backdrop-blur-[2px] open:flex ${previewUrl ? 'max-w-5xl' : 'max-w-xl'}`}
    >
      <header className="flex shrink-0 items-center gap-3 border-b border-line px-5 py-4">
        <span className="grid size-10 place-items-center rounded-xl bg-ink text-milk"><Icon {...ICON} /></span>
        <div className="min-w-0 flex-1">
          <h2 id="doc-title" className="truncate font-semibold">{doc.doc_type ? docLabel(doc.doc_type) : 'Document'}</h2>
          <p className="truncate text-xs text-muted">{doc.filename}</p>
        </div>
        <button type="button" onClick={close} aria-label="Close document" className="grid size-9 shrink-0 place-items-center rounded-lg text-muted transition-colors hover:bg-milk hover:text-ink">
          <X {...ICON} />
        </button>
      </header>

      <div className={`min-h-0 overflow-y-auto ${previewUrl ? 'md:grid md:grid-cols-[minmax(0,1.2fr)_minmax(0,1fr)] md:overflow-hidden' : ''}`} data-lenis-prevent>
        {previewUrl && <OriginalPreview url={previewUrl} mimeType={doc.mime_type} />}
        <section aria-labelledby="extracted-document-title" className="min-w-0 space-y-6 p-4 sm:p-5 md:overflow-y-auto">
          <h3 id="extracted-document-title" className={EYEBROW}>Extracted details</h3>
          {!previewUrl && <p className="text-xs text-muted">The original file is unavailable in this tab.</p>}
          {doc.status === 'failed' && (
            <p className="flex gap-2.5 rounded-xl bg-coral-soft px-4 py-3 text-sm">
              <CircleAlert {...ICON} className="mt-0.5 shrink-0 text-coral-ink" />
              {doc.error || 'This file could not be read. Try a clearer scan or photo.'}
            </p>
          )}
          {doc.status === 'uploaded' && (
            <p className="flex items-center gap-2.5 text-sm text-muted"><LoaderCircle {...ICON} className="animate-spin" /> Still reading this file.</p>
          )}
          {scalars.length > 0 && (
            <dl className="grid grid-cols-1 gap-x-6 gap-y-4 sm:grid-cols-2">
              {scalars.map(([k, v]) => (
                <div key={k}>
                  <dt className="text-xs text-muted">{LABELS[k] ?? k.replaceAll('_', ' ')}</dt>
                  <dd className={`mt-0.5 text-sm font-medium wrap-anywhere ${k.endsWith('amount') || k.endsWith('date') ? 'font-mono text-[13px]' : ''}`}>{show(k, v)}</dd>
                </div>
              ))}
            </dl>
          )}
          {facts.line_items?.length > 0 && (
            <Lines title="Bill lines" rows={facts.line_items} cols={[['head', 'Item'], ['amount', 'Amount', true]]} />
          )}
          {facts.line_decisions?.length > 0 && (
            <Lines title="Line decisions" rows={facts.line_decisions} cols={[['head', 'Item'], ['reason', 'Reason'], ['clause', 'Clause'], ['claimed', 'Claimed', true], ['approved', 'Approved', true]]} />
          )}
          {facts.credits?.length > 0 && (
            <Lines title="Money in" rows={facts.credits} cols={[['date', 'Date'], ['narration', 'Narration'], ['utr', 'Ref'], ['amount', 'Amount', true]]} />
          )}
          {facts.requested_documents?.length > 0 && (
            <section className="space-y-2">
              <h3 className={EYEBROW}>Requested</h3>
              <ul className="list-disc space-y-1 pl-5 text-sm">{facts.requested_documents.map((r) => <li key={r.label}>{r.label}</li>)}</ul>
            </section>
          )}
          {doc.status === 'parsed' && !scalars.length && !facts.line_items?.length && !facts.credits?.length && (
            <p className="text-sm text-muted">Read as {doc.doc_type ? docLabel(doc.doc_type).toLowerCase() : 'a document'}. Policy details live in the policy check step.</p>
          )}
        </section>
      </div>
    </dialog>
  )
}
