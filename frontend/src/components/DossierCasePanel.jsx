// Expand the case record without moving the conversation or composer.
import { useRef } from 'react'
import { ChevronRight, FolderOpen, X } from 'lucide-react'
import CaseRecord from './CaseRecord.jsx'
import Documents from './Documents.jsx'
import Notifications from './Notifications.jsx'
import { JourneyProgress } from './Progress.jsx'
import { Quiet } from './ui.jsx'
import { EYEBROW, ICON } from './tokens.js'
import { money } from '../flow.js'

const PAY = { verified: 'Verified in bank', reported: 'Reported by insurer', awaiting: 'Awaiting payment',
  mismatch: 'Needs reconciliation', top_up_due: 'Top-up due', short: 'Short payment', over: 'Overpayment' }

/** An accessible right-side drawer for progress, evidence, case history and outcomes. */
export default function DossierCasePanel({ cw, step, progress, onOpenDocument }) {
  const dialog = useRef(null)
  const decision = cw.claim?.decision
  const payment = cw.claim?.payment
  const unread = cw.notifications.filter((note) => !note.read).length
  return (
    <>
      <Quiet onClick={() => dialog.current.showModal()} className="h-9 shrink-0 px-2 text-xs sm:px-3">
        <FolderOpen {...ICON} size={16} /><span>Case details</span>
        {unread > 0 && <span className="rounded-full bg-coral-soft px-1.5 text-coral-ink" aria-label={`${unread} unread updates`}>{unread}</span>}
        <ChevronRight {...ICON} size={14} className="hidden sm:block" />
      </Quiet>
      <dialog ref={dialog} aria-labelledby="case-details-title"
        className="fixed inset-y-0 right-0 left-auto m-0 h-dvh max-h-none w-full max-w-[31rem] overflow-auto border-l border-line bg-milk p-0 text-ink shadow-xl backdrop:bg-ink/40" data-lenis-prevent>
        <header className="sticky top-0 z-10 flex items-center justify-between gap-4 border-b border-line bg-milk px-5 py-4 sm:px-7">
          <div><p className={EYEBROW}>Claimwise dossier</p><h2 id="case-details-title" className="mt-1 text-xl font-semibold">Case details</h2></div>
          <Quiet className="h-9 px-2" aria-label="Close case details" onClick={() => dialog.current.close()}><X {...ICON} size={18} /></Quiet>
        </header>
        <div className="px-5 py-5 sm:px-7">
          <section className="rounded-2xl border border-line bg-paper p-4" aria-label="Journey and outcome">
            <JourneyProgress value={progress} step={step} />
            <dl className="mt-4 grid grid-cols-2 gap-4 border-t border-line pt-4 text-sm">
              <div><dt className="text-xs text-muted">Claim</dt><dd className="mt-0.5 font-semibold">{cw.submission?.claim_id ?? 'No claim reference yet'}</dd></div>
              <div><dt className="text-xs text-muted">Claim stage</dt><dd className="mt-0.5 font-semibold capitalize">{cw.claim?.stage?.replaceAll('_', ' ') ?? 'Setting up'}</dd></div>
              <div><dt className="text-xs text-muted">Approved amount</dt><dd className="mt-0.5 font-semibold">{decision?.approved == null ? 'Awaiting decision' : money(decision.approved)}</dd></div>
              <div><dt className="text-xs text-muted">Payment</dt><dd className="mt-0.5 font-semibold">{PAY[payment?.status] ?? payment?.status?.replaceAll('_', ' ') ?? 'Pending'}</dd></div>
            </dl>
          </section>
          <section className="mt-6 space-y-2" aria-labelledby="case-detail-documents">
            <h3 id="case-detail-documents" className={EYEBROW}>Documents · {cw.documents.length}</h3>
            <Documents documents={cw.documents} onOpen={(item) => { dialog.current.close(); onOpenDocument(item.id) }} />
          </section>
          <Notifications cw={cw} showConnection={false} />
          <CaseRecord cw={cw} />
        </div>
      </dialog>
    </>
  )
}
