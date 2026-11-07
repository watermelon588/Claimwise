// In-chat approval for the case's verified demo providers.
import { useEffect, useEffectEvent, useRef, useState } from 'react'
import { ArrowUpRight, Check, Download, Hospital, Landmark, Mail, Plug, RefreshCw, ShieldCheck, X } from 'lucide-react'
import { Button, Outline, Quiet } from './ui.jsx'
import { EYEBROW, FIELD, ICON } from './tokens.js'

const TOOLS = [
  { id: 'tpa', name: 'Medivista TPA', Icon: ShieldCheck, tone: 'bg-coral-soft text-coral-ink',
    access: 'Check claim status, messages and decisions. Sending claim documents still needs a separate approval.' },
  { id: 'hospital', name: 'Doctor portal', Icon: Hospital, tone: 'bg-teal-100 text-teal-900',
    access: 'Read the Sunrise Hospital demo discharge summary.' },
  { id: 'bank', name: 'Bharat Demo Bank', Icon: Landmark, tone: 'bg-sky-100 text-sky-900',
    access: 'Read demo statement credits for payment follow-up. No transfers.' },
  { id: 'insurer', name: 'Suraksha Insurance', Icon: ShieldCheck, tone: 'bg-amber-100 text-amber-900',
    access: 'Read demo policy coverage dates and limits.' },
  { id: 'email', name: 'Case email', Icon: Mail, tone: 'bg-violet-100 text-violet-900',
    access: 'Send general claim alerts to your demo inbox. Emails contain no claim details or attachments.' },
]

const ERRORS = {
  INVALID_ONBOARDING_CODE: 'That verification code did not match.',
  INVALID_PROVIDER_CODE: 'That provider sign-in code did not match.',
  VERIFICATION_REQUIRED: 'Verify this demo workspace again to continue.',
  PROVIDER_NOT_CONNECTED: 'Approve this provider before opening its records.',
}

async function gateway(thread, suffix = '', method = 'GET', data, signal) {
  const res = await fetch('/connector-api/api/connectors' + suffix, {
    method, signal, credentials: 'same-origin',
    headers: { 'X-Claimwise-Thread': thread, ...(data ? { 'Content-Type': 'application/json' } : {}) },
    ...(data ? { body: JSON.stringify(data) } : {}),
  })
  if (!res.ok) {
    const code = (await res.json().catch(() => null))?.detail?.code
    if (method === 'GET' && suffix === '' && code === 'VERIFICATION_REQUIRED') return null
    throw new Error(ERRORS[code] ?? 'The local demo connector service is unavailable.')
  }
  if (res.status === 204) return null
  return suffix === '/document' ? res.blob() : res.json()
}

/** One scoped provider request, separate from subsequent claim approvals. */
function ProviderRow({ tool, connected, selected, disabled, onSelect, onRemove, onOpen }) {
  const { Icon } = tool
  return (
    <li className="rounded-2xl border border-line bg-paper p-3.5">
      <div className="flex items-start gap-3">
        <span className={`grid size-10 shrink-0 place-items-center rounded-xl ${tool.tone}`}><Icon {...ICON} size={19} /></span>
        <div className="min-w-0 flex-1">
          <p className="text-sm font-semibold">{tool.name}</p>
          <p className="mt-0.5 text-xs leading-relaxed text-muted">{tool.access}</p>
        </div>
        {connected
          ? <span className="inline-flex items-center gap-1 rounded-full bg-teal-50 px-2 py-1 text-[11px] font-semibold text-teal-900"><Check {...ICON} size={12} /> Connected</span>
          : <Outline className="h-8 px-2.5 text-xs" onClick={onSelect} disabled={disabled} aria-expanded={selected}>Connect</Outline>}
      </div>
      {connected && (
        <div className="mt-2 flex flex-wrap gap-2 pl-[3.25rem]">
          {tool.id === 'hospital' && <Quiet className="h-8 text-xs" onClick={onOpen} disabled={disabled}><Download {...ICON} size={14} /> Discharge PDF</Quiet>}
          {tool.id === 'email' && <Quiet className="h-8 text-xs" onClick={onOpen} disabled={disabled}><Mail {...ICON} size={14} /> Open demo inbox</Quiet>}
          <Quiet className="h-8 text-xs" onClick={onRemove} disabled={disabled}>Disconnect</Quiet>
        </div>
      )}
    </li>
  )
}

