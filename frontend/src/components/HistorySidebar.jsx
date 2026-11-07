// Collapsible thread history sidebar (Claude Code / Codex harness style) for switching Claimwise sessions.
import { useRef, useState } from 'react'
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
  const drawer = useRef(null)
  const [query, setQuery] = useState('')

  const activeThread = cw.threads.find((t) => t.thread_id === cw.threadId)

  const filtered = cw.threads.filter((item) => {
    const q = query.trim().toLowerCase()
    if (!q) return true
    return (
      (item.title || '').toLowerCase().includes(q) ||
      (item.thread_id || '').toLowerCase().includes(q) ||
      (item.stage || '').toLowerCase().includes(q)
    )
  })

  /** Open an existing session and return focus to the workspace. */
  function handleSelect(id) {
    cw.selectThread(id)
    drawer.current.close()
  }

  /** Start a blank claim from the vertical session list. */
  function handleCreate() {
    if (cw.createThread()) drawer.current.close()
  }

  /** Confirm deletion before asking the server to erase the session. */
  async function handleDelete(item) {
    if (window.confirm(`Permanently delete “${item.title}” and its conversation and uploads?`)) {
      const deleted = await cw.deleteThread(item.thread_id)
      if (!deleted) drawer.current?.close()
    }
  }

  return (
    <>
        <button
          type="button"
          onClick={() => drawer.current.showModal()}
          aria-label="Open claim sessions"
          aria-haspopup="dialog"
          aria-controls="claim-thread-history"
          title={activeThread?.title || 'Open claim sessions'}
          className="inline-flex min-h-10 shrink-0 items-center gap-1.5 rounded-lg border border-milk/15 px-2.5 text-xs font-medium hover:bg-milk/10"
        >
          <PanelLeftOpen {...ICON} size={14} className="text-coral" />
          <span>Sessions</span>
          <span className="rounded-md bg-milk/10 px-1.5 py-0.5 font-mono text-[10px] text-milk/70">
            {cw.threads.length}
          </span>
        </button>

      <dialog
        ref={drawer}
        id="claim-thread-history"
        aria-label="Claim sessions"
        data-lenis-prevent
        className="on-ink fixed inset-y-0 left-0 right-auto m-0 h-dvh max-h-none w-[22rem] max-w-[90vw] flex-col border-r border-milk/12 bg-ink p-0 text-milk shadow-2xl backdrop:bg-ink/45 open:flex"
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
            onClick={() => drawer.current.close()}
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
        <div className="min-h-0 flex-1 space-y-1.5 overflow-y-auto px-3 py-3">
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
                  disabled={cw.busy}
                  aria-current={isCurrent ? 'true' : undefined}
                  className="min-w-0 flex-1 text-left disabled:opacity-65"
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
                  onClick={() => handleDelete(item)}
                  disabled={cw.busy}
                  title="Delete session"
                  aria-label={`Delete ${item.title || 'session'}`}
                  className="mt-0.5 inline-flex size-8 shrink-0 items-center justify-center rounded-lg text-milk/60 hover:bg-milk/10 hover:text-coral disabled:opacity-40"
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
        <div className="shrink-0 border-t border-milk/10 bg-milk/[0.03] p-4 space-y-2.5">
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
                  drawer.current.close()
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
              drawer.current.close()
              onGoHome()
            }}
            className="inline-flex h-8 w-full items-center justify-center gap-1.5 rounded-lg border border-milk/15 bg-milk/5 text-xs font-light text-milk/85 transition-colors hover:bg-milk/12"
          >
            <Home {...ICON} size={13} />
            <span>Home</span>
          </button>
        </div>
      </dialog>
    </>
  )
}
