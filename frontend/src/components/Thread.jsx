// Conversation with the agent, with any paused card (policy check or claim pack approval) inline.
import { useEffect, useRef } from 'react'
import { FileText } from 'lucide-react'
import { scrollToBottom } from '../motion.js'
import ApproveLetter from './ApproveLetter.jsx'
import ApproveSubmission from './ApproveSubmission.jsx'
import ConfirmPolicy from './ConfirmPolicy.jsx'
import Markdown from './Markdown.jsx'
import NextSteps from './NextSteps.jsx'
import { MascotStatus, PipActivityLabel } from './Mascot.jsx'
import SkeletonMessage from './SkeletonMessage.jsx'
import { AgentMark } from './ui.jsx'
import { ICON } from './tokens.js'

/** One user message; an upload shows as a file chip. */
function UserMessage({ text }) {
  const upload = text.startsWith('Uploaded ')
  return (
    <div data-reveal className="flex justify-end">
      {upload ? (
        <span className="inline-flex max-w-[85%] items-center gap-2 rounded-xl border border-line bg-paper py-2 pr-3.5 pl-2.5 text-sm">
          <span className="grid size-7 place-items-center rounded-lg bg-ink text-milk"><FileText {...ICON} size={14} /></span>
          <span className="truncate">{text.slice('Uploaded '.length)}</span>
        </span>
      ) : (
        <p className="max-w-[85%] rounded-2xl rounded-br-md bg-ink px-4 py-2.5 text-sm leading-relaxed text-milk">{text}</p>
      )}
    </div>
  )
}

/**
 * Message thread.
 * @param {{cw: object}} props
 * @returns {JSX.Element}
 */
export default function Thread({ cw, onOpenDocument }) {
  const mounted = useRef(false)
  const last = cw.messages[cw.messages.length - 1]

  // Follow new messages and cards, but not on first render (the page should open at its top).
  useEffect(() => {
    if (mounted.current) scrollToBottom()
    mounted.current = true
  }, [cw.messages.length, cw.pending])

  return (
    <div className="space-y-6" aria-live="polite">
      {cw.messages.length === 0 && (
        <div className="flex items-center gap-3 rounded-2xl border border-dashed border-line px-5 py-4 text-sm text-muted">
          <AgentMark />
          <p><strong className="font-semibold text-ink">Ask Pip.</strong> Ask anything about your claim, or attach a letter from the hospital or insurer.</p>
        </div>
      )}
      {cw.messages.map((m, i) => {
        if (m.role === 'user') return <UserMessage key={i} text={m.text} />
        const active = cw.busy && m === last
        if (!m.text && !active) return null
        return (
          <div key={i} data-reveal className="flex gap-3">
            <AgentMark state={active ? cw.activity : 'ready'} />
            <div className="min-w-0 flex-1 pt-0.5 text-[15px] leading-relaxed">
              {active && <p role="status" className="mb-1 text-xs font-medium text-muted"><PipActivityLabel state={cw.activity} /></p>}
              {m.text ? <Markdown text={m.text} /> : <SkeletonMessage />}
            </div>
          </div>
        )
      })}
      {/* Uploads and approvals do not stream, so show what is happening instead. */}
      {cw.busy && last?.role === 'user' && (
        <MascotStatus state={cw.activity} />
      )}
      <NextSteps cw={cw} />
      {cw.pending?.type === 'confirm_policy' && (
        <ConfirmPolicy key={cw.pending.policy.doc_id} pending={cw.pending} onAnswer={cw.answer} busy={cw.busy} onOpenDocument={onOpenDocument} />
      )}
      {cw.pending?.type === 'approve_submission' && (
        <ApproveSubmission key={cw.pending.pack.hash} pending={cw.pending} onAnswer={cw.answer} busy={cw.busy} />
      )}
      {cw.pending?.type === 'approve_letter' && (
        <ApproveLetter key={cw.pending.kind} pending={cw.pending} onAnswer={cw.answer} busy={cw.busy} />
      )}
    </div>
  )
}
