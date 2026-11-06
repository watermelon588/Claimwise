// Mock PDF workbench backed by the existing insurer, hospital and bank routes.
import { useState } from 'react'
import { Download, FileText } from 'lucide-react'
import { ICON } from '../components/tokens.js'
import { Outline } from '../components/ui.jsx'

const GENERATORS = [
  ['hospital-discharge', 'Discharge summary & final bill'],
  ['hospital-reissue', 'Reissue hospital PDF'],
  ['payer-query', 'Insurer query letter'],
  ['payer-decide', 'Insurer decision letter'],
]

/** Collect downloadable documents from the current mock state and latest successful response. */
function issuedDocuments(overview, result) {
  const documents = new Map()

  function add(id, service, title) {
    if (id) documents.set(id, { id, title, path: `/${service}/documents/${encodeURIComponent(id)}.pdf` })
  }

  for (const doc of overview?.hospital_documents ?? []) {
    add(doc.id, 'hospital', doc.doc_type === 'final_bill' ? 'Final bill' : 'Discharge summary')
  }
  for (const claim of overview?.claims ?? []) {
    add(claim.decision?.letter_doc_id, 'payer', 'Decision letter')
  }
  // Query records only have a query ID. The event confirms a letter was generated.
  for (const event of overview?.events ?? []) {
    if (event.event_type === 'claim.query_raised' && event.data?.query_id) {
      add(`DOC-QRY-${event.data.query_id}`, 'payer', 'Query letter')
    }
  }

  if (result?.ok) {
    const data = result.data
    add(data?.letter_doc_id, 'payer', data?.query_id ? 'Query letter' : 'Decision letter')
    add(data?.discharge_summary_doc_id, 'hospital', 'Discharge summary')
    add(data?.final_bill_doc_id, 'hospital', 'Final bill')
    if (!documents.has(data?.reissued_doc_id)) add(data?.reissued_doc_id, 'hospital', 'Reissued hospital document')
  }

  return [...documents.values()]
}

/** Generate on-demand PDFs or download documents issued by mock workflows. */
export default function MockPdfSection({ base, overview, result, busy, selected, onSelectOperation }) {
  const [policy, setPolicy] = useState('')
  const [account, setAccount] = useState('')
  const [downloading, setDownloading] = useState(null)
  const [downloadError, setDownloadError] = useState('')
  const policies = overview?.policies ?? []
  const accounts = overview?.bank_accounts ?? []
  const currentPolicy = policies.find((item) => item.policy_number === policy)?.policy_number ?? policies[0]?.policy_number
  const currentAccount = accounts.find((item) => item.id === account)?.id ?? accounts[0]?.id
  const documents = issuedDocuments(overview, result)
  const downloadDisabled = busy || !base || downloading !== null

  /** Download verified PDF bytes, including through the direct mock-server fallback. */
  async function download(path, filename) {
    setDownloadError('')
    setDownloading(path)
    try {
      const response = await fetch(`${base}${path}`)
      if (!response.ok || response.headers.get('content-type')?.split(';')[0] !== 'application/pdf') {
        throw new Error('PDF unavailable')
      }
      const url = URL.createObjectURL(await response.blob())
      const link = document.createElement('a')
      link.href = url
      link.download = filename
      document.body.append(link)
      link.click()
      link.remove()
      window.setTimeout(() => URL.revokeObjectURL(url), 30000)
    } catch {
      setDownloadError(`Could not download ${filename}. Check the mock service or generate the PDF again.`)
    } finally {
      setDownloading(null)
    }
  }

  const policyPath = `/payer/documents/DOC-POL-${encodeURIComponent(currentPolicy)}.pdf`
  const accountPath = `/bank/accounts/${encodeURIComponent(currentAccount)}/statement.pdf`

  return (
    <section className="rounded-2xl border border-line bg-paper p-5 sm:p-6" aria-labelledby="mock-pdfs-title">
      <h2 id="mock-pdfs-title" className="flex items-center gap-2 text-base font-semibold">
        <FileText {...ICON} size={17} className="text-coral-ink" aria-hidden="true" /> PDF documents
      </h2>
      <div className="mt-4 grid gap-3 sm:grid-cols-2">
        <div className="flex flex-wrap items-center gap-2 rounded-xl border border-line p-3">
          <label className="min-w-36 flex-1 text-xs font-semibold">
            Policy schedule
            <select className="mt-1 block h-9 w-full rounded-lg border border-line bg-paper px-2 text-xs font-normal" value={currentPolicy ?? ''} onChange={(event) => setPolicy(event.target.value)} disabled={!policies.length}>
              {policies.map((item) => <option key={item.policy_number}>{item.policy_number}</option>)}
            </select>
          </label>
          <Outline className="self-end" aria-label="Download policy schedule" disabled={downloadDisabled || !currentPolicy} onClick={() => download(policyPath, `policy-${currentPolicy}.pdf`)}>
            <Download {...ICON} size={15} aria-hidden="true" /> {downloading === policyPath ? 'Downloading…' : 'Download'}
          </Outline>
        </div>
        <div className="flex flex-wrap items-center gap-2 rounded-xl border border-line p-3">
          <label className="min-w-36 flex-1 text-xs font-semibold">
            Bank statement
            <select className="mt-1 block h-9 w-full rounded-lg border border-line bg-paper px-2 text-xs font-normal" value={currentAccount ?? ''} onChange={(event) => setAccount(event.target.value)} disabled={!accounts.length}>
              {accounts.map((item) => <option key={item.id}>{item.id}</option>)}
            </select>
          </label>
          <Outline className="self-end" aria-label="Download bank statement" disabled={downloadDisabled || !currentAccount} onClick={() => download(accountPath, `statement_${currentAccount}.pdf`)}>
            <Download {...ICON} size={15} aria-hidden="true" /> {downloading === accountPath ? 'Downloading…' : 'Download'}
          </Outline>
        </div>
      </div>

      <div className="mt-4 flex flex-wrap items-center gap-2">
        <span className="mr-1 text-xs font-semibold text-muted">Generate with a test request</span>
        {GENERATORS.map(([id, title]) => (
          <button type="button" key={id} disabled={busy} aria-pressed={selected === id} onClick={() => onSelectOperation(id)} className="min-h-9 rounded-lg border border-line px-2.5 text-xs font-medium hover:bg-milk-deep aria-pressed:border-ink aria-pressed:bg-milk-deep disabled:opacity-40">
            {title}
          </button>
        ))}
      </div>

      {documents.length > 0 && (
        <ul className="mt-4 max-h-56 divide-y divide-line overflow-auto border-t border-line" aria-label="Generated PDFs" data-lenis-prevent>
          {documents.map(({ id, path, title }) => (
            <li key={id} className="flex items-center justify-between gap-3 py-2">
              <div className="min-w-0 text-sm font-medium">
                {title}<span className="block wrap-anywhere font-mono text-xs text-muted">{id}</span>
              </div>
              <Outline aria-label={`Download ${title} ${id}`} disabled={downloadDisabled} onClick={() => download(path, `${id}.pdf`)}>
                <Download {...ICON} size={15} aria-hidden="true" /> {downloading === path ? 'Downloading…' : 'Download'}
              </Outline>
            </li>
          ))}
        </ul>
      )}
      {downloadError && <p role="alert" className="mt-3 text-xs text-coral-ink">{downloadError}</p>}
    </section>
  )
}
