// Uploaded documents as a compact list: file icon, name, what Claimwise read it as, and its status.
import { Check, CircleAlert, FileImage, FileText, LoaderCircle } from 'lucide-react'
import { docLabel } from '../flow.js'
import { ICON } from './tokens.js'

/** What the document was read as, or where it stands. */
function meta(doc) {
  if (doc.status === 'failed') return 'Could not be read'
  if (doc.status === 'uploaded') return 'Reading...'
  const label = doc.doc_type ? docLabel(doc.doc_type) : 'Read'
  // DEV-023/024: replaced files and an earlier insurer's letters stay on record but leave the live claim.
  if (doc.status === 'superseded') return `${label}, replaced by a newer version`
  if (doc.status === 'archived') return `${label}, from the earlier claim`
  if (doc.version_choice === 'pending') return `${label}, new version? Choose replace or keep`
  return doc.version > 1 ? `${label}, version ${doc.version}` : label
}

/** Status glyph at the end of a row. */
function Status({ status }) {
  if (status === 'failed') return <CircleAlert {...ICON} size={15} className="text-coral" />
  if (status === 'uploaded') return <LoaderCircle {...ICON} size={15} className="animate-spin opacity-60" />
  return <Check {...ICON} size={15} className="opacity-60" />
}

/**
 * Document list.
 * @param {{documents: Array<object>, onOpen: (doc: object) => void, dark?: boolean}} props
 * @returns {JSX.Element}
 */
export default function Documents({ documents, onOpen, dark }) {
  if (!documents?.length) {
    return <p className={`text-sm ${dark ? 'text-milk/50' : 'text-muted'}`}>No documents yet.</p>
  }
  const row = dark ? 'hover:bg-milk/[0.06]' : 'hover:bg-paper'
  const tile = dark ? 'bg-milk/[0.08] text-milk' : 'border border-line bg-paper text-ink'
  return (
    <ul className="-mx-2 space-y-0.5">
      {documents.map((d) => {
        const Icon = d.mime_type?.startsWith('image/') ? FileImage : FileText
        return (
          <li key={d.id}>
            <button type="button" onClick={() => onOpen(d)} className={`flex w-full items-center gap-3 rounded-lg px-2 py-2 text-left transition-colors ${row} ${['superseded', 'archived'].includes(d.status) ? 'opacity-55' : ''}`}>
              <span className={`grid size-9 shrink-0 place-items-center rounded-lg ${tile}`}>
                <Icon {...ICON} />
              </span>
              <span className="min-w-0 flex-1">
                <span className="block truncate text-sm font-medium">{d.filename}</span>
                <span className={`block truncate text-xs ${dark ? 'text-milk/55' : 'text-muted'}`}>{meta(d)}</span>
              </span>
              <Status status={d.status} />
            </button>
          </li>
        )
      })}
    </ul>
  )
}
