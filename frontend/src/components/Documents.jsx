// Uploaded documents as a compact list: file icon, name, what Claimwise read it as, and its status.
import { Check, CircleAlert, FileImage, FileText, RotateCw, Trash2 } from 'lucide-react'
import { docLabel } from '../flow.js'
import { ICON } from './tokens.js'

/** What the document was read as, or where it stands. */
function meta(doc) {
  if (doc.status === 'failed') return 'Could not be read'
  if (doc.status === 'uploaded') return 'Processing incomplete'
  const label = doc.doc_type ? docLabel(doc.doc_type) : 'Read'
  // DEV-023/024: replaced files and an earlier insurer's letters stay on record but leave the live claim.
  if (doc.status === 'superseded') return `${label}, replaced by a newer version`
  if (doc.status === 'archived') return `${label}, from the earlier claim`
  if (doc.version_choice === 'pending') return `${label}, new version? Choose replace or keep`
  return doc.version > 1 ? `${label}, version ${doc.version}` : label
}

/** Status glyph at the end of a row. */
function Status({ status }) {
  if (status === 'failed' || status === 'uploaded') return <CircleAlert {...ICON} size={15} className="text-coral" />
  return <Check {...ICON} size={15} className="opacity-60" />
}

/**
 * Document list.
 * @param {{documents: Array<object>, onOpen: (doc: object) => void, onRetry: (id: string) => void, onDelete: (id: string) => void, busy: boolean, dark?: boolean}} props
 * @returns {JSX.Element}
 */
export default function Documents({ documents, onOpen, onRetry, onDelete, busy, dark }) {
  if (!documents?.length) {
    return <p className={`text-sm ${dark ? 'text-milk/50' : 'text-muted'}`}>No documents yet.</p>
  }
  const row = dark ? 'hover:bg-milk/[0.06]' : 'hover:bg-paper'
  const tile = dark ? 'bg-milk/[0.08] text-milk' : 'border border-line bg-paper text-ink'
  const action = `grid size-8 shrink-0 place-items-center rounded-lg hover:text-coral disabled:opacity-40 ${row}`
  return (
    <ul className="-mx-2 space-y-0.5">
      {documents.map((d) => {
        const Icon = d.mime_type?.startsWith('image/') ? FileImage : FileText
        return (
          <li key={d.id} className="flex min-w-0 items-center">
            <button type="button" onClick={() => onOpen(d)} className={`flex min-w-0 flex-1 items-center gap-3 rounded-lg px-2 py-2 text-left transition-colors ${row} ${['superseded', 'archived'].includes(d.status) ? 'opacity-55' : ''}`}>
              <span className={`grid size-9 shrink-0 place-items-center rounded-lg ${tile}`}>
                <Icon {...ICON} />
              </span>
              <span className="min-w-0 flex-1">
                <span className="block truncate text-sm font-medium">{d.filename}</span>
                <span className={`block truncate text-xs ${dark ? 'text-milk/55' : 'text-muted'}`}>{meta(d)}</span>
              </span>
              <Status status={d.status} />
            </button>
            {d.source !== 'connector' && (d.status === 'failed' || d.status === 'uploaded') && (
              <button type="button" title="Retry processing" aria-label={`Retry processing ${d.filename}`}
                disabled={busy} onClick={() => onRetry(d.id)} className={action}>
                <RotateCw {...ICON} />
              </button>
            )}
            {d.source !== 'connector' && (
              <button type="button" title="Delete document" aria-label={`Delete ${d.filename}`} disabled={busy}
                onClick={() => window.confirm(`Permanently delete “${d.filename}” from this claim?`) && onDelete(d.id)}
                className={action}>
                <Trash2 {...ICON} />
              </button>
            )}
          </li>
        )
      })}
    </ul>
  )
}
