// Mock test workbench: load a scenario, send a request, and inspect the real response.
import { useRef, useState } from 'react'
import { ArrowLeft, Clock3, Database, FlaskConical, List, RotateCcw } from 'lucide-react'
import { ICON } from '../components/tokens.js'
import { Brand, Button } from '../components/ui.jsx'
import MockPdfSection from './MockPdfSection.jsx'
import { useMockConsole } from './useMockConsole.js'

const GROUPS = { payer: 'Insurer', hospital: 'Hospital', bank: 'Bank', grievance: 'Grievance' }
const TEST_CONTROLS = [
  ['admin-clock-advance', 'Clock', Clock3],
  ['admin-faults-set', 'Failures', FlaskConical],
  ['admin-events', 'Events', List],
  ['admin-overview', 'Test data', Database],
  ['admin-reset', 'Reset', RotateCcw],
]

const ENDPOINTS = [
  {
    id: "payer-decide", group: "payer", title: "Decide claim",
    method: "POST", path: "/payer/claims/{claim_id}/decide",
    params: [{"name":"claim_id","location":"path","value":"CLM-0001"}],
    body: {
      "outcome": "approved",
      "rejection_reason": null,
      "policy_clause": null,
      "line_decisions": null
    },
  },
  {
    id: "payer-pay", group: "payer", title: "Send settlement",
    method: "POST", path: "/payer/claims/{claim_id}/pay",
    params: [{"name":"claim_id","location":"path","value":"CLM-0001"}],
    body: {
      "payee": "member",
      "bank_account_last4": "8921",
      "credit_amount_override": null,
      "credit_delay_days": 0,
      "utr_override": null,
      "skip_credit": false
    },
  },
  {
    id: "payer-query", group: "payer", title: "Request more documents",
    method: "POST", path: "/payer/claims/{claim_id}/query",
    params: [{"name":"claim_id","location":"path","value":"CLM-0001"}],
    body: {
      "items": [
        {
          "code": "DOC_HISTO",
          "label": "Histopathology Biopsy Report",
          "description": "Please provide signed histopathology report for appendectomy."
        }
      ],
      "due_days": 15,
      "inject_malicious": false
    },
  },
  {
    id: "payer-submit-claim", group: "payer", title: "Submit claim",
    method: "POST", path: "/payer/claims",
    headers: {"X-Api-Key":"claimwise-demo-key","Idempotency-Key":"idem-demo-001"},
    body: {
      "client_reference": "CLIENT-REF-001",
      "policy_number": "SURAKSHA-HEALTH-2026-001",
      "member_name": "Ramesh Sharma",
      "acting_user": "Ramesh Sharma",
      "claim_type": "reimbursement",
      "admission_date": "2026-10-02",
      "discharge_date": "2026-10-05",
      "claimed_amount": 6000000,
      "line_items": [
        {
          "head": "Room Rent",
          "amount": 1500000
        },
        {
          "head": "Surgeon Fees",
          "amount": 3500000
        },
        {
          "head": "Medicines",
          "amount": 1000000
        }
      ],
      "documents": [
        {
          "doc_type": "discharge_summary",
          "filename": "02_valid_discharge_summary.pdf"
        }
      ]
    },
  },
  {
    id: "payer-get-claim", group: "payer", title: "View claim",
    method: "GET", path: "/payer/claims/{claim_id}",
    params: [{"name":"claim_id","location":"path","value":"CLM-0001"}],
  },
  {
    id: "payer-list-claims", group: "payer", title: "List claims",
    method: "GET", path: "/payer/claims",
    params: [{"name":"client_reference","location":"query","value":""}],
  },
  {
    id: "payer-answer-query", group: "payer", title: "Answer a request",
    method: "POST", path: "/payer/claims/{claim_id}/documents",
    params: [{"name":"claim_id","location":"path","value":"CLM-0001"}],
    body: {
      "documents": [
        {
          "doc_type": "investigation_report",
          "filename": "biopsy_report.pdf"
        }
      ]
    },
  },
  {
    id: "payer-reopen", group: "payer", title: "Reopen claim",
    method: "POST", path: "/payer/claims/{claim_id}/reopen",
    params: [{"name":"claim_id","location":"path","value":"CLM-0001"}],
    body: {},
  },
  {
    id: "payer-withdraw", group: "payer", title: "Withdraw claim",
    method: "POST", path: "/payer/claims/{claim_id}/withdraw",
    params: [{"name":"claim_id","location":"path","value":"CLM-0001"}],
    body: {},
  },
  {
    id: "payer-get-policy", group: "payer", title: "View policy",
    method: "GET", path: "/payer/policies/{policy_number}",
    params: [{"name":"policy_number","location":"path","value":"SURAKSHA-HEALTH-2026-001"}],
  },
  {
    id: "payer-eligibility", group: "payer", title: "Check eligibility",
    method: "POST", path: "/payer/eligibility",
    body: {
      "policy_number": "SURAKSHA-HEALTH-2026-001",
      "member_name": "Ramesh Sharma",
      "treatment_date": "2026-10-02"
    },
  },
  {
    id: "payer-preauth", group: "payer", title: "Request cashless approval",
    method: "POST", path: "/payer/preauths",
    headers: {"X-Api-Key":"hospital-demo-key"},
    body: {
      "policy_number": "SURAKSHA-HEALTH-2026-001",
      "member_name": "Ramesh Sharma",
      "hospital_id": "HOSP-001",
      "admission_date": "2026-10-02",
      "diagnosis_text": "Acute Appendicitis (ICD K35.8)",
      "estimated_amount": 5500000
    },
  },
  {
    id: "hospital-create-admission", group: "hospital", title: "Admit patient",
    method: "POST", path: "/hospital/admissions",
    headers: {"X-Api-Key":"hospital-demo-key"},
    body: {
      "hospital_id": "HOSP-001",
      "patient_name": "Ramesh Sharma",
      "policy_number": "SURAKSHA-HEALTH-2026-001",
      "admission_date": "2026-10-02",
      "diagnosis_text": "Acute Appendicitis (Laparoscopic Appendectomy)",
      "deposit_amount": 1000000
    },
  },
  {
    id: "hospital-discharge", group: "hospital", title: "Discharge patient",
    method: "POST", path: "/hospital/admissions/{admission_id}/discharge",
    params: [{"name":"admission_id","location":"path","value":"ADM-0001"},{"name":"discharge_date","location":"query","value":"2026-10-05"}],
    headers: {"X-Api-Key":"hospital-demo-key"},
    body: {},
  },
  {
    id: "hospital-reissue", group: "hospital", title: "Reissue document",
    method: "POST", path: "/hospital/documents/{doc_id}/reissue",
    params: [{"name":"doc_id","location":"path","value":"DOC-DS-ADM-0001"}],
    body: {
      "corrected_diagnosis": "Acute Appendicitis (Symptom duration 48 hours, no prior history)",
      "corrected_line_items": null
    },
  },
  {
    id: "bank-statement", group: "bank", title: "View bank statement",
    method: "GET", path: "/bank/accounts/{account_id}/statement",
    params: [{"name":"account_id","location":"path","value":"ACC-001"}],
  },
  {
    id: "bank-post-credit", group: "bank", title: "Post bank credit",
    method: "POST", path: "/bank/accounts/{account_id}/credits",
    params: [{"name":"account_id","location":"path","value":"ACC-001"}],
    headers: {"X-Api-Key":"claimwise-demo-key"},
    body: {
      "amount": 4230000,
      "utr": "UTR-BDBL92817261",
      "narration": "NEFT/SURAKSHA/CLM-0001",
      "credited_at": null
    },
  },
  {
    id: "grievance-file", group: "grievance", title: "File grievance",
    method: "POST", path: "/grievance/grievances",
    headers: {"X-Api-Key":"claimwise-demo-key"},
    body: {
      "claim_id": "CLM-0001",
      "level": "insurer_gro",
      "complaint_text": "Disputing proportionate room-rent deduction on consumables."
    },
  },
  {
    id: "grievance-resolve", group: "grievance", title: "Resolve grievance",
    method: "POST", path: "/grievance/grievances/{grievance_id}/resolve",
    params: [{"name":"grievance_id","location":"path","value":"GRV-0001"}],
    body: {
      "status": "resolved",
      "resolution_text": "Grievance upheld: non-payable deduction reversed."
    },
  },
  {
    id: "ombudsman-file", group: "grievance", title: "File Ombudsman complaint",
    method: "POST", path: "/grievance/ombudsman",
    headers: {"X-Api-Key":"claimwise-demo-key"},
    body: {
      "grievance_id": "GRV-0001",
      "claim_id": "CLM-0001",
      "complaint_summary": "Insurer rejected claim citing pre-existing condition without evidence."
    },
  },
  {
    id: "ombudsman-award", group: "grievance", title: "Issue award",
    method: "POST", path: "/grievance/ombudsman/{ombudsman_id}/award",
    params: [{"name":"ombudsman_id","location":"path","value":"OMB-0001"}],
    body: {
      "award_amount": 6000000,
      "award_notes": "Insurer directed to settle full claim within 30 days.",
      "reopen_claim": true
    },
  },
  {
    id: "ombudsman-comply", group: "grievance", title: "Confirm award compliance",
    method: "POST", path: "/grievance/ombudsman/{ombudsman_id}/comply",
    params: [{"name":"ombudsman_id","location":"path","value":"OMB-0001"},{"name":"complied","location":"query","value":"true"}],
    body: {},
  },
  {
    id: "admin-scenario-load", group: "admin", title: "Load scenario",
    method: "POST", path: "/admin/scenarios/{name}",
    params: [{"name":"name","location":"path","value":"standard_reimbursement"}],
    body: {},
  },
  {
    id: "admin-clock-advance", group: "admin", title: "Advance test clock",
    method: "POST", path: "/admin/clock/advance",
    body: {
      "days": 15,
      "hours": 0,
      "minutes": 0
    },
  },
  {
    id: "admin-faults-set", group: "admin", title: "Simulate a failure",
    method: "POST", path: "/admin/faults",
    body: {
      "drop_response_after_commit": false,
      "delay_ms": 0,
      "error_rate": 0,
      "duplicate_webhooks": false,
      "webhook_down": false
    },
  },
  {
    id: "admin-events", group: "admin", title: "View events",
    method: "GET", path: "/events",
    params: [{"name":"after","location":"query","value":""}],
  },
  {
    id: "admin-overview", group: "admin", title: "View test data",
    method: "GET", path: "/admin/overview",
  },
  {
    id: "admin-reset", group: "admin", title: "Reset test data",
    method: "POST", path: "/admin/reset",
    body: {},
  },
]

