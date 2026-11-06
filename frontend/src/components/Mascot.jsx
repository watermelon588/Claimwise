// Pip, the Claimwise mascot. Each pose uses one cutout from the shared sprite sheet.
import './mascot.css'

const PIP_STATUS = {
  ready: 'Ready to help',
  welcome: 'Ready to help',
  thinking: 'Thinking through your claim',
  tool: 'Running a claim tool',
  streaming: 'Writing your reply',
  reading: 'Reading your document',
  checking: 'Checking your confirmation',
  waiting: 'Waiting for your review',
}

/** Decorative pose and motion layers. Put the activity label beside the mascot. */
export default function Mascot({ state = 'ready', size = 'avatar', motion = 'full' }) {
  return (
    <span aria-hidden="true" className={`pip pip--${size}`} data-pip={state} data-pip-motion={motion}>
      <span className="pip__pose" />
      <span className="pip__cue"><i /><i /><i /></span>
    </span>
  )
}

/** Consistent activity copy for the sidebar and current reply. */
export function PipActivityLabel({ state }) {
  return PIP_STATUS[state]
}

/** Text plus mascot for the live surface closest to the user's current action. */
export function MascotStatus({ state }) {
  return (
    <div className="flex items-center gap-3 text-sm text-muted" role="status">
      <Mascot state={state} />
      <span>{PIP_STATUS[state]}</span>
    </div>
  )
}
