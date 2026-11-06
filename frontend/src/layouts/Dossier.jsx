// Dossier: an ink case-file panel on the left (summary and documents) and the work on the right,
// under a segmented progress bar. Reads like a file you work through.
import { useCallback, useEffect, useRef, useState } from 'react'
import Alerts from '../components/Alerts.jsx'
import CaseRecord from '../components/CaseRecord.jsx'
import ClaimPack from '../components/ClaimPack.jsx'
import Composer from '../components/Composer.jsx'
import DocumentModal from '../components/DocumentModal.jsx'
import Documents from '../components/Documents.jsx'
import ErrorToast from '../components/ErrorToast.jsx'
import { stepIcon } from '../components/icons.js'
import Mascot, { PipActivityLabel } from '../components/Mascot.jsx'
import Notifications from '../components/Notifications.jsx'
import { JourneyProgress } from '../components/Progress.jsx'
import StepForm from '../components/StepForm.jsx'
import Thread from '../components/Thread.jsx'
import { Brand, FilePick } from '../components/ui.jsx'
import { EYEBROW, ICON } from '../components/tokens.js'
import { useEnter, useReveal } from '../motion.js'
import { journeyProgress } from '../flow.js'

const STAGE = {
  preparing: 'Preparing', approved_to_submit: 'Ready to submit', submitted: 'Submitted',
  query_raised: 'Query raised', decided: 'Decided', payment_reported: 'Payment reported',
  payment_verified: 'Paid', payment_mismatch: 'Payment issue',
}

/** Four key facts about the case, from state the app already has. */
function CaseFacts({ cw, view }) {
  const toFix = (cw.claim?.issues ?? []).filter((i) => i.severity === 'block').length
  const facts = [
    ['Stage', view.onboarding ? 'Setting up' : STAGE[cw.claim?.stage] ?? 'Preparing'],
    ['Claim type', cw.answers.claimType ? cw.answers.claimType[0].toUpperCase() + cw.answers.claimType.slice(1) : 'Not set'],
    ['Documents', String(cw.documents.length)],
    ['To fix', String(toFix)],
  ]
  return (
    <dl className="grid grid-cols-2 gap-px overflow-hidden rounded-xl bg-milk/10">
      {facts.map(([k, v]) => (
        <div key={k} className="bg-ink px-4 py-3.5">
          <dt className="text-[11px] text-milk/50">{k}</dt>
          <dd className={`mt-1 truncate text-sm font-semibold ${k === 'To fix' && v !== '0' ? 'text-coral' : ''}`}>{v}</dd>
        </div>
      ))}
    </dl>
  )
}

/**
 * Dossier layout.
 * @param {{cw: object, view: object}} props
 * @returns {JSX.Element}
 */
