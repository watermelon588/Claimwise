// Claim journey bar and individual step indicators.
import { useLayoutEffect, useRef } from 'react'
import { Check } from 'lucide-react'
import { gsap, useFill } from '../motion.js'
import { shortFor, stepIcon } from './icons.js'
import { ICON } from './tokens.js'

const SR = { done: 'done', skipped: 'skipped', now: 'current', todo: 'to do', later: 'later' }

/** Display the current journey step and weighted completion as one accessible bar. */
export function JourneyProgress({ value, step }) {
  return (
    <div>
      <div className="mb-2 flex items-baseline justify-between gap-3">
        <p className="min-w-0 text-sm font-semibold">{step}</p>
        <span className="shrink-0 font-mono text-xs font-semibold text-coral-ink">{value}%</span>
      </div>
      <div
        role="progressbar"
        aria-label="Claim journey"
        aria-valuemin={0}
        aria-valuemax={100}
        aria-valuenow={value}
        aria-valuetext={`${value}% complete. ${step}`}
        className="h-1.5 overflow-hidden rounded-full bg-line"
      >
        <div
          aria-hidden="true"
          className="h-full origin-left rounded-full bg-coral motion-safe:transition-transform motion-safe:duration-500 motion-safe:ease-out"
          style={{ transform: `scaleX(${value / 100})` }}
        />
      </div>
    </div>
  )
}

/** Position of the progress head: the current item, else the last finished one. */
function headIndex(items) {
  const now = items.findIndex((i) => i.status === 'now')
  if (now !== -1) return now
  return items.reduce((last, it, i) => (it.status === 'done' ? i : last), 0)
}

/** One round node of the stepper. */
function Node({ item }) {
  const tone = {
    done: 'border-ink bg-ink text-milk',
    now: 'border-coral bg-paper text-coral-ink ring-4 ring-coral/15',
    todo: 'border-line bg-paper text-muted',
    skipped: 'border-dashed border-line bg-milk text-muted/60',
    later: 'border-dashed border-line bg-milk text-muted/50',
  }[item.status]
  return (
    <span className={`relative z-10 grid size-8 place-items-center sm:size-9 rounded-full border transition-[background-color,border-color,color,box-shadow] duration-500 ${tone}`}>
      {item.status === 'done' ? <Check {...ICON} size={15} /> : stepIcon(item.id, { ...ICON, size: 15 })}
    </span>
  )
}

/**
 * Icon stepper with a connecting line that fills to the current item.
 * @param {{items: Array<{id: string, title: string, status: string}>, label: string}} props
 * @returns {JSX.Element}
 */
export function Stepper({ items, label }) {
  const fill = useRef(null)
  const head = headIndex(items)
  useFill(fill, items.length > 1 ? head / (items.length - 1) : 1)
  const inset = `${50 / items.length}%` // the line runs between the first and last node centres

  return (
    <nav aria-label={label}>
      <div className="relative">
        <div className="absolute top-4 h-px bg-line sm:top-[18px]" style={{ left: inset, right: inset }} aria-hidden>
          <div ref={fill} className="h-full w-full origin-left bg-coral" />
        </div>
        <ol className="relative grid" style={{ gridTemplateColumns: `repeat(${items.length}, minmax(0, 1fr))` }}>
          {items.map((it) => (
            <li key={it.id} aria-current={it.status === 'now' ? 'step' : undefined} className="flex flex-col items-center gap-2.5">
              <Node item={it} />
              <span className={`hidden truncate px-1 text-xs transition-colors sm:block ${it.status === 'now' ? 'font-semibold text-ink' : it.status === 'done' ? 'text-ink/80' : 'text-muted'}`}>
                {shortFor(it)}
              </span>
              <span className="sr-only">{it.title}, {SR[it.status]}</span>
            </li>
          ))}
        </ol>
      </div>
    </nav>
  )
}

/**
 * Segmented bar: done segments in ink, the current one fills in coral, the rest stay empty.
 * @param {{items: Array<{id: string, title: string, status: string}>, label: string}} props
 * @returns {JSX.Element}
 */
export function Segments({ items, label }) {
  const root = useRef(null)
  const statuses = items.map((i) => i.status).join()

  // Fill finished and current segments left to right whenever the statuses change.
  useLayoutEffect(() => {
    const fills = root.current.querySelectorAll('[data-fill]')
    const list = statuses.split(',')
    const target = (i) => (['done', 'now'].includes(list[i]) ? 1 : 0)
    if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) {
      gsap.set(fills, { scaleX: target })
      return undefined
    }
    const tween = gsap.to(fills, { scaleX: target, duration: 0.7, ease: 'power3.out', stagger: 0.05 })
    return () => tween.kill()
  }, [statuses]) // statuses is the only input that changes the fills

  return (
    <nav aria-label={label}>
      <ol ref={root} className="flex gap-1.5">
        {items.map((it) => (
          <li key={it.id} aria-current={it.status === 'now' ? 'step' : undefined} className="min-w-0 flex-1">
            <span className={`block h-1 overflow-hidden rounded-full ${it.status === 'later' ? 'bg-line/50' : 'bg-line'}`} aria-hidden>
              {/* Starts empty; GSAP owns the transform after mount. */}
              <span data-fill className={`block h-full origin-left ${it.status === 'now' ? 'bg-coral' : 'bg-ink'}`} style={{ transform: 'scaleX(0)' }} />
            </span>
            <span className={`mt-2 hidden truncate text-[11px] sm:block ${it.status === 'now' ? 'font-semibold text-ink' : 'text-muted'}`}>
              {shortFor(it)}
            </span>
            <span className="sr-only">{it.title}, {SR[it.status]}</span>
          </li>
        ))}
      </ol>
    </nav>
  )
}
