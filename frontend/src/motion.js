// Motion layer: Lenis smooth scroll driven by the GSAP ticker, scroll reveals, entrances and progress fills.
// Everything is skipped when the user prefers reduced motion, and every effect reverts on cleanup.
import gsap from 'gsap'
import { ScrollTrigger } from 'gsap/ScrollTrigger'
import Lenis from 'lenis'
import { useEffect, useLayoutEffect, useRef } from 'react'

gsap.registerPlugin(ScrollTrigger)

const EASE = 'power3.out'
let lenis = null // the one smooth-scroll instance, so other modules can scroll or pause it

/** True when the user asked the OS for less motion. */
const reduced = () => window.matchMedia('(prefers-reduced-motion: reduce)').matches

/** Start Lenis on the window and keep ScrollTrigger in sync with it. Call once at the app root. */
export function useSmoothScroll() {
  useEffect(() => {
    if (reduced()) return undefined
    const instance = new Lenis({ lerp: 0.11, wheelMultiplier: 0.9 })
    lenis = instance
    instance.on('scroll', ScrollTrigger.update)
    // One clock for scroll and animation avoids jitter between them.
    const tick = (time) => instance.raf(time * 1000)
    gsap.ticker.add(tick)
    gsap.ticker.lagSmoothing(0)
    return () => {
      gsap.ticker.remove(tick)
      gsap.ticker.lagSmoothing(500, 33)
      instance.destroy()
      lenis = null
    }
  }, [])
}

/** Smoothly scroll the page to its end (newest message). */
export function scrollToBottom() {
  const y = document.documentElement.scrollHeight
  if (lenis) lenis.scrollTo(y, { duration: 0.9 })
  else window.scrollTo({ top: y, behavior: reduced() ? 'auto' : 'smooth' })
}

/** Jump to the top without animation (used when switching layout). */
export function scrollToTop() {
  if (lenis) lenis.scrollTo(0, { immediate: true })
  else window.scrollTo(0, 0)
}

/** Pause page scrolling while a modal is open. */
export function lockScroll(locked) {
  if (!lenis) return
  if (locked) lenis.stop()
  else lenis.start()
}

/**
 * Fade and lift [data-reveal] elements inside scope as they scroll into view.
 * New elements are picked up whenever dep changes; already revealed ones are left alone.
 * @param {{current: HTMLElement|null}} scope
 * @param {unknown} dep value that changes when new content appears
 */
export function useReveal(scope, dep) {
  useLayoutEffect(() => {
    const root = scope.current
    if (!root) return undefined
    const fresh = [...root.querySelectorAll('[data-reveal]:not([data-shown])')]
    fresh.forEach((el) => el.setAttribute('data-shown', ''))
    if (!fresh.length || reduced()) return undefined

    const entered = new Set()
    const ctx = gsap.context(() => {
      gsap.set(fresh, { autoAlpha: 0, y: 18 })
      ScrollTrigger.batch(fresh, {
        start: 'top 96%',
        once: true,
        onEnter: (batch) => {
          batch.forEach((el) => entered.add(el))
          gsap.to(batch, { autoAlpha: 1, y: 0, duration: 0.8, ease: EASE, stagger: 0.07, overwrite: true })
        },
      })
      ScrollTrigger.refresh()
    }, root)
    return () => {
      ctx.revert() // anything not yet revealed becomes visible, never stuck hidden
      fresh.forEach((el) => !entered.has(el) && el.removeAttribute('data-shown'))
    }
  }, [scope, dep])
}

/**
 * Stagger [data-enter] elements in on mount and whenever key changes (a new step or view).
 * @param {{current: HTMLElement|null}} scope
 * @param {unknown} key
 */
export function useEnter(scope, key) {
  useLayoutEffect(() => {
    if (!scope.current || reduced()) return undefined
    const ctx = gsap.context(() => {
      gsap.from('[data-enter]', {
        autoAlpha: 0, y: 20, duration: 0.75, ease: EASE, stagger: 0.07,
        clearProps: 'opacity,visibility,transform',
      })
    }, scope)
    return () => ctx.revert()
  }, [scope, key])
}

/**
 * Animate an element's horizontal scale to value (0..1); grows from zero on first render.
 * @param {{current: HTMLElement|null}} ref
 * @param {number} value
 */
export function useFill(ref, value) {
  const first = useRef(true)
  useLayoutEffect(() => {
    const el = ref.current
    if (!el) return
    if (reduced()) {
      gsap.set(el, { scaleX: value })
    } else if (first.current) {
      gsap.fromTo(el, { scaleX: 0 }, { scaleX: value, duration: 1.2, ease: EASE, delay: 0.15 })
    } else {
      gsap.to(el, { scaleX: value, duration: 0.9, ease: 'power3.inOut', overwrite: true })
    }
    first.current = false
  }, [ref, value])
}

export { gsap }
