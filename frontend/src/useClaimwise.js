// State, activity, multi-thread history and backend calls for Claimwise threads.
import { useEffect, useState } from 'react'
import { docLabel } from './flow.js'

const ACTIVE_THREAD_KEY = 'claimwise_active_thread_v1'
const THREADS_STORAGE_KEY = 'claimwise_threads_v1'

/** Read stored thread records from localStorage safely. */
function readStoredThreads() {
  if (typeof window === 'undefined') return []
  try {
    const raw = window.localStorage.getItem(THREADS_STORAGE_KEY)
    const parsed = raw ? JSON.parse(raw) : []
    return Array.isArray(parsed) ? parsed : []
  } catch {
    return []
  }
}

/** Persist thread metadata array to localStorage safely. */
function writeStoredThreads(threads) {
  if (typeof window === 'undefined') return
  try {
    window.localStorage.setItem(THREADS_STORAGE_KEY, JSON.stringify(threads.slice(0, 35)))
  } catch {
    // Ignore storage quota errors
  }
}

/** Get or create the initial active thread UUID. */
function getInitialThreadId() {
  if (typeof window === 'undefined') return crypto.randomUUID()
  try {
    const stored = window.localStorage.getItem(ACTIVE_THREAD_KEY)
    if (stored && stored.trim()) return stored.trim()
    const created = crypto.randomUUID()
    window.localStorage.setItem(ACTIVE_THREAD_KEY, created)
    return created
  } catch {
    return crypto.randomUUID()
  }
}

/** Save active thread UUID to localStorage. */
function saveActiveThreadId(id) {
  if (typeof window === 'undefined') return
  try {
    window.localStorage.setItem(ACTIVE_THREAD_KEY, id)
  } catch {
    // Ignore storage errors
  }
}

/** Build a default thread metadata entry. */
function makeThreadEntry(threadId, overrides = {}) {
  return {
    thread_id: threadId,
    title: 'New Claim Session',
    stage: 'onboarding',
    onboarding_complete: false,
    doc_count: 0,
    message_count: 0,
    claim_type: null,
    answers: {},
    skipped: {},
    ...overrides,
  }
}

/** Derive a concise human-readable title from thread state. */
function deriveThreadTitle(data, answers, existingTitle) {
  const claimInfo = data?.claim?.claim_info ?? {}
  const patient = answers?.patientName || claimInfo.patient_name
  const policyNum =
    claimInfo.policy_number ||
    (data?.pending?.type === 'confirm_policy' ? data.pending.policy?.policy_number : null)
  const docs = Array.isArray(data?.documents) ? data.documents.filter((d) => d.status !== 'rejected') : []
  const history = Array.isArray(data?.history) ? data.history : []
  const firstUser = history.find((m) => m.role === 'user')?.text

  if (patient && policyNum) return `${patient} · ${policyNum}`
  if (patient) return `${patient} Claim`
  if (policyNum) return `Policy ${policyNum}`
  if (docs.length > 0 && docs[0].filename) return docs[0].filename
  if (firstUser) return firstUser.slice(0, 44)
  if (existingTitle && existingTitle !== 'New Claim Session') return existingTitle
  return 'New Claim Session'
}

/** JSON POST options carrying the given thread id. */
const post = (threadId, body) => ({
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({ thread_id: threadId, ...body }),
})

/**
 * Safely parse an HTTP response body as JSON without throwing SyntaxError on plain-text errors.
 * @param {Response} res
 * @returns {Promise<{data: object | null, text: string}>}
 */
async function readBody(res) {
  const text = await res.text()
  if (!text) return { data: null, text: '' }
  try {
    return { data: JSON.parse(text), text }
  } catch {
    return { data: null, text: text.trim() }
  }
}

/** Documents worth showing: rejected uploads (not claim documents) were deleted on the server. */
const kept = (docs) => docs.filter((doc) => doc.status !== 'rejected')

/**
 * Notice for an upload the step cannot use, or null when it is fine.
 * @param {object|undefined} doc the new document record from the server
 * @param {{types: string[], label: string}|undefined} expect what the current onboarding step needs
 * @returns {object|null} toast payload
 */
function uploadNotice(doc, expect) {
  if (doc?.status === 'rejected') {
    return {
      id: Date.now(),
      title: 'Not a claim document',
      message: doc.error,
      instruction: expect ? `This step needs ${expect.label}.` : 'Upload a policy, hospital, insurer or bank document.',
    }
  }
  if (expect && doc?.status === 'parsed' && !expect.types.includes(doc.doc_type)) {
    return {
      id: Date.now(),
      title: 'Different document',
      message: `This looks like a ${docLabel(doc.doc_type).toLowerCase()}. It is saved with your documents.`,
      instruction: `This step still needs ${expect.label}.`,
    }
  }
  return null
}

