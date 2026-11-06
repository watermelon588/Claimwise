// Collapsible thread history sidebar (Claude Code / Codex harness style) for switching Claimwise sessions.
import { useEffect, useState } from 'react'
import {
  FileText,
  Home,
  LogOut,
  MessageSquare,
  PanelLeftClose,
  PanelLeftOpen,
  Plus,
  Search,
  Trash2,
} from 'lucide-react'
import { EYEBROW, ICON } from './tokens.js'
import { Brand } from './ui.jsx'

const STAGE_BADGES = {
  onboarding: { label: 'Setup', tone: 'border-milk/20 bg-milk/8 text-milk/75' },
  preparing: { label: 'Preparing', tone: 'border-amber/30 bg-amber-soft/15 text-amber' },
  approved_to_submit: { label: 'Ready', tone: 'border-coral/40 bg-coral/15 text-coral' },
  submitted: { label: 'Submitted', tone: 'border-sage/35 bg-sage-soft/15 text-sage' },
  query_raised: { label: 'Query', tone: 'border-coral/50 bg-coral/20 text-coral' },
  decided: { label: 'Decided', tone: 'border-milk/30 bg-milk/12 text-milk' },
  payment_reported: { label: 'Payout', tone: 'border-amber/30 bg-amber-soft/15 text-amber' },
  payment_verified: { label: 'Paid', tone: 'border-sage/40 bg-sage-soft/20 text-sage' },
  payment_mismatch: { label: 'Discrepancy', tone: 'border-coral/50 bg-coral/20 text-coral' },
}

/**
 * Collapsible Thread History Sidebar.
 * Lets users create new threads, switch between existing checkpointer sessions,
 * inspect thread stage/document/message counts, or return to the Landing Page.
 * @param {{cw: object, user: object|null, onGoHome: () => void, onSignOut: () => void}} props
 */
