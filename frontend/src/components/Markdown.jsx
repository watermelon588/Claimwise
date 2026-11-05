// Lightweight markdown renderer: parses bold, italic, code, lists, dividers and headings.
// Zero dependencies, fast, safe, and handles partial tokens during stream delivery.

/**
 * Render inline tokens (code, bold, italic, links, plain text).
 * @param {string} text
 * @returns {Array<JSX.Element>}
 */
function renderInline(text) {
  if (!text) return []
  // Matches:
  // 1. inline code: `...`
  // 2. bold: **...** (or unclosed **... during streaming)
  // 3. italic: *...* (not **; or unclosed *... during streaming)
  // 4. link: [text](url)
  const regex = /(`[^`]+`|\*\*(.+?)(?:\*\*|$)|(?<!\*)\*([^*]+?)(?:\*(?!\*)|$)|\[([^\]]+)\]\((https?:\/\/[^\s)]+)\))/g
  const parts = []
  let lastIndex = 0
  let match
  let key = 0

  while ((match = regex.exec(text)) !== null) {
    if (match.index > lastIndex) {
      parts.push(<span key={key++}>{text.slice(lastIndex, match.index)}</span>)
    }
    const [full, , bold, italic, linkText, linkUrl] = match
    if (full.startsWith('`') && full.endsWith('`') && full.length >= 2) {
      parts.push(
        <code key={key++} className="rounded bg-ink/5 px-1 py-0.5 font-mono text-[13px]">
          {full.slice(1, -1)}
        </code>,
      )
    } else if (full.startsWith('**')) {
      parts.push(
        <strong key={key++} className="font-semibold text-ink">
          {bold}
        </strong>,
      )
    } else if (full.startsWith('*')) {
      parts.push(
        <em key={key++} className="italic">
          {italic}
        </em>,
      )
    } else if (linkText && linkUrl) {
      parts.push(
        <a key={key++} href={linkUrl} target="_blank" rel="noreferrer" className="underline hover:opacity-80">
          {linkText}
        </a>,
      )
    }
    lastIndex = regex.lastIndex
  }

  if (lastIndex < text.length) {
    parts.push(<span key={key++}>{text.slice(lastIndex)}</span>)
  }

  return parts
}

/**
 * Render lines inside a block, preserving intra-paragraph line breaks.
 * @param {string} text
 * @returns {Array<JSX.Element>}
 */
function renderLines(text) {
  const lines = text.split('\n')
  return lines.map((line, i) => (
    <span key={i}>
      {i > 0 && <br />}
      {renderInline(line)}
    </span>
  ))
}

/**
 * Group raw block tokens (merges adjacent list items into list groups).
 * @param {Array<object>} rawBlocks
 * @returns {Array<object>}
 */
function groupBlocks(rawBlocks) {
  const grouped = []
  let currentList = null

  for (const block of rawBlocks) {
    if (block.type === 'ol-item') {
      if (!currentList || currentList.type !== 'ol') {
        currentList = { type: 'ol', items: [] }
        grouped.push(currentList)
      }
      currentList.items.push(block.text)
    } else if (block.type === 'ul-item') {
      if (!currentList || currentList.type !== 'ul') {
        currentList = { type: 'ul', items: [] }
        grouped.push(currentList)
      }
      currentList.items.push(block.text)
    } else {
      currentList = null
      grouped.push(block)
    }
  }

  return grouped
}

/**
 * Parse markdown text into structured blocks.
 * @param {string} markdown
 * @returns {Array<object>}
 */
function parseBlocks(markdown) {
  if (!markdown) return []
  const lines = markdown.split(/\r?\n/)
  const rawBlocks = []
  let currentParagraph = []
  let inCodeBlock = false
  let codeLines = []

  function flushParagraph() {
    if (currentParagraph.length > 0) {
      rawBlocks.push({ type: 'p', text: currentParagraph.join('\n') })
      currentParagraph = []
    }
  }

  for (let i = 0; i < lines.length; i++) {
    const line = lines[i]
    const trimmed = line.trim()

    // Fenced code block toggle
    if (trimmed.startsWith('```')) {
      if (inCodeBlock) {
        rawBlocks.push({ type: 'codeblock', code: codeLines.join('\n') })
        codeLines = []
        inCodeBlock = false
      } else {
        flushParagraph()
        inCodeBlock = true
      }
      continue
    }

    if (inCodeBlock) {
      codeLines.push(line)
      continue
    }

    // Horizontal rule: ***, ---, ___
    if (/^(\*{3,}|-{3,}|_{3,})$/.test(trimmed)) {
      flushParagraph()
      rawBlocks.push({ type: 'hr' })
      continue
    }

    // Heading: #, ##, ###
    const headingMatch = line.match(/^(#{1,6})\s+(.+)$/)
    if (headingMatch) {
      flushParagraph()
      rawBlocks.push({ type: 'h', level: headingMatch[1].length, text: headingMatch[2] })
      continue
    }

    // Ordered list item: 1. ...
    const olMatch = line.match(/^(\d+)\.\s+(.+)$/)
    if (olMatch) {
      flushParagraph()
      rawBlocks.push({ type: 'ol-item', num: olMatch[1], text: olMatch[2] })
      continue
    }

    // Unordered list item: - ..., * ...
    const ulMatch = line.match(/^[-*]\s+(.+)$/)
    if (ulMatch) {
      flushParagraph()
      rawBlocks.push({ type: 'ul-item', text: ulMatch[1] })
      continue
    }

    // Blank line terminates current paragraph
    if (trimmed === '') {
      flushParagraph()
      continue
    }

    currentParagraph.push(line)
  }

  if (inCodeBlock && codeLines.length > 0) {
    rawBlocks.push({ type: 'codeblock', code: codeLines.join('\n') })
  }
  flushParagraph()

  return groupBlocks(rawBlocks)
}