const FIELD = 'min-h-10 w-full min-w-0 rounded-lg border border-line bg-paper px-3 text-sm text-ink'

/** Format a short human label for a scenario or parameter name. */
function label(value) {
  return value.replaceAll('_', ' ').replace(/^./, (first) => first.toUpperCase()).replace(/ id$/, ' ID')
}

/** Use the current scenario's IDs until the tester enters a different value. */
function parameterValue(parameter, values, overview) {
  const first = {
    claim_id: overview?.claims?.[0]?.id,
    admission_id: overview?.admissions?.[0]?.id,
    grievance_id: overview?.grievances?.[0]?.id,
    ombudsman_id: overview?.ombudsman_complaints?.[0]?.id,
    account_id: overview?.bank_accounts?.[0]?.id,
    doc_id: overview?.hospital_documents?.[0]?.id,
    policy_number: overview?.policies?.[0]?.policy_number,
  }
  return String(values[parameter.name] ?? first[parameter.name] ?? parameter.value ?? '')
}

/** Build the selected operation's URL from editable path and query values. */
function buildPath(endpoint, values, overview) {
  let path = endpoint.path
  const query = new URLSearchParams()
  for (const parameter of endpoint.params ?? []) {
    const value = parameterValue(parameter, values, overview).trim()
    if (parameter.location === 'path') path = path.replace(`{${parameter.name}}`, encodeURIComponent(value))
    else if (value) query.set(parameter.name, value)
  }
  return query.size ? `${path}?${query}` : path
}

