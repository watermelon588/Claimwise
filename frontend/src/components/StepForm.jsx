// Body of the current onboarding step: upload, policy check, patient, authority, claim type or a hospital document.
// The parent remounts it per step (key=step.id), so local state resets when the step advances.
import { useState } from 'react'
import { ArrowRight, Check, FileCheck, Landmark, ScrollText, ShieldCheck, Stethoscope, UserRound, Users, Wallet } from 'lucide-react'
import ConfirmPolicy from './ConfirmPolicy.jsx'
import Markdown from './Markdown.jsx'
import { MascotStatus } from './Mascot.jsx'
import { AgentMark, Button, DropZone, Quiet } from './ui.jsx'
import { FIELD, ICON } from './tokens.js'

// What each upload step accepts; anything else shows a notice and the step stays.
const EXPECT = {
  policy: { types: ['policy_schedule', 'e_card', 'policy_wording'], label: 'your policy schedule or e-card' },
  discharge_summary: { types: ['discharge_summary'], label: 'the discharge summary' },
  hospital_bill: { types: ['hospital_bill'], label: 'the final hospital bill' },
}

const DROP_LABEL = {
  policy: 'Drop your policy schedule or e-card',
  discharge_summary: 'Drop the discharge summary',
  hospital_bill: 'Drop the final hospital bill',
}

/** Selectable card backed by a radio input, with an optional icon and a check when chosen. */
function Choice({ name, checked, onChange, title, note, Icon }) {
  return (
    <label className={`group relative flex cursor-pointer items-center gap-3.5 rounded-xl border bg-paper p-4 transition-[border-color,box-shadow] duration-200 has-[:focus-visible]:outline-2 has-[:focus-visible]:outline-offset-2 has-[:focus-visible]:outline-ink ${checked ? 'border-ink shadow-[0_0_0_1px_var(--color-ink)]' : 'border-line hover:border-ink/40'}`}>
      <input type="radio" name={name} checked={checked} onChange={onChange} className="sr-only" />
      {Icon && (
        <span className={`grid size-9 shrink-0 place-items-center rounded-lg transition-colors ${checked ? 'bg-ink text-milk' : 'bg-milk-deep text-ink'}`}>
          <Icon {...ICON} />
        </span>
      )}
      <span className="min-w-0 flex-1">
        <span className="block text-sm font-semibold">{title}</span>
        {note && <span className="block text-xs text-muted">{note}</span>}
      </span>
      <span className={`grid size-5 shrink-0 place-items-center rounded-full border transition-colors ${checked ? 'border-ink bg-ink text-milk' : 'border-line'}`} aria-hidden>
        {checked && <Check {...ICON} size={12} strokeWidth={2.5} />}
      </span>
    </label>
  )
}

/** Patient step: who the user is, which policy member is the patient, and the relation. */
function PatientForm({ cw, act }) {
  const members = cw.answers.members ?? []
  const [who, setWho] = useState('self')
  const [name, setName] = useState(members[0] ?? '')
  const [relation, setRelation] = useState('')

  /** Phrase the answer so the agent's record_role tool gets role, patient and relation. */
  function submit(e) {
    e.preventDefault()
    if (who === 'self') act(cw.say)(`I am the patient. My name is ${name}.`)
    else act(cw.say)(`I am helping the patient, ${name}. I am their ${relation}.`)
  }

  return (
    <form onSubmit={submit} className="space-y-8">
      <fieldset className="space-y-3">
        <legend className="mb-3 text-sm font-medium">You are</legend>
        <div className="grid gap-2.5 sm:grid-cols-2">
          <Choice name="who" checked={who === 'self'} onChange={() => setWho('self')} title="The patient" note="Claiming for yourself" Icon={UserRound} />
          <Choice name="who" checked={who === 'caregiver'} onChange={() => setWho('caregiver')} title="Helping someone" note="Family member or caregiver" Icon={Users} />
        </div>
      </fieldset>
      {members.length > 0 ? (
        <fieldset className="space-y-3">
          <legend className="mb-3 text-sm font-medium">Patient, from your policy</legend>
          <div className="grid gap-2.5 sm:grid-cols-2">
            {members.map((m) => <Choice key={m} name="patient" checked={name === m} onChange={() => setName(m)} title={m} />)}
          </div>
        </fieldset>
      ) : (
        <label className="block space-y-2">
          <span className="text-sm font-medium">Patient name, as on the policy</span>
          <input className={FIELD} value={name} onChange={(e) => setName(e.target.value)} required />
        </label>
      )}
      {who === 'caregiver' && (
        <label className="block space-y-2">
          <span className="text-sm font-medium">You are their</span>
          <input className={FIELD} value={relation} onChange={(e) => setRelation(e.target.value)} placeholder="Son, daughter, spouse" required />
        </label>
      )}
      <Button type="submit" disabled={cw.busy || !name.trim()}>
        Continue <ArrowRight {...ICON} />
      </Button>
    </form>
  )
}

