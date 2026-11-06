// Claimwise public landing, prototype information pages and demo viewer.
import { useEffect, useRef } from 'react'
import { ArrowLeft, ArrowRight, ArrowUpRight, Play, X } from 'lucide-react'
import { gsap } from '../motion.js'
import { ICON } from './tokens.js'
import { Brand } from './ui.jsx'
import './landing.css'

const DEMO_URL = import.meta.env.VITE_CLAIMWISE_DEMO_URL?.trim()
const PIP_INBETWEENS = '/pip-hero-inbetweens.webp'
const PIP_FRAMES = [
  ['original', '0% 50%'],
  ['inbetween', '0% 0%'],
  ['inbetween', '100% 0%'],
  ['original', '50% 50%'],
  ['inbetween', '0% 100%'],
  ['inbetween', '100% 100%'],
  ['original', '100% 50%'],
]
const PIP_CENTER = 3

const PUBLIC_PAGES = {
  policy: {
    title: 'Use policy',
    intro: 'Claimwise is a prototype for exploring the health insurance claim workflow.',
    sections: [
      ['Use sample documents', 'Use synthetic or redacted files for walkthroughs. Keep real medical records, policy details and bank information out of the demo and Mock Console.'],
      ['Review before you act', 'Check extracted details and draft documents against your originals. Use your insurer’s official channels for real claim submissions and decisions.'],
    ],
  },
  privacy: {
    title: 'Privacy',
    intro: 'How the Claimwise prototype handles the information you enter.',
    sections: [
      ['What the workspace uses', 'The workspace sends uploaded files and messages to the Claimwise backend to extract details and prepare responses. Depending on the deployment, a configured AI provider can process content from a claim.'],
      ['What the browser remembers', 'The browser stores claim session identifiers and summaries so the workspace can reopen a session. Claim documents and session data can also be stored by the backend. Clearing local browser data only clears the browser’s copy.'],
      ['Keep test data separate', 'Use synthetic or redacted information in this prototype.'],
    ],
  },
  terms: {
    title: 'Terms of use',
    intro: 'These terms describe the intended use of the Claimwise prototype.',
    sections: [
      ['Use of the assistant', 'Claimwise helps you organize evidence and understand the steps in a claim. You are responsible for reviewing its output and deciding whether to use it.'],
      ['Decisions and payments', 'Your insurer or administrator decides coverage and payment. Check your policy and official correspondence before acting on claim information.'],
      ['Mock testing', 'The Mock Console simulates provider actions for testing. Use it with synthetic cases and documents.'],
    ],
  },
}

/** Display the actual demo when configured and a clear preview state before it is available. */
function DemoDialog({ dialogRef }) {
  return (
    <dialog
      ref={dialogRef}
      className="landing-demo"
      aria-labelledby="landing-demo-title"
      onClose={(event) => event.currentTarget.querySelector('video')?.pause()}
    >
      <div className="landing-demo-header">
        <h2 id="landing-demo-title">Claimwise demo</h2>
        <form method="dialog">
          <button type="submit" className="landing-demo-close" aria-label="Close demo">
            <X {...ICON} size={20} />
          </button>
        </form>
      </div>
      {DEMO_URL ? (
        <video className="landing-video" controls playsInline preload="none" src={DEMO_URL} aria-label="Claimwise walkthrough" />
      ) : (
        <div className="landing-demo-preview">
          <Play {...ICON} size={30} aria-hidden="true" />
          <p>Demo video coming soon</p>
          <span>The walkthrough will cover policy upload, claim review and payment checks.</span>
        </div>
      )}
    </dialog>
  )
}