/** Pick the record for this upload, ignoring historical records with the same filename. */
function uploadedDocument(records, previousIds, file) {
  return records?.findLast((doc) => (
    !previousIds.has(doc.id) && doc.filename === file.name.slice(0, 200) && doc.mime_type === file.type
  ))
}

/**
 * Build a user-friendly error toast payload with a clear title, message, and clean recovery instruction.
 * @param {number} status HTTP status code (0 for network errors)
 * @param {string} rawDetail Raw detail message from server or exception
 * @returns {{id: number, title: string, message: string, instruction: string, status: number}}
 */
function formatErrorToast(status, rawDetail) {
  const detail = (rawDetail || '').trim()
  const cleanDetail = detail.startsWith('Unexpected token') ? '' : detail

  if (status === 0) {
    return {
      id: Date.now(),
      status: 0,
      title: 'Backend Server Unreachable',
      message: 'Could not connect to the Claimwise API server on port 8000.',
      instruction: 'Verify the backend server is running ("uv run uvicorn app.main:app --reload" in backend/) and retry your action.',
    }
  }
  if (status === 415) {
    return {
      id: Date.now(),
      status,
      title: 'Unsupported Document Format',
      message: cleanDetail || 'The uploaded file is not a supported document format.',
      instruction: 'Please upload a valid PDF (.pdf), PNG (.png), or JPEG (.jpg) file.',
    }
  }
  if (status === 413) {
    return {
      id: Date.now(),
      status,
      title: 'File Size Limit Exceeded',
      message: cleanDetail || 'The uploaded document exceeds the maximum allowed file size.',
      instruction: 'Compress the PDF or upload a smaller scan (under 10 MB) and try again.',
    }
  }
  if (status === 422) {
    return {
      id: Date.now(),
      status,
      title: 'Invalid Request Format',
      message: cleanDetail || 'The server could not validate the submitted data.',
      instruction: 'Check your input fields or refresh the page to start a fresh session.',
    }
  }
  if (status === 409) {
    return {
      id: Date.now(),
      status,
      title: 'Confirmation Already Processed',
      message: cleanDetail || 'Nothing is waiting for confirmation on this thread.',
      instruction: 'Your confirmation was already recorded. Proceed with the current step on screen.',
    }
  }
  if (status === 503 || /API_KEY/i.test(cleanDetail)) {
    return {
      id: Date.now(),
      status: 503,
      title: 'AI Model Service Unavailable',
      message: cleanDetail || 'No LLM provider API key is configured on the server.',
      instruction: 'Ensure GOOGLE_API_KEY or GROQ_API_KEY is set in backend/.env, then retry.',
    }
  }
  return {
    id: Date.now(),
    status: status || 500,
    title: 'Server Request Interrupted',
    message: cleanDetail && cleanDetail !== 'Internal Server Error'
      ? cleanDetail
      : 'The server encountered a temporary error while processing your request.',
    instruction: 'Please retry your upload or message now. If you were uploading a file, select it once more.',
  }
}

/**
 * Claimwise thread state and actions. Supports creating, switching, and hydrating multiple threads
 * backed by the server checkpointer and local metadata.
 * @returns {object} state plus say, upload, answer, setClaimType, skip, thread switcher and error actions
 */