/** Keep codes in short-lived input state and use server-derived connection status. */
export default function CaseConnectors({ cw }) {
  const dialog = useRef(null)
  const [catalog, setCatalog] = useState(null)
  const [selected, setSelected] = useState('')
  const [code, setCode] = useState('')
  const [approved, setApproved] = useState(false)
  const [working, setWorking] = useState(false)
  const [error, setError] = useState('')
  const [inbox, setInbox] = useState(null)
  const count = catalog?.providers.filter((provider) => provider.connected).length ?? 0
  const canSync = !cw.busy && !cw.pending && !cw.loadingThread
  const poll = useEffectEvent(() => {
    if (document.visibilityState === 'visible') void cw.syncTools(catalog.case_id, false)
  })
  const selectedTool = TOOLS.find((tool) => tool.id === selected)

  useEffect(() => {
    const controller = new AbortController()
    gateway(cw.threadId, '', 'GET', undefined, controller.signal).then(setCatalog).catch(() => {})
    return () => controller.abort()
  }, [cw.threadId])

  useEffect(() => {
    if (!count || !canSync || working) return undefined
    const timer = window.setInterval(poll, 30_000)
    return () => window.clearInterval(timer)
  }, [count, canSync, working])

  /** Run one gateway action at a time and keep errors local to the approval panel. */
  async function run(operation) {
    setWorking(true)
    setError('')
    try {
      await operation()
    } catch (err) {
      setError(err.message)
    } finally {
      setWorking(false)
    }
  }

  function select(provider) {
    setSelected(provider)
    setCode('')
    setApproved(false)
  }

  async function reload(sync = false) {
    const latest = await gateway(cw.threadId)
    setCatalog(latest)
    if (sync && latest && canSync && !(await cw.syncTools(latest.case_id))) {
      throw new Error('Your provider permissions were saved. Refresh the tools after the case finishes its current step.')
    }
    return latest
  }

  function open() {
    dialog.current.showModal()
    run(() => reload())
  }

  function verify(e) {
    e.preventDefault()
    run(async () => {
      await gateway(cw.threadId, '/session', 'POST', { code: code.trim() })
      select('')
      await reload()
    })
  }

  function connect(e) {
    e.preventDefault()
    run(async () => {
      await gateway(cw.threadId, '/' + selected, 'POST', { code: code.trim(), approved })
      select('')
      await reload(true)
    })
  }

  function remove(provider) {
    run(async () => {
      await gateway(cw.threadId, '/' + provider, 'DELETE')
      if (provider === 'email') setInbox(null)
      await reload(true)
    })
  }

  function viewResource(provider) {
    run(async () => {
      if (provider === 'email') {
        const data = await gateway(cw.threadId, '/inbox')
        setInbox(data.messages)
        return
      }
      const pdf = await gateway(cw.threadId, '/document')
      if (pdf.type !== 'application/pdf') throw new Error('The discharge summary is unavailable.')
      const url = URL.createObjectURL(pdf)
      const link = document.createElement('a')
      link.href = url
      link.download = 'mock-discharge-summary.pdf'
      link.click()
      window.setTimeout(() => URL.revokeObjectURL(url), 30_000)
    })
  }

  return (
    <>
      <section aria-label="Connected tools" className="mt-5 flex flex-wrap items-center gap-3 rounded-2xl border border-line bg-paper p-3.5 sm:p-4">
        <span className="grid size-10 shrink-0 place-items-center rounded-xl bg-coral-soft text-coral-ink"><Plug {...ICON} size={19} /></span>
        <div className="min-w-0 flex-1">
          <p className="text-sm font-semibold">{count ? `Connected tools · ${count}` : 'Let Pip check with your providers'}</p>
          <p className="text-xs leading-relaxed text-muted">Approve access to receive provider updates and case email.</p>
        </div>
        <Outline className="h-9 whitespace-nowrap text-xs" onClick={open}>{count ? 'Manage tools' : 'Connect tools'} <ArrowUpRight {...ICON} size={14} /></Outline>
      </section>

      <dialog ref={dialog} aria-labelledby="case-connectors-title" onClose={() => { select(''); setError(''); setInbox(null) }}
        className="fixed inset-0 m-auto max-h-[calc(100dvh-1rem)] w-[min(36rem,calc(100%-1rem))] overflow-auto rounded-2xl border border-line bg-milk p-0 text-ink shadow-xl backdrop:bg-ink/45" data-lenis-prevent>
        <header className="sticky top-0 z-10 flex items-start justify-between gap-4 border-b border-line bg-milk px-5 py-4 sm:px-6">
          <div>
            <p className={EYEBROW}>Pip · Demo workspace</p>
            <h2 id="case-connectors-title" className="mt-1 text-xl font-semibold tracking-tight">Connect tools</h2>
            <p className="mt-1 text-sm text-muted">Choose which providers can share updates for this case.</p>
          </div>
          <Quiet className="h-9 px-2" aria-label="Close connected tools" onClick={() => dialog.current.close()}><X {...ICON} size={18} /></Quiet>
        </header>
        <div className="space-y-4 px-5 py-4 sm:px-6">
          {error && <p role="alert" className="rounded-lg bg-coral-soft px-3 py-2 text-sm text-coral-ink">{error}</p>}
          {!catalog ? (
            <form onSubmit={verify} className="space-y-3 rounded-2xl border border-line bg-paper p-4">
              <h3 className="text-sm font-semibold">Verify this demo case</h3>
              <p className="text-xs leading-relaxed text-muted">Use the demo workspace setup code displayed by the local connector service.</p>
              <label className="flex flex-col gap-2 text-xs font-semibold">
                <span>Workspace verification code</span>
                <input className={FIELD} type="password" value={code} onChange={(e) => setCode(e.target.value)} autoComplete="off" maxLength={128} required />
              </label>
              <Button type="submit" disabled={working || !canSync}>Verify case</Button>
            </form>
          ) : (
            <>
              <ul className="space-y-2.5">
                {TOOLS.map((tool) => (
                  <ProviderRow key={tool.id} tool={tool} connected={catalog.providers.some((p) => p.provider === tool.id && p.connected)}
                    selected={selected === tool.id} disabled={working} onSelect={() => select(tool.id)}
                    onRemove={() => remove(tool.id)} onOpen={() => viewResource(tool.id)} />
                ))}
              </ul>
              {selectedTool && (
                <form onSubmit={connect} className="space-y-3 rounded-2xl border border-coral/50 bg-paper p-4">
                  <h3 className="text-sm font-semibold">Approve {selectedTool.name}</h3>
                  <label className="flex flex-col gap-2 text-xs font-semibold">
                    <span>Demo provider sign-in code</span>
                    <input autoFocus className={FIELD} type="password" value={code} onChange={(e) => setCode(e.target.value)} autoComplete="off" maxLength={128} required />
                  </label>
                  <label className="flex items-start gap-2 text-sm">
                    <input type="checkbox" className="mt-1 accent-coral" checked={approved} onChange={(e) => setApproved(e.target.checked)} />
                    <span>I approve this access for the current case.</span>
                  </label>
                  <div className="flex flex-wrap gap-2">
                    <Button type="submit" disabled={working || !approved || !canSync}>Approve and connect</Button>
                    <Quiet onClick={() => select('')} type="button">Cancel</Quiet>
                  </div>
                </form>
              )}
              {inbox && (
                <section aria-label="Demo inbox" className="rounded-2xl border border-line bg-paper p-4">
                  <h3 className="text-sm font-semibold">Demo inbox</h3>
                  {inbox.length ? <ul className="mt-2 divide-y divide-line">
                    {inbox.map((mail) => <li key={mail.id} className="py-2 text-xs"><strong>{mail.subject}</strong><p className="mt-1 text-muted">{mail.body}</p></li>)}
                  </ul> : <p className="mt-1 text-xs text-muted">New case updates will appear here.</p>}
                </section>
              )}
              <Outline onClick={() => run(() => reload(true))} disabled={working || !canSync}><RefreshCw {...ICON} size={15} /> Refresh approved tools</Outline>
            </>
          )}
        </div>
      </dialog>
    </>
  )
}
