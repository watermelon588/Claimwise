// Local mock transport and the most recent test response.
import { useEffect, useRef, useState } from 'react'

const BASES = import.meta.env.DEV ? ['/mock-api', 'http://localhost:8100'] : ['/mock-api']

/** Read the test response as JSON when possible, otherwise preserve its text. */
async function readBody(response) {
  const text = await response.text()
  try {
    return JSON.parse(text)
  } catch {
    return text || null
  }
}

/** Find the mock server with a read-only request before sending any test mutations. */
async function findServer(signal) {
  for (const base of BASES) {
    try {
      const response = await fetch(`${base}/admin/overview`, { signal })
      if (response.ok) {
        const overview = await readBody(response)
        if (overview?.mock === true) return { base, overview }
      }
    } catch {
      if (signal?.aborted) return null
    }
  }
  return { base: null, overview: null }
}

/** Connect to the mock service, submit one test at a time, and refresh the dashboard. */
export function useMockConsole() {
  const [connection, setConnection] = useState(null)
  const [busy, setBusy] = useState(false)
  const [result, setResult] = useState(null)
  const submissionKeys = useRef(new Map())

  useEffect(() => {
    const controller = new AbortController()
    findServer(controller.signal).then((server) => {
      if (server && !controller.signal.aborted) setConnection(server)
    })
    return () => controller.abort()
  }, [])

  /** Retry a failed connection without sending the previous request again. */
  async function reconnect() {
    setConnection(null)
    setConnection(await findServer())
  }

  /** Send the selected operation exactly once, using stable keys for identical claim submissions. */
  async function execute({ title, method, path, headers = {}, body }) {
    if (!connection?.base || busy) return null
    const { base } = connection
    const requestHeaders = { ...headers }
    if (body !== undefined) requestHeaders['Content-Type'] = 'application/json'
    if ('Idempotency-Key' in requestHeaders) {
      const signature = `${path}:${body ?? ''}`
      if (!submissionKeys.current.has(signature)) {
        const key = Array.from(crypto.getRandomValues(new Uint32Array(4)), (part) => part.toString(16).padStart(8, '0')).join('')
        submissionKeys.current.set(signature, key)
      }
      requestHeaders['Idempotency-Key'] = submissionKeys.current.get(signature)
    }
    setBusy(true)
    setResult(null)
    try {
      const response = await fetch(`${base}${path}`, { method, headers: requestHeaders, body })
      const data = await readBody(response)
      const execution = { title, status: response.status, ok: response.ok, data }
      setResult(execution)
      if (response.ok && (path === '/admin/reset' || path.startsWith('/admin/scenarios/'))) {
        submissionKeys.current.clear()
      }
      // A simulated error can still leave a state change behind.
      if (method !== 'GET') {
        try {
          const refresh = await fetch(`${base}/admin/overview`)
          if (refresh.ok) {
            const overview = await readBody(refresh)
            if (overview?.mock === true) setConnection({ base, overview })
          }
        } catch {
          // Preserve the actual response even if the summary refresh fails.
        }
      }
      return execution
    } catch {
      setConnection((current) => ({ ...current, base: null }))
      setResult({ title, ok: false, status: null, data: 'The connection dropped before a response arrived. Check the test state before trying again.' })
      return null
    } finally {
      setBusy(false)
    }
  }

  return { connection, busy, result, reconnect, execute, clearResult: () => setResult(null) }
}