export function useClaimwise() {
  const [threadId, setThreadId] = useState(getInitialThreadId)
  const [threads, setThreads] = useState(() => {
    const stored = readStoredThreads()
    const currentId = getInitialThreadId()
    if (stored.some((t) => t.thread_id === currentId)) return stored
    return [makeThreadEntry(currentId), ...stored]
  })
  // A saved session is fetched on mount; show it as loading until then, not as an empty new claim.
  const [loadingThread, setLoadingThread] = useState(() => {
    const currentId = getInitialThreadId()
    return readStoredThreads().some((t) => t.thread_id === currentId)
  })

  const [messages, setMessages] = useState([])
  const [activity, setActivity] = useState('ready')
  const busy = activity !== 'ready' || loadingThread
  const [pending, setPending] = useState(null)
  const [onboarding, setOnboarding] = useState(null)
  const [claim, setClaim] = useState(null)
  const [documents, setDocuments] = useState([])
  const [originals, setOriginals] = useState({})
  const [actions, setActions] = useState([])
  const [notifications, setNotifications] = useState([])
  const [submission, setSubmission] = useState(null)
  const [connection, setConnection] = useState(null)
  // Wave 4: caregiver authority, audit log, household policies and the dispute route (all from the API).
  const [authority, setAuthority] = useState(null)
  const [audit, setAudit] = useState([])
  const [household, setHousehold] = useState(null)
  const [dispute, setDispute] = useState(null)
  const [reply, setReply] = useState('') // latest agent text, shown under the step that caused it
  const [answers, setAnswers] = useState(() => {
    const currentId = getInitialThreadId()
    const found = readStoredThreads().find((t) => t.thread_id === currentId)
    return found?.answers ?? {}
  })
  const [skipped, setSkipped] = useState(() => {
    const currentId = getInitialThreadId()
    const found = readStoredThreads().find((t) => t.thread_id === currentId)
    return found?.skipped ?? {}
  })
  const [error, setError] = useState(null)

  const add = (role, text) => setMessages((m) => [...m, { role, text }])
  const dismissError = () => setError(null)

  /** Update a thread summary entry in state and localStorage. */
  function syncThreadEntry(targetId, updater) {
    setThreads((prev) => {
      const idx = prev.findIndex((t) => t.thread_id === targetId)
      const base = idx >= 0 ? prev[idx] : makeThreadEntry(targetId)
      const updated = typeof updater === 'function' ? updater(base) : { ...base, ...updater }
      const next = idx >= 0
        ? [updated, ...prev.slice(0, idx), ...prev.slice(idx + 1)]
        : [updated, ...prev]
      writeStoredThreads(next)
      return next
    })
  }

  /** Apply a full ChatResponse snapshot to the active React state and thread registry. */
  function applySnapshot(targetId, data, nextMessages, nextAnswers, nextSkipped) {
    const validDocs = data.documents ? kept(data.documents) : []
    const mergedAnswers = { ...(data.answers ?? {}), ...(nextAnswers ?? {}) }
    const stage = data.claim?.stage || (data.onboarding?.complete ? 'preparing' : 'onboarding')

    setPending(data.pending ?? null)
    setOnboarding(data.onboarding ?? null)
    setClaim(data.claim ?? null)
    setDocuments(validDocs)
    if (data.actions) setActions(data.actions)
    if (data.notifications) setNotifications(data.notifications)
    if (data.submission !== undefined) setSubmission(data.submission)
    if (data.connection !== undefined) setConnection(data.connection)
    if (data.authority !== undefined) setAuthority(data.authority)
    if (data.audit) setAudit(data.audit)
    if (data.household !== undefined) setHousehold(data.household)
    if (data.dispute !== undefined) setDispute(data.dispute)

    syncThreadEntry(targetId, (prev) => {
      const finalAnswers = { ...(prev.answers ?? {}), ...mergedAnswers }
      const finalSkipped = nextSkipped ?? prev.skipped ?? {}
      const count = Array.isArray(nextMessages) ? nextMessages.length : (data.history?.length ?? prev.message_count ?? 0)
      return {
        ...prev,
        title: deriveThreadTitle(data, finalAnswers, prev.title),
        stage,
        onboarding_complete: Boolean(data.onboarding?.complete),
        doc_count: validDocs.length,
        message_count: count,
        claim_type: finalAnswers.claimType || data.claim?.claim_info?.claim_type || prev.claim_type || null,
        answers: finalAnswers,
        skipped: finalSkipped,
      }
    })
  }

  // Fetch server-side thread list from checkpointer on initial mount
  useEffect(() => {
    let active = true
    // Only this browser's own thread ids: the server never lists other people's claims.
    const ids = readStoredThreads().map((t) => t.thread_id).slice(0, 25).join(',')
    fetch(`/api/threads?ids=${encodeURIComponent(ids)}`)
      .then((res) => readBody(res))
      .then(({ data }) => {
        const list = Array.isArray(data) ? data : data?.threads
        if (!active || !Array.isArray(list)) return
        setThreads((prev) => {
          const map = new Map(prev.map((t) => [t.thread_id, t]))
          for (const srv of list) {
            const existing = map.get(srv.thread_id)
            map.set(srv.thread_id, {
              ...makeThreadEntry(srv.thread_id),
              ...existing,
              thread_id: srv.thread_id,
              title: existing?.title && existing.title !== 'New Claim Session' ? existing.title : (srv.title || 'New Claim Session'),
              stage: srv.stage || existing?.stage || 'onboarding',
              onboarding_complete: Boolean(srv.onboarding_complete),
              doc_count: srv.doc_count ?? existing?.doc_count ?? 0,
              message_count: srv.message_count ?? existing?.message_count ?? 0,
              claim_type: srv.claim_type || existing?.claim_type || null,
            })
          }
          const merged = Array.from(map.values())
          writeStoredThreads(merged)
          return merged
        })
      })
      .catch(() => {
        // Ignore offline errors during background list sync
      })
    return () => {
      active = false
    }
  }, [])

  // Hydrate the active thread from the backend checkpointer whenever threadId changes
  useEffect(() => {
    let active = true
    saveActiveThreadId(threadId)

    fetch(`/api/thread/${encodeURIComponent(threadId)}`)
      .then((res) => {
        if (!res.ok) return { data: null }
        return readBody(res)
      })
      .then(({ data }) => {
        if (!active) return
        // No saved state (or an error status): stop loading and keep the empty case.
        if (!data) {
          setLoadingThread(false)
          return
        }
        const storedEntry = readStoredThreads().find((t) => t.thread_id === threadId)
        const restoredAnswers = { ...(data.answers ?? {}), ...(storedEntry?.answers ?? {}) }
        const restoredSkipped = storedEntry?.skipped ?? {}
        const history = Array.isArray(data.history) ? data.history : []

        setMessages(history)
        setReply(data.reply || '')
        setAnswers(restoredAnswers)
        setSkipped(restoredSkipped)
        applySnapshot(threadId, data, history, restoredAnswers, restoredSkipped)
        setLoadingThread(false)
      })
      .catch(() => {
        if (active) setLoadingThread(false)
      })

    return () => {
      active = false
    }
  }, [threadId])

  /** Switch to an existing thread ID and hydrate its state from the checkpointer. */
  function selectThread(nextId) {
    if (!nextId || nextId === threadId || activity !== 'ready') return
    const storedEntry = threads.find((t) => t.thread_id === nextId)
    setError(null)
    setLoadingThread(true)
    setMessages([])
    setReply('')
    setPending(null)
    setOnboarding(null)
    setClaim(null)
    setDocuments([])
    setAnswers(storedEntry?.answers ?? {})
    setSkipped(storedEntry?.skipped ?? {})
    setThreadId(nextId)
  }

  /** Create a brand-new thread and switch to it immediately. */
  function createThread() {
    if (activity !== 'ready') return null
    const nextId = crypto.randomUUID()
    const entry = makeThreadEntry(nextId)
    setError(null)
    setLoadingThread(false)
    setMessages([])
    setReply('')
    setPending(null)
    setOnboarding(null)
    setClaim(null)
    setDocuments([])
    setActions([])
    setNotifications([])
    setSubmission(null)
    setAuthority(null)
    setAudit([])
    setHousehold(null)
    setDispute(null)
    setAnswers({})
    setSkipped({})
    setThreads((prev) => {
      const next = [entry, ...prev]
      writeStoredThreads(next)
      return next
    })
    setThreadId(nextId)
    return nextId
  }

  /** Remove a thread from the sidebar registry; switches away if it was the active thread. */
  function deleteThread(targetId) {
    if (!targetId || activity !== 'ready') return
    const remaining = threads.filter((t) => t.thread_id !== targetId)
    if (remaining.length === 0) {
      const freshId = crypto.randomUUID()
      const fresh = [makeThreadEntry(freshId)]
      writeStoredThreads(fresh)
      setThreads(fresh)
      setMessages([])
      setReply('')
      setPending(null)
      setOnboarding(null)
      setClaim(null)
      setDocuments([])
      setAnswers({})
      setSkipped({})
      setThreadId(freshId)
      return
    }
    writeStoredThreads(remaining)
    setThreads(remaining)
    if (targetId === threadId) {
      selectThread(remaining[0].thread_id)
    }
  }

  /** Apply a backend result and associate an optional upload with its new document ID. Returns the data, or null on error. */
  async function call(path, init, state, original, nextAnswers = answers) {
    setActivity(state)
    setError(null)
    try {
      const res = await fetch(path, init)
      const { data, text } = await readBody(res)
      if (!res.ok) {
        const detail = typeof data?.detail === 'string' ? data.detail : text
        setError(formatErrorToast(res.status, detail))
        setReply('')
        return null
      }
      if (!data) {
        setError(formatErrorToast(500, 'Empty or invalid JSON response from server.'))
        setReply('')
        return null
      }
      setReply(data.reply)
      if (data.reply) add('agent', data.reply)
      if (data.documents && original) {
        const existing = new Set(documents.map((doc) => doc.id))
        const uploaded = uploadedDocument(data.documents, existing, original)
        if (uploaded && uploaded.status !== 'rejected') {
          setOriginals((files) => ({ ...files, [uploaded.id]: original }))
        }
      }
      const mergedAnswers = { ...(data.answers ?? {}), ...nextAnswers }
      if (data.answers && Object.keys(data.answers).length > 0) {
        setAnswers(mergedAnswers)
      }
      applySnapshot(threadId, data, null, mergedAnswers, skipped)
      return data
    } catch (err) {
      const isNetwork = err instanceof TypeError
      setError(formatErrorToast(isNetwork ? 0 : 500, isNetwork ? '' : err.message))
      setReply('')
      return null
    } finally {
      setActivity('ready')
    }
  }

  /** Send a message with streaming token delivery. The claim type shown comes only from what the server saved. */
  async function say(text) {
    if (busy) return
    const nextAnswers = answers

    setError(null)
    add('user', text)
    setActivity('thinking')

    // Append placeholder for incoming agent tokens
    setMessages((m) => [...m, { role: 'agent', text: '' }])

    let accumulated = ''
    /** Replace the current response without remounting the active message. */
    function showReply(nextText) {
      setReply(nextText)
      setMessages((m) => [...m.slice(0, -1), { role: 'agent', text: nextText }])
    }

    /** Consume one SSE data line and use actual tool and token events for Pip. */
    function consume(line, replySoFar) {
      const trimmed = line.trim()
      if (!trimmed.startsWith('data:')) return replySoFar
      const payload = trimmed.slice(5).trim()
      if (!payload) return replySoFar
      const data = JSON.parse(payload)

      if (data.type === 'activity' && ['tool', 'thinking'].includes(data.state)) {
        setActivity(data.state)
      } else if (data.type === 'token' && data.content) {
        const nextReply = replySoFar + data.content
        setActivity('streaming')
        showReply(nextReply)
        return nextReply
      } else if (data.type === 'done') {
        const finalText = data.reply || replySoFar
        if (finalText) showReply(finalText)
        else setMessages((m) => m.slice(0, -1))
        const mergedAnswers = { ...(data.answers ?? {}), ...nextAnswers }
        if (data.answers && Object.keys(data.answers).length > 0) {
          setAnswers(mergedAnswers)
        }
        applySnapshot(threadId, data, null, mergedAnswers, skipped)
      } else if (data.type === 'error') {
        throw new Error(data.error)
      }
      return replySoFar
    }

    try {
      const res = await fetch('/api/chat/stream', post(threadId, { message: text }))
      if (!res.ok) {
        const { data, text: rawText } = await readBody(res)
        const detail = typeof data?.detail === 'string' ? data.detail : rawText
        setError(formatErrorToast(res.status, detail))
        setReply('')
        setMessages((m) => (m.length > 0 && m[m.length - 1].role === 'agent' && !m[m.length - 1].text ? m.slice(0, -1) : m))
        return
      }

      const reader = res.body.getReader()
      const decoder = new TextDecoder()
      let buffer = ''

      while (true) {
        const { done, value } = await reader.read()
        if (done) break
        buffer += decoder.decode(value, { stream: true })
        const lines = buffer.split('\n')
        buffer = lines.pop() ?? ''

        for (const line of lines) accumulated = consume(line, accumulated)
      }
      consume(buffer + decoder.decode(), accumulated)
    } catch (err) {
      const isNetwork = err instanceof TypeError
      setError(formatErrorToast(isNetwork ? 0 : 500, isNetwork ? '' : err.message))
      if (!accumulated) {
        setReply('')
        setMessages((m) => (m.length > 0 && m[m.length - 1].role === 'agent' && !m[m.length - 1].text ? m.slice(0, -1) : m))
      }
    } finally {
      setActivity('ready')
    }
  }

  /**
   * Upload one file; the agent reads it on the backend. A rejected file or a different document type
   * than the step needs shows a notice, and the step does not advance.
   * @param {File} file
   * @param {{types: string[], label: string}} [expect] what the current onboarding step needs
   */
  async function upload(file, expect) {
    if (busy) return
    add('user', `Uploaded ${file.name}`)
    const body = new FormData()
    body.append('thread_id', threadId)
    body.append('file', file)
    const before = new Set(documents.map((doc) => doc.id))
    const data = await call('/api/documents', { method: 'POST', body }, 'reading', file)
    const uploaded = uploadedDocument(data?.documents, before, file)
    const notice = uploadNotice(uploaded, expect)
    if (notice) setError(notice)
    return notice ? null : uploaded
  }

  /** Answer the paused card. A confirmed policy's members feed the patient step. */
  function answer(approved, corrections = {}) {
    if (busy || !pending) return
    const confirm = pending.type === 'confirm_policy'
    const nextAnswers = confirm && approved
      ? { ...answers, members: corrections.members ?? pending.policy.members ?? [] }
      : answers
    if (confirm && approved) setAnswers(nextAnswers)
    const yes = { confirm_policy: 'Policy details confirmed', approve_letter: 'Letter approved' }[pending.type] ?? 'Claim pack approved'
    add('user', approved ? yes : (confirm ? 'Wrong document' : 'Not yet'))
    call('/api/resume', post(threadId, { approved, corrections }), 'checking', null, nextAnswers)
  }

  /** Request the deterministic approval card for the changed claim pack. */
  function reviewPack() {
    if (busy || pending || loadingThread) return
    call('/api/action', post(threadId, { action: 'review_pack' }), 'checking')
  }

  /**
   * Press a next-step button that runs on the server (fixed action, never free text).
   * @param {{id: string, label: string}} action button from the API
   * @param {object} [data] form fields, only for "I submitted it"
   */
  function act(action, data = {}) {
    if (busy || pending || loadingThread) return
    add('user', action.label)
    call('/api/action', post(threadId, { action: action.id, data }), 'checking')
  }

  /**
   * Update the snapshot without touching the conversation (connection, read marks, background checks).
   * @returns {Promise<boolean>} whether the request succeeded
   */
  async function quiet(path, init) {
    try {
      const res = await fetch(path, init)
      const { data, text } = await readBody(res)
      if (!res.ok || !data) {
        if (init) setError(formatErrorToast(res.status, typeof data?.detail === 'string' ? data.detail : text))
        return false
      }
      applySnapshot(threadId, data, null, answers, skipped)
      return true
    } catch {
      if (init) setError(formatErrorToast(0, ''))
      return false
    }
  }

  /** Bind the insurer account connected on the connector page to this claim, by its connection code. */
  const linkConnection = (code) => quiet('/api/connection', post(threadId, { code: code.trim() }))
  /** Forget the connected account for this claim. */
  const unlinkConnection = () => quiet('/api/connection/remove', post(threadId, {}))
  /** Mark every notification read. */
  const markRead = () => quiet('/api/notifications/read', post(threadId, {}))
  /** Record the caregiver's authority (name, basis, scope, expiry, proof document id). */
  const recordAuthority = (form) => quiet('/api/authority', post(threadId, form))
  /** Record cashless or reimbursement directly on the server (no model involved), then show the refreshed claim. */
  async function setClaimType(type) {
    setAnswers({ ...answers, claimType: type })
    return quiet('/api/claim-type', post(threadId, { claim_type: type }))
  }
  /** Record that the patient withdrew consent: work pauses and approvals are cancelled. */
  const withdrawAuthority = () => quiet('/api/authority/withdraw', post(threadId, {}))

  // Check on open happens on hydrate; while a claim waits on the insurer, check again every 30 seconds.
  const watching = ['submitted', 'unconfirmed'].includes(submission?.status) && connection?.status === 'active'
  useEffect(() => {
    if (!watching || pending) return undefined
    const timer = setInterval(() => {
      if (document.visibilityState === 'visible') quiet(`/api/thread/${encodeURIComponent(threadId)}`)
    }, 30000)
    return () => clearInterval(timer)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [watching, pending, threadId])

  /** Skip an optional step and persist the skip flag on the current thread entry. */
  function skipStep(id) {
    setSkipped((prev) => {
      const next = { ...prev, [id]: true }
      syncThreadEntry(threadId, { skipped: next })
      return next
    })
  }

  return {
    threadId, threads, loadingThread,
    selectThread, createThread, deleteThread,
    messages, busy, activity, pending, onboarding, claim, documents, originals,
    actions, notifications, submission, connection, authority, audit, household, dispute,
    reply, answers, skipped,
    error, dismissError,
    say, upload, answer, reviewPack, act, linkConnection, unlinkConnection, markRead, recordAuthority, withdrawAuthority,
    setClaimType,
    skip: skipStep,
  }
}
