// Floating error toaster with a plain-English explanation and actionable recovery instruction.
import { useEffect, useState } from 'react'
import { AlertTriangle, CheckCircle2, X } from 'lucide-react'
import { ICON } from './tokens.js'

const AUTO_DISMISS_MS = 10000

/**
 * Floating toast banner for API, upload, and stream errors.
 * @param {{error: {id: number, title: string, message: string, instruction: string, status?: number} | null, onDismiss: () => void}} props
 * @returns {JSX.Element | null}
 */
export default function ErrorToast({ error, onDismiss }) {
  const [paused, setPaused] = useState(false)

  useEffect(() => {
    if (!error || paused) return undefined
    const timer = window.setTimeout(() => {
      onDismiss()
    }, AUTO_DISMISS_MS)
    return () => window.clearTimeout(timer)
  }, [error, paused, onDismiss])

  useEffect(() => {
    if (!error) return undefined
    const onKeyDown = (e) => {
      if (e.key === 'Escape') onDismiss()
    }
    window.addEventListener('keydown', onKeyDown)
    return () => window.removeEventListener('keydown', onKeyDown)
  }, [error, onDismiss])

  if (!error) return null

  return (
    <div
      role="alert"
      aria-live="assertive"
      onMouseEnter={() => setPaused(true)}
      onMouseLeave={() => setPaused(false)}
      className="fixed right-4 bottom-4 z-50 w-[calc(100vw-2rem)] max-w-md overflow-hidden rounded-2xl border border-coral/50 bg-ink text-milk shadow-2xl sm:right-6 sm:bottom-6"
    >
      <div className="h-1 w-full bg-coral" aria-hidden="true" />
      <div className="p-4 sm:p-5">
        <div className="flex items-start justify-between gap-3">
          <div className="flex items-center gap-2.5">
            <span className="grid size-8 shrink-0 place-items-center rounded-lg bg-coral/20 text-coral">
              <AlertTriangle {...ICON} size={17} />
            </span>
            <div>
              <div className="flex items-center gap-2">
                <h3 className="text-sm font-semibold tracking-tight text-milk">{error.title}</h3>
                {error.status > 0 && (
                  <span className="rounded bg-coral/20 px-1.5 py-0.5 font-mono text-[10px] font-semibold text-coral">
                    HTTP {error.status}
                  </span>
                )}
              </div>
              <p className="mt-0.5 text-xs leading-relaxed text-milk/80">{error.message}</p>
            </div>
          </div>
          <button
            type="button"
            onClick={onDismiss}
            aria-label="Dismiss error notification"
            className="rounded-lg p-1 text-milk/60 transition-colors hover:bg-milk/10 hover:text-milk"
          >
            <X {...ICON} size={15} />
          </button>
        </div>

        {error.instruction && (
          <div className="mt-3.5 flex items-start gap-2.5 rounded-xl border border-milk/12 bg-milk/6 px-3.5 py-2.5 text-xs leading-relaxed text-milk/90">
            <CheckCircle2 {...ICON} size={14} className="mt-0.5 shrink-0 text-coral" />
            <div>
              <span className="font-semibold text-milk">Next step: </span>
              <span>{error.instruction}</span>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
