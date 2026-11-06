// Review the current server-generated claim pack and download its PDF or email draft.
import { useEffect, useState } from 'react'
import { Download, ExternalLink, FileText, Mail } from 'lucide-react'
import { docLabel } from '../flow.js'
import { EYEBROW, ICON } from './tokens.js'
import { Button, FilePick } from './ui.jsx'

const STATUS = {
  approved: 'Approved',
  changed: 'Approval needs renewal',
  not_approved: 'Awaiting approval',
}

const LINK = 'inline-flex min-h-10 items-center justify-center gap-2 rounded-lg border border-line bg-paper px-3 text-sm font-medium hover:border-ink'

/** Load a pack for the active thread and refresh it when the backend claim snapshot changes. */
export default function ClaimPack({ threadId, claim, pending, busy, onUpload, onReview }) {
  const [result, setResult] = useState(null)
  const [retry, setRetry] = useState(0)
  const endpoint = `/api/pack/${encodeURIComponent(threadId)}`

  useEffect(() => {
    const controller = new AbortController()
    fetch(endpoint, { signal: controller.signal, cache: 'no-store' })
      .then(async (response) => {
        if (response.status === 409) return null
        if (!response.ok) throw new Error('Claim pack request failed')
        return response.json()
      })
      .then((data) => {
        if (!controller.signal.aborted) setResult({ claim, data })
      })
      .catch(() => {
        if (!controller.signal.aborted) setResult({ claim, failed: true })
      })
    return () => controller.abort()
  }, [endpoint, claim, retry])

  if (result?.claim !== claim) return null
  if (result.failed) {
    return (
      <section className="mt-10 rounded-xl border border-line bg-paper p-4" aria-label="Claim pack">
        <p className="text-sm text-muted">The claim pack could not be loaded.</p>
        <Button onClick={() => setRetry((count) => count + 1)} className="mt-2">Try again</Button>
      </section>
    )
  }
  if (!result.data) return null

  const { pack, status } = result.data
  return (
    <section className="mt-10 overflow-hidden rounded-2xl border border-line bg-paper" aria-labelledby="claim-pack-title">
      <header className="flex flex-wrap items-center justify-between gap-3 border-b border-line px-5 py-4">
        <div>
          <h2 id="claim-pack-title" className="font-semibold">Claim pack</h2>
          <p className="text-xs text-muted">{pack.documents.length} supporting files · Ref {pack.hash}</p>
        </div>
        <span className={`rounded-md px-2.5 py-1 text-xs font-semibold ${status === 'changed' ? 'bg-coral-soft text-coral-ink' : 'bg-milk-deep text-ink'}`} role="status">
          {STATUS[status]}
        </span>
      </header>
      <div className="space-y-5 px-5 py-4">
        {status === 'changed' && <p className="text-sm text-coral-ink">The documents changed. Review and approve this version before submitting.</p>}
        <details className="rounded-xl border border-line bg-milk/45 px-3.5">
          <summary className="cursor-pointer py-2.5 text-sm font-semibold">Cover letter</summary>
          <pre className="max-h-64 overflow-auto pb-3 font-sans text-sm leading-relaxed whitespace-pre-wrap wrap-anywhere" data-lenis-prevent>{pack.cover_letter}</pre>
        </details>
        <div>
          <h3 className={EYEBROW}>Supporting documents</h3>
          <ul className="mt-2 divide-y divide-line">
            {pack.documents.map((document) => (
              <li key={document.id} className="flex items-center gap-3 py-2.5">
                <FileText {...ICON} className="shrink-0 text-muted" />
                <div className="min-w-0 flex-1">
                  <p className="wrap-anywhere text-sm font-medium">{document.filename}</p>
                  <p className="text-xs text-muted">{docLabel(document.doc_type)}</p>
                </div>
                <a
                  href={`${endpoint}/documents/${encodeURIComponent(document.id)}`}
                  target="_blank"
                  rel="noreferrer"
                  aria-label={`View original ${document.filename} (new tab)`}
                  className="inline-flex min-h-9 shrink-0 items-center gap-1.5 rounded-md px-2 text-xs font-semibold text-coral-ink hover:bg-coral-soft/50"
                >
                  View original <ExternalLink {...ICON} size={13} />
                </a>
              </li>
            ))}
          </ul>
        </div>
      </div>
      <footer className="flex flex-wrap items-center gap-2 border-t border-line bg-milk/45 px-5 py-4">
        <a href={`${endpoint}/pdf`} download className={LINK}><Download {...ICON} /> Download PDF</a>
        <a href={`${endpoint}/eml`} download className={LINK}><Mail {...ICON} /> Download email draft</a>
        <FilePick onFile={onUpload} disabled={busy || pending}>Add supporting document</FilePick>
        {status === 'changed' && <Button onClick={onReview} disabled={busy || pending}>Review updated pack</Button>}
        {pending && <p className="w-full text-xs text-muted">Answer the approval card before adding documents.</p>}
      </footer>
    </section>
  )
}
