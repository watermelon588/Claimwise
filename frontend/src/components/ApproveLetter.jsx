// Approval card for a grievance or Ombudsman letter (DEV-026). The letter is built from the decision facts on the
// server; nothing is sent by Claimwise, the user sends it after approving.
import { Check } from 'lucide-react'
import { Button, Quiet } from './ui.jsx'
import { EYEBROW, ICON } from './tokens.js'

const TITLES = { grievance: 'Grievance to the insurer', ombudsman: 'Complaint to the Insurance Ombudsman' }

/**
 * Letter approval card.
 * @param {{pending: {kind: string, question: string, letter: string}, onAnswer: (approved: boolean) => void, busy: boolean}} props
 * @returns {JSX.Element}
 */
export default function ApproveLetter({ pending, onAnswer, busy }) {
  return (
    <section className="overflow-hidden rounded-2xl border border-line bg-paper" aria-labelledby="letter-title">
      <header className="border-b border-line p-5 sm:p-6">
        <p className={EYEBROW}>Letter to approve</p>
        <h2 id="letter-title" className="mt-1 text-lg font-semibold tracking-tight">{TITLES[pending.kind] ?? 'Letter'}</h2>
      </header>
      <div className="space-y-4 p-5 sm:p-6">
        <p className="text-sm text-muted">{pending.question}</p>
        <pre className="max-h-96 overflow-auto rounded-xl bg-milk p-4 font-mono text-xs leading-relaxed whitespace-pre-wrap" data-lenis-prevent>{pending.letter}</pre>
      </div>
      <footer className="flex flex-wrap items-center gap-2 border-t border-line bg-milk/50 px-5 py-4 sm:px-6">
        <Button onClick={() => onAnswer(true)} disabled={busy}><Check {...ICON} /> Approve letter</Button>
        <Quiet onClick={() => onAnswer(false)} disabled={busy}>Not yet</Quiet>
        <span className="ml-auto text-xs text-muted">You send it yourself. Claimwise records the date.</span>
      </footer>
    </section>
  )
}