/** Show the last test result and direct the tester to any generated PDFs. */
function TestResponse({ result, busy }) {
  const formatted = typeof result?.data === 'string' ? result.data : JSON.stringify(result?.data, null, 2)
  const pdfIssued = result?.ok && (
    result.data?.letter_doc_id || result.data?.discharge_summary_doc_id || result.data?.reissued_doc_id
  )
  return (
    <section className="min-w-0 border-t border-line p-5 lg:border-t-0 lg:border-l sm:p-6" aria-labelledby="mock-response-title">
      <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
        <h3 id="mock-response-title" className="text-sm font-semibold">Response</h3>
        {result && (
          <span role="status" className={`rounded-md px-2 py-0.5 text-xs font-medium ${result.ok ? 'bg-milk-deep text-ink' : 'bg-coral-soft text-coral-ink'}`}>
            {result.status ?? 'Connection lost'}
          </span>
        )}
      </div>
      {result ? (
        <>
          <p className="mb-2 text-xs text-muted">{result.title}</p>
          <pre className="max-h-96 min-h-36 overflow-auto rounded-xl bg-ink p-4 font-mono text-xs leading-relaxed whitespace-pre-wrap wrap-anywhere text-milk" data-lenis-prevent>
            {formatted ?? 'Empty response'}
          </pre>
          {pdfIssued && (
            <a className="mt-3 inline-flex text-xs font-semibold text-coral-ink hover:underline" href="#mock-pdfs-title">
              Go to PDF downloads
            </a>
          )}
        </>
      ) : (
        <p role="status" className="grid min-h-36 place-items-center rounded-xl border border-dashed border-line px-5 text-center text-sm text-muted">
          {busy ? 'Waiting for the response…' : 'Run a request to see its response here.'}
        </p>
      )}
    </section>
  )
}

