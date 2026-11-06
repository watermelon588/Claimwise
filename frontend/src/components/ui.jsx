// Shared primitives in the Claimwise tokens: buttons, fields, file pickers, the upload zone and the wordmark.
import { useState } from 'react'
import { Paperclip, Upload } from 'lucide-react'
import Mascot from './Mascot.jsx'
import { ICON } from './tokens.js'

const BASE =
  'inline-flex h-10 shrink-0 items-center justify-center gap-2 rounded-lg text-sm font-medium transition-[background-color,border-color,color,scale] duration-200 ease-out active:scale-[.97] disabled:pointer-events-none disabled:opacity-40'
const ACCEPT = '.pdf,.png,.jpg,.jpeg'

/** Solid button. invert=true on ink backgrounds. */
export function Button({ invert, className = '', ...props }) {
  const tone = invert ? 'bg-milk text-ink hover:bg-white' : 'bg-ink text-milk hover:bg-ink-soft'
  return <button type="button" className={`${BASE} px-4 ${tone} ${className}`} {...props} />
}

/** Text-only button for secondary actions. */
export function Quiet({ className = '', ...props }) {
  return <button type="button" className={`${BASE} px-3 text-muted hover:text-ink ${className}`} {...props} />
}

/** Bordered button for equal-weight choices. */
export function Outline({ className = '', ...props }) {
  return <button type="button" className={`${BASE} border border-line bg-paper px-4 hover:border-ink ${className}`} {...props} />
}

/** Read the chosen file, reset the input so the same file can be picked again, and hand it on. */
function picked(e, onFile) {
  const file = e.target.files?.[0]
  e.target.value = ''
  if (file) onFile(file)
}

/**
 * File chooser styled as a button. iconOnly renders a square paperclip button (needs a label).
 * @param {{onFile: (f: File) => void, disabled?: boolean, invert?: boolean, iconOnly?: boolean, children?: string, className?: string}} props
 */
export function FilePick({ onFile, disabled, invert, iconOnly, children = 'Upload', className = '' }) {
  const tone = invert ? 'border-milk/20 text-milk hover:border-milk/60' : 'border-line bg-paper text-ink hover:border-ink'
  return (
    <label
      aria-label={iconOnly ? children : undefined}
      className={`${BASE} cursor-pointer border ${tone} ${iconOnly ? 'w-10' : 'px-4'} focus-within:outline-2 focus-within:outline-offset-2 focus-within:outline-current ${disabled ? 'pointer-events-none opacity-40' : ''} ${className}`}
    >
      {iconOnly ? <Paperclip {...ICON} size={18} /> : <Upload {...ICON} />}
      {!iconOnly && <span>{children}</span>}
      <input type="file" accept={ACCEPT} className="sr-only" disabled={disabled} onChange={(e) => picked(e, onFile)} />
    </label>
  )
}

/**
 * Large click-or-drop upload area. While busy it shows the chosen file and an indeterminate bar.
 * @param {{onFile: (f: File) => void, busy: boolean, label?: string}} props
 */
export function DropZone({ onFile, busy, label = 'Drop your file here' }) {
  const [over, setOver] = useState(false)
  const [name, setName] = useState('')

  /** Remember the name for the busy state, then upload. */
  function take(file) {
    if (busy) return
    setName(file.name)
    onFile(file)
  }

  /** Take the first dropped file. */
  function drop(e) {
    e.preventDefault()
    setOver(false)
    const file = e.dataTransfer.files?.[0]
    if (file) take(file)
  }

  if (busy) {
    return (
      <div className="relative overflow-hidden rounded-2xl border border-line bg-paper p-5" role="status">
        <div className="flex items-center gap-4">
          <Mascot state="reading" size="sidebar" />
          <div className="min-w-0 flex-1">
            <p className="truncate text-sm font-medium">{name || 'Your document'}</p>
            <p className="text-xs text-muted">Pip is reading your document.</p>
          </div>
        </div>
        <div className="absolute inset-x-0 bottom-0 h-0.5 overflow-hidden bg-line" aria-hidden>
          <div className="animate-indeterminate h-full w-2/5 bg-coral" />
        </div>
      </div>
    )
  }

  return (
    <label
      onDragOver={(e) => {
        e.preventDefault()
        setOver(true)
      }}
      onDragLeave={() => setOver(false)}
      onDrop={drop}
      className={`group flex cursor-pointer flex-col items-center justify-center gap-4 rounded-2xl border border-dashed px-6 py-8 text-center transition-colors duration-200 focus-within:outline-2 focus-within:outline-offset-2 focus-within:outline-ink ${
        over ? 'border-coral bg-coral-soft/60' : 'border-ink/20 bg-paper/60 hover:border-ink/50 hover:bg-paper'
      }`}
    >
      <span className="relative grid place-items-center rounded-full bg-coral-soft">
        <Mascot state="welcome" size="hero" />
        <span className="absolute right-0 bottom-1 grid size-7 place-items-center rounded-full border border-line bg-paper text-coral-ink" aria-hidden="true">
          <Upload {...ICON} size={14} />
        </span>
      </span>
      <span className="space-y-1">
        <span className="block text-[15px] font-semibold">{label}</span>
        <span className="block text-sm text-muted">
          or <span className="font-medium text-ink underline decoration-line underline-offset-4 group-hover:decoration-ink">browse files</span>. Pip will read it for your claim.
        </span>
      </span>
      <span className="font-mono text-[11px] tracking-wide text-muted">PDF, PNG or JPEG · up to 10 MB</span>
      <input type="file" accept={ACCEPT} className="sr-only" onChange={(e) => picked(e, take)} />
    </label>
  )
}

/** Claimwise wordmark with Pip's face, shared with the browser favicon. */
export function Brand() {
  return (
    <span className="inline-flex items-center gap-2.5">
      <img src="/mascot-icon.png" width="34" height="34" alt="" />
      <span className="text-[15px] font-semibold tracking-[-0.01em]">Claimwise</span>
    </span>
  )
}

/** Pip's static avatar for history and a live pose for the current reply. */
export function AgentMark({ state = 'ready' }) {
  return (
    <span className="grid size-10 shrink-0 place-items-center rounded-xl border border-line bg-paper" aria-hidden="true">
      {state === 'ready'
        ? <img src="/mascot-icon.png" width="29" height="29" alt="" />
        : <Mascot state={state} />}
    </span>
  )
}