/** Ease through Pip's seven poses as the pointer crosses the stage. */
function PipStage() {
  const stageRef = useRef(null)

  useEffect(() => {
    const stage = stageRef.current
    const frames = stage.querySelectorAll('.landing-pip-frame')
    const media = gsap.matchMedia()

    media.add('(hover: hover) and (pointer: fine) and (prefers-reduced-motion: no-preference)', () => {
      // Keep the neutral frame until the additional poses are decoded.
      const atlas = new Image()
      atlas.src = PIP_INBETWEENS
      let ready = false
      atlas.decode().then(() => { ready = true }).catch(() => {})
      const motion = { frame: PIP_CENTER }
      let targetFrame = PIP_CENTER
      const turn = gsap.quickTo(motion, 'frame', {
        duration: 0.28,
        ease: 'power3.out',
        onUpdate() {
          // Briefly blend adjacent poses in motion, then hold a single sharp frame.
          frames.forEach((frame, index) => {
            const distance = Math.abs(motion.frame - index)
            frame.style.opacity = gsap.utils.clamp(0, 1, (0.7 - distance) / 0.4)
          })
        },
      })

      /** Map the pointer to a target pose and let the tween fill the steps between. */
      function followPointer(event) {
        if (!ready || event.pointerType === 'touch') return
        const { left, width } = stage.getBoundingClientRect()
        const position = gsap.utils.clamp(0, 1, ((event.clientX - left) / width - 0.08) / 0.84)
        const nextFrame = Math.round(position * (PIP_FRAMES.length - 1))
        if (nextFrame === targetFrame) return
        targetFrame = nextFrame
        turn(targetFrame)
      }

      /** Return Pip to the front-facing pose when the pointer leaves. */
      function resetPose() {
        targetFrame = PIP_CENTER
        turn(targetFrame)
      }

      stage.addEventListener('pointermove', followPointer, { passive: true })
      stage.addEventListener('pointerleave', resetPose)
      return () => {
        stage.removeEventListener('pointermove', followPointer)
        stage.removeEventListener('pointerleave', resetPose)
        frames.forEach((frame) => frame.style.removeProperty('opacity'))
      }
    })

    return () => media.revert()
  }, [])

  return (
    <figure className="landing-stage" ref={stageRef}>
      <div className="landing-pip-shadow" aria-hidden="true" />
      <div className="landing-pip" role="img" aria-label="Pip, a coral robot with a smiling face">
        {PIP_FRAMES.map(([atlas, position], index) => (
          <span
            key={atlas + position}
            className={`landing-pip-frame landing-pip-frame--${atlas}`}
            data-neutral={index === PIP_CENTER || undefined}
            style={{ backgroundPosition: position }}
          />
        ))}
      </div>
      <figcaption className="landing-stage-caption">
        <span>Pip</span>
        <span>Your claim guide</span>
      </figcaption>
    </figure>
  )
}

/** Render the public shell and its home or informational content. */
export default function LandingPage({ onEnter, onOpenMocks, page }) {
  const demo = useRef(null)
  const info = PUBLIC_PAGES[page]

  return (
    <div className="landing">
      <a className="landing-skip" href="#landing-main">Skip to content</a>
      <header className="landing-header landing-container">
        <a className="landing-brand" href="/" aria-label="Claimwise home"><Brand /></a>
        <nav className="landing-nav" aria-label="Main navigation">
          <a className="landing-nav-link" href={info ? '/#about' : '#about'}>About</a>
          <button type="button" className="landing-action landing-action--nav" onClick={onOpenMocks}>
            Mock Console <ArrowUpRight {...ICON} size={15} aria-hidden="true" />
          </button>
        </nav>
      </header>

      {info ? (
        <main className="landing-info landing-container" id="landing-main">
          <a className="landing-back" href="/"><ArrowLeft {...ICON} size={16} /> Back to home</a>
          <h1>{info.title}</h1>
          <p className="landing-info-intro">{info.intro}</p>
          {info.sections.map(([title, body]) => (
            <section key={title}>
              <h2>{title}</h2>
              <p>{body}</p>
            </section>
          ))}
        </main>
      ) : (
        <main id="landing-main">
          <section className="landing-hero landing-container" aria-labelledby="landing-title">
            <div className="landing-hero-copy">
              <p className="landing-kicker">For patients and caregivers</p>
              <h1 id="landing-title">Health claims,<br />made clearer.</h1>
              <p className="landing-intro">
                Bring your policy, hospital bills and claim updates into one place. Pip helps you see what’s missing and what to do next.
              </p>
              <div className="landing-actions">
                <button type="button" className="landing-action landing-action--primary" onClick={onEnter}>
                  Open Claim Assistant <ArrowRight {...ICON} size={18} aria-hidden="true" />
                </button>
                <button type="button" className="landing-action landing-action--secondary" aria-haspopup="dialog" onClick={() => demo.current.showModal()}>
                  <Play {...ICON} size={16} aria-hidden="true" /> Watch demo
                </button>
              </div>
            </div>
            <PipStage />
          </section>

          <section className="landing-about landing-container" id="about" aria-labelledby="landing-about-title">
            <p className="landing-kicker">About Claimwise</p>
            <div>
              <h2 id="landing-about-title">Know where your claim stands.</h2>
              <p>Review the details from your documents, prepare what your insurer asks for, and compare the payment you receive with the settlement. You review each step before taking action.</p>
            </div>
          </section>

          <DemoDialog dialogRef={demo} />
        </main>
      )}

      <footer className="landing-footer landing-container">
        <p>Claimwise : Rohit</p>
        <nav aria-label="Policies">
          {Object.entries(PUBLIC_PAGES).map(([slug, { title }]) => (
            <a key={slug} href={`/${slug}`} aria-current={slug === page ? 'page' : undefined}>{title}</a>
          ))}
        </nav>
      </footer>
    </div>
  )
}
