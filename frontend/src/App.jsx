// Minimal chat page for talking to the Claimwise agent. Placeholder until the real UI is designed.
import { useState } from 'react'

// One thread per browser tab; the backend checkpointer keeps its history.
const THREAD_ID = crypto.randomUUID()

/**
 * Chat screen: sends messages to POST /api/chat and lists the conversation.
 * @returns {JSX.Element}
 */
export default function App() {
  const [messages, setMessages] = useState([])
  const [input, setInput] = useState('')
  const [busy, setBusy] = useState(false)

  /** Send the typed message and append the agent's reply (or the error). */
  async function send(e) {
    e.preventDefault()
    const text = input.trim()
    if (!text || busy) return
    setMessages((m) => [...m, { role: 'user', text }])
    setInput('')
    setBusy(true)
    try {
      const res = await fetch('/api/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ thread_id: THREAD_ID, message: text }),
      })
      const data = await res.json()
      const reply = res.ok ? data.reply : `Error: ${data.detail ?? res.status}`
      setMessages((m) => [...m, { role: 'agent', text: reply }])
    } catch {
      setMessages((m) => [...m, { role: 'agent', text: 'Error: backend not reachable' }])
    } finally {
      setBusy(false)
    }
  }

  return (
    <main className="mx-auto flex h-screen max-w-2xl flex-col bg-white p-4 text-gray-900">
      <h1 className="mb-4 text-xl font-semibold">Claimwise</h1>
      <ul className="flex-1 space-y-3 overflow-y-auto">
        {messages.map((m, i) => (
          <li
            key={i}
            className={`whitespace-pre-wrap rounded-lg px-3 py-2 ${
              m.role === 'user' ? 'ml-auto max-w-[80%] bg-gray-900 text-white' : 'max-w-[80%] bg-gray-100'
            }`}
          >
            {m.text}
          </li>
        ))}
        {busy && <li className="text-sm text-gray-500">Thinking...</li>}
      </ul>
      <form onSubmit={send} className="mt-4 flex gap-2">
        <input
          className="flex-1 rounded-lg border border-gray-300 px-3 py-2 focus:outline-none focus:ring-2 focus:ring-gray-900"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder="Describe your claim situation..."
          aria-label="Message"
        />
        <button
          type="submit"
          disabled={busy}
          className="rounded-lg bg-gray-900 px-4 py-2 text-white disabled:opacity-50"
        >
          Send
        </button>
      </form>
    </main>
  )
}