// How a caregiver can be authorised (DEV-025); every basis except holding the policy needs an uploaded proof.
const BASES = [
  ['policyholder', 'I hold the policy', 'The patient is a member on my policy', ShieldCheck],
  ['patient_consent', 'Written consent', 'A signed letter from the patient', FileCheck],
  ['insurer_registration', 'Registered with the insurer', 'The insurer lists me as representative', Landmark],
  ['power_of_attorney', 'Power of attorney', 'A registered POA for the patient', ScrollText],
]
const SCOPES = [
  ['submit_claim', 'Submit the claim'],
  ['share_records', 'Share medical records'],
  ['receive_updates', 'Receive insurer updates'],
  ['file_grievance', 'File a grievance or complaint'],
]
const PROOF = { types: ['authority_proof'], label: 'a consent letter, insurer registration or power of attorney' }

/** Authority step: who is acting, on what basis, with which proof, for what and until when. */
function AuthorityForm({ cw }) {
  const [name, setName] = useState(cw.authority?.representative_name ?? '')
  const [basis, setBasis] = useState('patient_consent')
  const [scope, setScope] = useState(SCOPES.map(([id]) => id))
  const [expires, setExpires] = useState('')
  // Start from the latest proof already on file, so recording again after a withdrawal needs no re-upload.
  const [proof, setProof] = useState(() => cw.documents.findLast((d) => d.doc_type === 'authority_proof' && d.status === 'parsed') ?? null)
  const needsProof = basis !== 'policyholder'

  /** Upload the proof; keep its id only when it was read as an authority document. */
  async function addProof(file) {
    const doc = await cw.upload(file, PROOF)
    if (doc) setProof(doc)
  }

  /** Send the form; the server checks it against the role and the proof. */
  function save(e) {
    e.preventDefault()
    cw.recordAuthority({
      representative_name: name.trim(), basis, scope, expires_on: expires || null,
      proof_doc_id: needsProof ? proof?.id ?? null : null,
    })
  }

  const toggle = (id) => setScope((s) => (s.includes(id) ? s.filter((x) => x !== id) : [...s, id]))
  return (
    <form onSubmit={save} className="space-y-8">
      {cw.authority?.status === 'withdrawn' && (
        <p role="alert" className="rounded-xl bg-coral-soft px-4 py-3 text-sm">Consent was withdrawn. Work on the claim is paused until a new authority is recorded.</p>
      )}
      {cw.authority?.status === 'expired' && (
        <p role="alert" className="rounded-xl bg-coral-soft px-4 py-3 text-sm">Your authority expired on {cw.authority.expires_on}. Record a current one to continue.</p>
      )}
      <label className="block space-y-2">
        <span className="text-sm font-medium">Your full name, as the insurer knows you</span>
        <input className={FIELD} value={name} onChange={(e) => setName(e.target.value)} required minLength={2} maxLength={120} />
      </label>
      <fieldset className="space-y-3">
        <legend className="mb-3 text-sm font-medium">What lets you act for the patient</legend>
        <div className="grid gap-2.5 sm:grid-cols-2">
          {BASES.map(([id, title, note, Icon]) => (
            <Choice key={id} name="basis" checked={basis === id} onChange={() => setBasis(id)} title={title} note={note} Icon={Icon} />
          ))}
        </div>
      </fieldset>
      {needsProof && (
        <div className="space-y-2">
          <span className="text-sm font-medium">Proof</span>
          {proof
            ? (
              <p className="flex flex-wrap items-center gap-2 text-sm">
                <Check {...ICON} size={14} />{proof.filename} read as proof.
                <Quiet type="button" onClick={() => setProof(null)} className="h-8 text-xs">Use another file</Quiet>
              </p>
            )
            : <DropZone onFile={addProof} busy={cw.busy} label="Drop the signed consent, registration or power of attorney" />}
        </div>
      )}
      <fieldset className="space-y-3">
        <legend className="mb-3 text-sm font-medium">It covers</legend>
        <div className="grid gap-2 sm:grid-cols-2">
          {SCOPES.map(([id, label]) => (
            <label key={id} className="flex items-center gap-2.5 text-sm">
              <input type="checkbox" checked={scope.includes(id)} onChange={() => toggle(id)} className="size-4 accent-ink" />
              {label}
            </label>
          ))}
        </div>
      </fieldset>
      <label className="block space-y-2">
        <span className="text-sm font-medium">Valid until (leave empty if it does not expire, or to use the date on the proof)</span>
        <input type="date" className={`${FIELD} h-10 w-auto`} value={expires} onChange={(e) => setExpires(e.target.value)} />
      </label>
      <Button type="submit" disabled={cw.busy || !name.trim() || !scope.length || (needsProof && !proof)}>
        Record authority <ArrowRight {...ICON} />
      </Button>
    </form>
  )
}

