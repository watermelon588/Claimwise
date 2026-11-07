// Claim pack approval for the prepare_submission pause: pack facts, documents and the cover letter.
import { Check, FileText } from 'lucide-react'
import { docLabel, money } from '../flow.js'
import { Accent, Quiet } from './ui.jsx'
import { EYEBROW, ICON } from './tokens.js'

const ROWS = [
  ['claim_type', 'Claim type'],
  ['patient', 'Patient'],
  ['insurer', 'Insurer'],
  ['policy_number', 'Policy number'],
  ['hospital', 'Hospital'],
  ['admission_date', 'Admitted'],
  ['discharge_date', 'Discharged'],
]

/**
 * Submission pack approval card.
 * @param {{pending: object, onAnswer: (approved: boolean) => void, busy: boolean}} props
 * @returns {JSX.Element}
 */
export default function ApproveSubmission({ pending, onAnswer, busy }) {
  const { pack } = pending
  return (
    <section className="overflow-hidden rounded-2xl border border-line bg-paper" aria-labelledby="approve-title">
      <header className="flex flex-wrap items-end justify-between gap-4 border-b border-line p-5 sm:p-6">
        <div>
          <p className={EYEBROW}>Claim pack</p>
          <h2 id="approve-title" className="mt-1 text-lg font-semibold tracking-tight">Approve before you submit</h2>
        </div>
        <div className="text-right">
          <p className="text-xs text-muted">Amount claimed</p>
          <p className="font-mono text-2xl font-medium tracking-tight">{money(pack.claimed_amount)}</p>
        </div>
      </header>
      <div className="space-y-6 p-5 sm:p-6">
        <p className="text-sm text-muted">{pending.question}</p>
        <dl className="grid grid-cols-1 gap-x-6 gap-y-3 text-sm sm:grid-cols-2">
          {ROWS.map(([key, label]) => (
            <div key={key} className="flex justify-between gap-4 border-b border-line/70 pb-2">
              <dt className="text-muted">{label}</dt>
              <dd className="text-right font-medium">{String(pack[key] ?? 'Not found').replaceAll('_', ' ')}</dd>
            </div>
          ))}
        </dl>
        <div>
          <h3 className={EYEBROW}>Documents</h3>
          <ul className="mt-3 grid gap-2 sm:grid-cols-2">
            {pack.documents.map((d) => (
              <li key={d.id} className="flex items-center gap-2.5 rounded-lg border border-line px-3 py-2 text-sm">
                <FileText {...ICON} className="shrink-0 text-muted" />
                <span className="min-w-0 flex-1 truncate">{d.filename}</span>
                <span className="shrink-0 text-xs text-muted">{docLabel(d.doc_type)}</span>
              </li>
            ))}
          </ul>
        </div>
        <details className="group">
          <summary className={`cursor-pointer list-none ${EYEBROW} hover:text-ink`}>
            <span className="group-open:hidden">Show cover letter</span>
            <span className="hidden group-open:inline">Hide cover letter</span>
          </summary>
          <pre className="mt-3 max-h-64 overflow-auto rounded-xl bg-milk p-4 font-mono text-xs leading-relaxed whitespace-pre-wrap" data-lenis-prevent>{pack.cover_letter}</pre>
        </details>
      </div>
      <footer className="flex flex-wrap items-center gap-2 border-t border-line bg-milk/50 px-5 py-4 sm:px-6">
        <Accent onClick={() => onAnswer(true)} disabled={busy}><Check {...ICON} /> Approve pack</Accent>
        <Quiet onClick={() => onAnswer(false)} disabled={busy}>Not yet</Quiet>
        <span className="ml-auto text-xs text-muted">You submit it yourself on the insurer portal.</span>
      </footer>
    </section>
  )
}