export default function HistorySidebar({ cw, user, onGoHome, onSignOut }) {
  const [open, setOpen] = useState(false)
  const [query, setQuery] = useState('')

  const activeThread = cw.threads.find((t) => t.thread_id === cw.threadId)
  const shortActiveId = cw.threadId ? cw.threadId.slice(0, 8) : '--------'

  const filtered = cw.threads.filter((item) => {
    const q = query.trim().toLowerCase()
    if (!q) return true
    return (
      (item.title || '').toLowerCase().includes(q) ||
      (item.thread_id || '').toLowerCase().includes(q) ||
      (item.stage || '').toLowerCase().includes(q)
    )
  })

  useEffect(() => {
    if (!open) return undefined
    function onKeyDown(e) {
      if (e.key === 'Escape') setOpen(false)
    }
    window.addEventListener('keydown', onKeyDown)
    return () => window.removeEventListener('keydown', onKeyDown)
  }, [open])

  function handleSelect(id) {
    cw.selectThread(id)
    setOpen(false)
  }

  function handleCreate() {
    cw.createThread()
    setOpen(false)
  }

  return (
    <>
      {/* One toolbar groups the workspace controls without hiding their actions. */}
      <div role="group" aria-label="Claim workspace controls" className="fixed top-4 right-4 z-40 inline-flex divide-x divide-line overflow-hidden rounded-xl border border-line bg-paper text-ink lg:top-20 lg:right-6">
        <button
          type="button"
          onClick={() => setOpen(true)}
          aria-label="Open claim sessions"
          aria-expanded={open}
          aria-controls="claim-thread-history"
          title={activeThread?.title || 'Open claim sessions'}
          className="inline-flex min-h-10 items-center gap-1.5 px-2.5 text-xs font-semibold transition-colors hover:bg-milk-deep focus-visible:-outline-offset-2 lg:px-3"
        >
          <PanelLeftOpen {...ICON} size={14} className="text-coral" />
          <span className="hidden lg:inline">Sessions</span>
          <span className="rounded-md bg-ink/8 px-1.5 py-0.5 font-mono text-[10px] font-normal text-muted">
            {cw.threads.length}
          </span>
        </button>

        <button
          type="button"
          onClick={handleCreate}
          disabled={cw.busy}
          title="Start a new claim thread"
          aria-label="Start a new claim thread"
          className="inline-flex min-h-10 items-center gap-1.5 px-2.5 text-xs font-semibold transition-colors hover:bg-milk-deep focus-visible:-outline-offset-2 disabled:opacity-40 lg:px-3"
        >
          <Plus {...ICON} size={14} className="text-coral" />
          <span className="hidden lg:inline">New</span>
        </button>

        <button
          type="button"
          onClick={onGoHome}
          title="Back to Claimwise Home"
          className="inline-flex min-h-10 items-center gap-1.5 px-2.5 text-xs font-semibold transition-colors hover:bg-milk-deep focus-visible:-outline-offset-2 lg:px-3"
          aria-label="Back to Claimwise Home"
        >
          <Home {...ICON} size={14} />
          <span className="hidden lg:inline">Home</span>
        </button>
      </div>

      {/* Backdrop when drawer is open */}
      {open && (
        <div
          className="fixed inset-0 z-50 bg-ink/45 backdrop-blur-[2px] transition-opacity"
          onClick={() => setOpen(false)}
          aria-hidden="true"
        />
      )}

      {/* Collapsible Claude Code / Codex style Thread Harness Sidebar */}
      <aside
        id="claim-thread-history"
        aria-label="Claim thread history"
        aria-hidden={!open}
        data-lenis-prevent
        className={`on-ink fixed inset-y-0 left-0 z-50 flex w-[22rem] max-w-[90vw] flex-col border-r border-milk/12 bg-ink text-milk shadow-2xl transition-transform duration-300 ease-out ${
          open ? 'translate-x-0' : '-translate-x-full pointer-events-none'
        }`}
      >
        {/* Header */}
        <div className="flex h-16 shrink-0 items-center justify-between border-b border-milk/10 px-5">
          <div className="flex items-center gap-2.5">
            <Brand />
            <span className="rounded-md border border-milk/15 bg-milk/8 px-1.5 py-0.5 font-mono text-[10px] uppercase tracking-wider text-milk/70">
              Threads
            </span>
          </div>
          <button
            type="button"
            onClick={() => setOpen(false)}
            className="inline-flex size-8 items-center justify-center rounded-lg text-milk/60 transition-colors hover:bg-milk/10 hover:text-milk"
            aria-label="Close thread history sidebar"
          >
            <PanelLeftClose {...ICON} size={16} />
          </button>
        </div>

        {/* New thread + Search */}
        <div className="space-y-3 border-b border-milk/10 p-4">
          <button
            type="button"
            onClick={handleCreate}
            disabled={cw.busy}
            className="flex h-10 w-full items-center justify-between rounded-xl bg-coral px-4 text-xs font-normal text-milk shadow-sm transition-transform hover:bg-coral/90 active:scale-[0.99] disabled:opacity-40"
          >
            <span className="inline-flex items-center gap-2">
              <Plus {...ICON} size={15} />
              <span>New Claim Session</span>
            </span>
            <span className="font-mono text-[10px] opacity-80">#{shortActiveId}</span>
          </button>

          {cw.threads.length > 3 && (
            <div className="relative">
              <Search
                {...ICON}
                size={14}
                className="pointer-events-none absolute top-1/2 left-3 -translate-y-1/2 text-milk/40"
              />
              <input
                type="search"
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                placeholder="Filter threads..."
                className="h-9 w-full rounded-lg border border-milk/12 bg-milk/5 pr-3 pl-8 text-xs font-light text-milk placeholder:text-milk/40 focus:border-milk/35 focus:outline-none"
              />
            </div>
          )}
        </div>

        {/* Thread list */}
        <div className="flex-1 space-y-1.5 overflow-y-auto px-3 py-3">
          <div className="flex items-center justify-between px-2 py-1">
            <span className={`${EYEBROW} text-milk/45`}>Sessions</span>
            <span className="font-mono text-[10px] text-milk/40">{filtered.length}</span>
          </div>

          {filtered.map((item) => {
            const isCurrent = item.thread_id === cw.threadId
            const badge = STAGE_BADGES[item.stage] ?? STAGE_BADGES.onboarding
            const shortId = (item.thread_id || '').slice(0, 8)

            return (
              <div
                key={item.thread_id}
                className={`group relative flex items-start justify-between gap-2 rounded-xl border p-3 transition-colors ${
                  isCurrent
                    ? 'border-coral/50 bg-milk/10 text-milk'
                    : 'border-transparent bg-milk/[0.03] text-milk/80 hover:border-milk/12 hover:bg-milk/[0.07]'
                }`}
              >
                <button
                  type="button"
                  onClick={() => handleSelect(item.thread_id)}
                  className="min-w-0 flex-1 text-left"
                >
                  <div className="flex items-center gap-2">
                    <span
                      className={`size-1.5 shrink-0 rounded-full ${
                        isCurrent ? 'bg-coral' : 'bg-milk/25'
                      }`}
                      aria-hidden="true"
                    />
                    <p className="truncate text-xs font-normal text-milk">
                      {item.title || 'New Claim Session'}
                    </p>
                  </div>

                  <div className="mt-2 flex flex-wrap items-center gap-1.5 pl-3.5">
                    <span
                      className={`inline-flex items-center rounded border px-1.5 py-0.5 font-mono text-[10px] font-light ${badge.tone}`}
                    >
                      {badge.label}
                    </span>
                    <span className="font-mono text-[10px] text-milk/45">#{shortId}</span>
                    {item.claim_type && (
                      <span className="rounded bg-milk/8 px-1.5 py-0.5 font-mono text-[10px] capitalize text-milk/60">
                        {item.claim_type}
                      </span>
                    )}
                  </div>

                  <div className="mt-2 flex items-center gap-3 pl-3.5 text-[11px] font-light text-milk/50">
                    <span className="inline-flex items-center gap-1">
                      <FileText {...ICON} size={11} />
                      <span>{item.doc_count ?? 0}</span>
                    </span>
                    <span className="inline-flex items-center gap-1">
                      <MessageSquare {...ICON} size={11} />
                      <span>{item.message_count ?? 0}</span>
                    </span>
                  </div>
                </button>

                <button
                  type="button"
                  onClick={() => cw.deleteThread(item.thread_id)}
                  title="Remove session from sidebar"
                  aria-label={`Remove ${item.title || 'session'}`}
                  className="mt-0.5 inline-flex size-7 shrink-0 items-center justify-center rounded-lg text-milk/35 opacity-0 transition-opacity hover:bg-milk/10 hover:text-coral group-hover:opacity-100 focus:opacity-100"
                >
                  <Trash2 {...ICON} size={13} />
                </button>
              </div>
            )
          })}

          {filtered.length === 0 && (
            <p className="px-3 py-6 text-center text-xs font-light text-milk/45">
              No threads match "{query}".
            </p>
          )}
        </div>

        {/* Footer with user profile + Home navigation */}
        <div className="border-t border-milk/10 bg-milk/[0.03] p-4 space-y-2.5">
          {user && (
            <div className="flex items-center justify-between gap-2 rounded-xl border border-milk/10 bg-ink px-3 py-2">
              <div className="min-w-0">
                <p className="truncate text-xs font-normal text-milk">{user.name}</p>
                <p className="truncate font-mono text-[10px] text-milk/50">
                  {user.email || 'Policyholder'}
                </p>
              </div>
              <button
                type="button"
                onClick={() => {
                  setOpen(false)
                  onSignOut()
                }}
                title="Sign out"
                className="inline-flex size-7 shrink-0 items-center justify-center rounded-lg text-milk/55 transition-colors hover:bg-milk/10 hover:text-coral"
                aria-label="Sign out"
              >
                <LogOut {...ICON} size={14} />
              </button>
            </div>
          )}

          <button
            type="button"
            onClick={() => {
              setOpen(false)
              onGoHome()
            }}
            className="inline-flex h-8 w-full items-center justify-center gap-1.5 rounded-lg border border-milk/15 bg-milk/5 text-xs font-light text-milk/85 transition-colors hover:bg-milk/12"
          >
            <Home {...ICON} size={13} />
            <span>Home</span>
          </button>
        </div>
      </aside>
    </>
  )
}
