// Message bar: attach, type, send. Locked while a card waits for an answer.
import { useState } from 'react'
import { ArrowUp } from 'lucide-react'
import { FilePick } from './ui.jsx'
import { ICON } from './tokens.js'

/**
 * Composer.
 * @param {{cw: object}} props
 * @returns {JSX.Element}
 */
export default function Composer({ cw }) {
  const [text, setText] = useState('')
  const locked = Boolean(cw.pending)
  const canSend = text.trim() && !cw.busy && !locked

  /** Send the typed message. */
  function send(e) {
    e.preventDefault()
    if (!canSend) return
    cw.say(text.trim())
    setText('')
  }

  return (
    <form onSubmit={send} className="flex items-center gap-1.5 rounded-2xl border border-line bg-paper p-1.5 shadow-[0_8px_30px_-12px_rgb(17_17_17/0.18)] transition-colors focus-within:border-ink/40">
      <FilePick onFile={cw.upload} disabled={cw.busy} iconOnly className="border-transparent bg-transparent text-muted hover:border-transparent hover:text-ink">Attach a document</FilePick>
      <input
        value={text}
        onChange={(e) => setText(e.target.value)}
        disabled={locked}
        aria-label="Message"
        placeholder={locked ? 'Answer the card above first' : 'Ask Claimwise about your claim'}
        className="h-10 min-w-0 flex-1 bg-transparent px-1 text-sm placeholder:text-muted/80 focus:outline-none"
      />
      <button
        type="submit"
        disabled={!canSend}
        aria-label="Send"
        className="grid size-10 shrink-0 place-items-center rounded-xl bg-ink text-milk transition-[background-color,opacity,scale] duration-200 hover:bg-ink-soft active:scale-95 disabled:opacity-25"
      >
        <ArrowUp {...ICON} size={17} />
      </button>
    </form>
  )
}