/** Claim type step: two choices, sent as soon as one is picked. */
function ClaimType({ cw, act }) {
  const options = [
    ['cashless', 'Cashless', 'The insurer pays the hospital directly.', Stethoscope],
    ['reimbursement', 'Reimbursement', 'You paid and claim the money back.', Wallet],
  ]
  return (
    <div className="grid gap-2.5 sm:grid-cols-2">
      {options.map(([value, title, note, Icon]) => (
        <button
          key={value}
          type="button"
          disabled={cw.busy}
          onClick={() => act(cw.setClaimType)(value)}
          className="group flex flex-col gap-6 rounded-xl border border-line bg-paper p-5 text-left transition-[border-color,translate] duration-300 hover:-translate-y-0.5 hover:border-ink disabled:opacity-40"
        >
          <span className="grid size-10 place-items-center rounded-lg bg-milk-deep text-ink transition-colors group-hover:bg-ink group-hover:text-milk">
            <Icon {...ICON} />
          </span>
          <span>
            <span className="block font-semibold">{title}</span>
            <span className="mt-0.5 block text-sm text-muted">{note}</span>
          </span>
        </button>
      ))}
    </div>
  )
}

/**
 * Current onboarding step.
 * @param {{step: object, cw: object, view: object}} props
 * @returns {JSX.Element}
 */
export default function StepForm({ step, cw, view, onOpenDocument }) {
  const [acted, setActed] = useState(false)
  // Wrap an action so the agent's reply shows here if the step does not advance (it explains why).
  const act = (fn) => (...args) => {
    setActed(true)
    fn(...args)
  }

  let body
  if (step.id === 'confirm') {
    body = cw.pending?.type === 'confirm_policy'
      ? <ConfirmPolicy key={cw.pending.policy.doc_id} pending={cw.pending} onAnswer={act(cw.answer)} busy={cw.busy} onOpenDocument={onOpenDocument} />
      : <p className="text-sm text-muted">Reading your policy...</p>
  } else if (step.id === 'patient') {
    body = <PatientForm cw={cw} act={act} />
  } else if (step.id === 'authority') {
    body = <AuthorityForm cw={cw} />
  } else if (step.id === 'claimType') {
    body = <ClaimType cw={cw} act={act} />
  } else {
    body = <DropZone onFile={act((file) => cw.upload(file, EXPECT[step.id]))} busy={cw.busy} label={DROP_LABEL[step.id]} />
  }

  return (
    <div className="space-y-6">
      {body}
      {cw.busy && cw.activity !== 'reading' && <MascotStatus state={cw.activity} />}
      {step.id === 'patient' && view.patientMismatch && (
        <p role="alert" className="rounded-xl bg-coral-soft px-4 py-3 text-sm">That name does not match a member on the policy. Pick the patient from the list.</p>
      )}
      {acted && !cw.busy && cw.reply && (
        <div className="flex gap-3 rounded-2xl border border-line bg-paper p-4 text-sm">
          <AgentMark />
          <div className="min-w-0 flex-1 pt-0.5"><Markdown text={cw.reply} /></div>
        </div>
      )}
      {step.optional && (
        <div className="flex items-center justify-between gap-4 pt-2">
          <span className="text-xs text-muted">Optional for now. Claimwise asks again when the claim needs it.</span>
          <Quiet onClick={() => cw.skip(step.id)} disabled={cw.busy}>
            Skip <ArrowRight {...ICON} />
          </Quiet>
        </div>
      )}
    </div>
  )
}