/**
 * Markdown component.
 * @param {{ text: string, className?: string }} props
 * @returns {JSX.Element|null}
 */
export default function Markdown({ text, className = '' }) {
  if (!text) return null
  const blocks = parseBlocks(text)

  return (
    <div className={`space-y-2.5 ${className}`}>
      {blocks.map((block, i) => {
        if (block.type === 'hr') {
          return <hr key={i} className="my-3 border-t border-line" />
        }
        if (block.type === 'h') {
          if (block.level === 1) {
            return (
              <h1 key={i} className="text-base font-bold text-ink">
                {renderInline(block.text)}
              </h1>
            )
          }
          if (block.level === 2) {
            return (
              <h2 key={i} className="text-sm font-semibold text-ink">
                {renderInline(block.text)}
              </h2>
            )
          }
          return (
            <h3 key={i} className="text-sm font-medium text-ink">
              {renderInline(block.text)}
            </h3>
          )
        }
        if (block.type === 'ol') {
          return (
            <ol key={i} className="my-2 list-decimal space-y-1 pl-5">
              {block.items.map((item, j) => (
                <li key={j} className="leading-relaxed">
                  {renderLines(item)}
                </li>
              ))}
            </ol>
          )
        }
        if (block.type === 'ul') {
          return (
            <ul key={i} className="my-2 list-disc space-y-1 pl-5">
              {block.items.map((item, j) => (
                <li key={j} className="leading-relaxed">
                  {renderLines(item)}
                </li>
              ))}
            </ul>
          )
        }
        if (block.type === 'codeblock') {
          return (
            <pre key={i} className="my-2 overflow-x-auto rounded bg-ink/5 p-3 font-mono text-xs">
              <code>{block.code}</code>
            </pre>
          )
        }
        // Paragraph
        return (
          <p key={i} className="leading-relaxed">
            {renderLines(block.text)}
          </p>
        )
      })}
    </div>
  )
}