/** Run one test operation at a time and keep its response beside the request. */
export default function MockConsole({ onBackToApp }) {
  const { connection, busy, result, reconnect, execute, clearResult } = useMockConsole()
  const [scenario, setScenario] = useState('standard_reimbursement')
  const [selected, setSelected] = useState('payer-list-claims')
  const [values, setValues] = useState({})
  const [body, setBody] = useState('')
  const [formError, setFormError] = useState('')
  const requestTitle = useRef(null)
  const endpoint = ENDPOINTS.find((item) => item.id === selected)
  const overview = connection?.overview
  const unavailable = !connection?.base || busy

  /** Replace the editor with the selected operation's ready-to-edit example. */
  function selectOperation(id) {
    const operation = ENDPOINTS.find((item) => item.id === id)
    setSelected(id)
    setValues({})
    setBody(operation.body === undefined ? '' : JSON.stringify(operation.body, null, 2))
    setFormError('')
    clearResult()
  }

  /** Open the request editor from the test toolbar or a PDF generator. */
  function openOperation(id) {
    selectOperation(id)
    requestTitle.current?.focus()
  }

  /** Load a preset scenario and let request parameters pick up the new IDs. */
  async function loadScenario(event) {
    event.preventDefault()
    setFormError('')
    const operation = ENDPOINTS.find((item) => item.id === 'admin-scenario-load')
    const response = await execute({ ...operation, path: buildPath(operation, { name: scenario }) })
    if (response?.ok) setValues({})
  }

  /** Validate JSON locally, then submit it to the selected mock operation. */
  async function sendRequest(event) {
    event.preventDefault()
    setFormError('')
    let payload
    if (endpoint.method !== 'GET' && body.trim()) {
      try {
        payload = JSON.stringify(JSON.parse(body))
      } catch {
        setFormError('Enter valid JSON before sending.')
        return
      }
    }
    const response = await execute({ ...endpoint, path: buildPath(endpoint, values, overview), body: payload })
    if (response?.ok && selected === 'admin-reset') {
      setValues({})
      setScenario('standard_reimbursement')
    }
  }

  return (
    <div className="min-h-dvh bg-milk text-ink">
      <header className="mx-auto flex h-17 max-w-6xl items-center justify-between border-b border-line px-5 sm:px-9">
        <Brand />
        <button type="button" onClick={onBackToApp} className="inline-flex min-h-10 items-center gap-2 rounded-lg px-2 text-sm font-medium text-muted hover:text-ink">
          <ArrowLeft {...ICON} /> Home
        </button>
      </header>
      <main className="mx-auto max-w-6xl space-y-6 px-5 py-8 sm:px-9 sm:py-11">
        <h1 className="text-3xl font-semibold tracking-[-0.035em] sm:text-4xl">Mock Console</h1>
        {connection && !connection.base && (
          <div className="flex flex-wrap items-center justify-between gap-2 rounded-xl border border-coral/40 bg-coral-soft/45 px-4 py-3">
            <p role="status" className="text-sm">Mock service is offline. Start it, then try again.</p>
            <Button onClick={reconnect}>Try again</Button>
          </div>
        )}
        <section className="rounded-2xl border border-line bg-paper p-5 sm:p-6" aria-labelledby="mock-scenario-title">
          <div className="flex flex-wrap items-end justify-between gap-5">
            <div className="min-w-0 flex-1">
              <h2 id="mock-scenario-title" className="text-base font-semibold">Test scenario</h2>
              <p className="mt-1 text-xs text-muted">Loading a scenario replaces the mock test data.</p>
            </div>
            <form onSubmit={loadScenario} className="flex w-full flex-wrap items-end gap-2 sm:w-auto">
              <label className="min-w-0 flex-1 sm:min-w-64">
                <span className="sr-only">Test scenario</span>
                <select className={FIELD} value={scenario} onChange={(event) => setScenario(event.target.value)} disabled={unavailable}>
                  {(overview?.scenarios ?? [{ name: 'standard_reimbursement' }]).map(({ name }) => <option key={name} value={name}>{label(name)}</option>)}
                </select>
              </label>
              <Button type="submit" disabled={unavailable}>Load scenario</Button>
            </form>
          </div>
          {overview && (
            <dl className="mt-4 flex flex-wrap gap-x-6 gap-y-1 border-t border-line pt-3 text-xs text-muted">
              {[['Claims', overview.claims], ['Admissions', overview.admissions], ['Bank credits', overview.bank_credits]].map(([title, rows]) => (
                <div key={title} className="flex items-center gap-1.5"><dt>{title}</dt><dd className="font-semibold text-ink">{rows?.length ?? 0}</dd></div>
              ))}
            </dl>
          )}
          <div role="group" aria-label="Test controls" className="mt-4 flex flex-wrap items-center gap-2 border-t border-line pt-4">
            <span className="mr-1 text-xs font-semibold text-muted">Test controls</span>
            {TEST_CONTROLS.map(([id, title, ControlIcon]) => (
              <button
                type="button"
                key={id}
                disabled={busy}
                aria-pressed={selected === id}
                onClick={() => openOperation(id)}
                className="inline-flex min-h-9 items-center gap-1.5 rounded-lg border border-line px-2.5 text-xs font-medium hover:bg-milk-deep aria-pressed:border-ink aria-pressed:bg-milk-deep disabled:opacity-40"
              >
                <ControlIcon {...ICON} size={15} className="text-coral-ink" aria-hidden="true" /> {title}
              </button>
            ))}
          </div>
        </section>

        <MockPdfSection base={connection?.base} overview={overview} result={result} busy={busy} selected={selected} onSelectOperation={openOperation} />

        <section className="overflow-hidden rounded-2xl border border-line bg-paper" aria-label="Run a test">
          <div className="grid lg:grid-cols-2">
            <form onSubmit={sendRequest} className="min-w-0 space-y-4 p-5 sm:p-6">
              <h2 ref={requestTitle} tabIndex={-1} className="text-sm font-semibold">Request · {endpoint.title}</h2>
              <label className="block space-y-1.5 text-xs font-medium text-muted">
                <span>Operation</span>
                <select className={FIELD} value={endpoint.group === 'admin' ? '' : selected} onChange={(event) => selectOperation(event.target.value)} disabled={busy}>
                  <option value="" disabled>Choose a provider operation</option>
                  {Object.entries(GROUPS).map(([group, title]) => (
                    <optgroup key={group} label={title}>
                      {ENDPOINTS.filter((item) => item.group === group).map((item) => (
                        <option key={item.id} value={item.id}>{item.title}</option>
                      ))}
                    </optgroup>
                  ))}
                </select>
              </label>
              {endpoint.params?.length > 0 && (
                <div className="grid gap-2.5 sm:grid-cols-2">
                  {endpoint.params.map((parameter) => (
                    <label key={parameter.name} className="min-w-0 space-y-1.5 text-xs font-medium text-muted">
                      <span>{label(parameter.name)}{parameter.location === 'query' && !parameter.value ? ' (optional)' : ''}</span>
                      <input
                        className={FIELD}
                        value={parameterValue(parameter, values, overview)}
                        onChange={(event) => setValues((previous) => ({ ...previous, [parameter.name]: event.target.value }))}
                        required={parameter.location === 'path'}
                      />
                    </label>
                  ))}
                </div>
              )}
              {endpoint.method !== 'GET' && (
                <label className="block space-y-1.5 text-xs font-medium text-muted">
                  <span>Request body (JSON)</span>
                  <textarea className={`${FIELD} block min-h-36 resize-y bg-milk/45 py-2.5 font-mono text-xs leading-relaxed`} spellCheck={false} value={body} onChange={(event) => setBody(event.target.value)} />
                </label>
              )}
              {selected === 'admin-reset' && <p className="text-xs text-muted">This clears the current mock test data and restores the starter records.</p>}
              {formError && <p role="alert" className="text-xs font-medium text-coral-ink">{formError}</p>}
              <Button type="submit" disabled={unavailable}>{selected === 'admin-reset' ? 'Reset test data' : 'Send request'}</Button>
            </form>
            <TestResponse result={result} busy={busy} />
          </div>
        </section>
      </main>
    </div>
  )
}