export default function Dossier({ cw, view }) {
  const root = useRef(null)
  const [review, setReview] = useState(null)
  const doc = cw.documents.find((item) => item.id === review?.id)
  const pendingPolicy = cw.pending?.type === 'confirm_policy' ? cw.pending.policy : null
  const previewUrl = review?.url
  const closeDoc = useCallback(() => setReview(null), [])
  useEffect(() => () => {
    if (previewUrl) URL.revokeObjectURL(previewUrl)
  }, [previewUrl])
  useEnter(root, view.onboarding ? view.current.id : 'workspace')
  useReveal(root, `${cw.messages.length}:${view.alerts.length}`)

  const head = view.onboarding ? view.current : view.now
  const pipState = cw.busy ? cw.activity : cw.pending ? 'waiting' : 'ready'

  /** Open a document review with a temporary URL for this tab's original file. */
  function openDoc(id) {
    const original = cw.originals[id]
    setReview({ id, url: original ? URL.createObjectURL(original) : null })
  }

  return (
    <div ref={root} className="min-h-dvh lg:pl-[22rem]">
      <aside className="on-ink flex flex-col bg-ink text-milk lg:fixed lg:inset-y-0 lg:left-0 lg:w-[22rem] lg:overflow-y-auto" data-lenis-prevent>
        <div className="flex h-16 shrink-0 items-center border-b border-milk/10 px-6">
          <Brand />
        </div>
        <div className="space-y-9 px-6 py-7">
          <section className="flex items-center gap-3 rounded-xl border border-milk/12 bg-milk/5 px-3 py-2.5" aria-label="Pip, your claim assistant">
            <Mascot key={pipState} state={pipState} size="sidebar" motion="brief" />
            <div className="min-w-0">
              <p className="text-sm font-semibold">Pip <span className="ml-1.5 text-xs font-normal text-milk/60">Your claim assistant</span></p>
              <p className="mt-0.5 flex items-center gap-1.5 text-xs text-milk/75">
                <span className="size-1.5 shrink-0 rounded-full bg-coral" aria-hidden="true" />
                <PipActivityLabel state={pipState} />
              </p>
            </div>
          </section>
          <section data-enter aria-labelledby="case-title" className="space-y-3">
            <h2 id="case-title" className={`${EYEBROW} text-milk/50`}>Case file</h2>
            <CaseFacts cw={cw} view={view} />
          </section>
          <section data-enter aria-labelledby="docs-title" className={`space-y-3 ${cw.documents.length ? '' : 'hidden lg:block'}`}>
            <h2 id="docs-title" className={`${EYEBROW} text-milk/50`}>Documents</h2>
            <Documents documents={cw.documents} onOpen={(item) => openDoc(item.id)} dark />
            <FilePick onFile={cw.upload} disabled={cw.busy} invert className="w-full">Add a document</FilePick>
          </section>
        </div>
        <p className="mt-auto hidden px-6 py-6 text-xs leading-relaxed text-milk/45 lg:block">
          Claimwise prepares and explains. You submit and decide.
        </p>
      </aside>

      <header className="sticky top-0 z-30 border-b border-line/80 bg-milk/85 backdrop-blur-md">
        <div className="mx-auto max-w-3xl px-6 py-3.5">
          <JourneyProgress value={journeyProgress(view)} step={head?.title ?? 'All current steps done'} />
        </div>
      </header>

      {cw.loadingThread ? (
        // Saved session still loading from the server: say so instead of showing an empty new claim.
        <main className="mx-auto max-w-3xl px-6 pt-14 pb-24 sm:pt-16">
          <div role="status" className="relative max-w-xl overflow-hidden rounded-2xl border border-line bg-paper p-5">
            <div className="flex items-center gap-4">
              <Mascot state="reading" size="sidebar" />
              <div className="min-w-0 flex-1">
                <p className="text-sm font-medium">Loading your claim</p>
                <p className="text-xs text-muted">Pip is opening your saved case file.</p>
              </div>
            </div>
            <div className="absolute inset-x-0 bottom-0 h-0.5 overflow-hidden bg-line" aria-hidden>
              <div className="animate-indeterminate h-full w-2/5 bg-coral" />
            </div>
          </div>
        </main>
      ) : view.onboarding ? (
        <main className="mx-auto max-w-3xl px-6 pt-14 pb-24 sm:pt-16">
          <div className={view.current.id === 'confirm' ? 'max-w-2xl' : 'max-w-xl'}>
            <span data-enter className="grid size-12 place-items-center rounded-xl bg-ink text-milk">
              {stepIcon(view.current.id, { ...ICON, size: 20 })}
            </span>
            <h1 data-enter className="mt-7 text-[2rem] leading-[1.1] font-semibold tracking-[-0.03em] text-balance sm:text-[2.5rem]">{view.current.title}</h1>
            <p data-enter className="mt-3 text-[15px] leading-relaxed text-muted">{view.current.hint}</p>
            <div data-enter className="mt-10">
              <StepForm key={view.current.id} step={view.current} cw={cw} view={view} onOpenDocument={openDoc} />
            </div>
          </div>
        </main>
      ) : (
        <main className="mx-auto max-w-3xl px-6 pt-12">
          <h1 data-enter className="text-[2rem] leading-[1.1] font-semibold tracking-[-0.03em] sm:text-[2.5rem]">{view.headline}</h1>
          <section aria-labelledby="dossier-needs" className="mt-10">
            <h2 id="dossier-needs" className={`mb-1 ${EYEBROW}`}>Needs you</h2>
            <Alerts alerts={view.alerts} cw={cw} />
          </section>
          <Notifications cw={cw} />
          <CaseRecord cw={cw} />
          {cw.threadId && cw.claim && !cw.loadingThread && (
            <ClaimPack
              key={cw.threadId}
              threadId={cw.threadId}
              claim={cw.claim}
              pending={Boolean(cw.pending)}
              busy={cw.busy}
              onUpload={cw.upload}
              onReview={cw.reviewPack}
            />
          )}
          <section aria-labelledby="dossier-talk" className="mt-14 pb-6">
            <h2 id="dossier-talk" className={`mb-6 ${EYEBROW}`}>Conversation</h2>
            <Thread cw={cw} onOpenDocument={openDoc} />
          </section>
          <div className="sticky bottom-0 z-20 bg-milk pt-2 pb-6">
            <Composer cw={cw} />
          </div>
        </main>
      )}

      {doc && <DocumentModal key={doc.id} doc={doc} policy={pendingPolicy?.doc_id === doc.id ? pendingPolicy : null} previewUrl={previewUrl} onClose={closeDoc} />}
      <ErrorToast error={cw.error} onDismiss={cw.dismissError} />
    </div>
  )
}
