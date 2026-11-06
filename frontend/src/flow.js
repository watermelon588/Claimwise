// Pure rules that turn backend state into onboarding steps, claim phases and "needs you" alerts.
// No React here, so every layout derives the same picture from the same state.

const DOC_LABELS = {
  discharge_summary: 'Discharge summary',
  hospital_bill: 'Final hospital bill',
  pharmacy_bill: 'Pharmacy bills',
  investigation_report: 'Test reports',
  prescription: 'Prescriptions',
  id_proof: 'ID proof',
  cancelled_cheque: 'Cancelled cheque',
  authority_proof: 'Consent or authority proof',
}

/** Human label for a backend document type. */
export const docLabel = (type) => {
  const text = DOC_LABELS[type] ?? String(type).replaceAll('_', ' ')
  return text.charAt(0).toUpperCase() + text.slice(1)
}

/** Rupee amount for display, or a dash when the letter did not state it. */
export const money = (n) => (n == null ? '-' : `Rs ${Number(n).toLocaleString('en-IN')}`)

/** Two-digit step number, e.g. 3 -> "03". */
export const pad = (n) => String(n).padStart(2, '0')

// Onboarding steps in the order they are asked. Optional steps can be skipped and come back as alerts.
const STEPS = [
  { id: 'policy', title: 'Upload your policy', hint: 'Your policy schedule or e-card, as a PDF or a photo.' },
  { id: 'confirm', title: 'Check the policy details', hint: 'We read these from your document. Fix anything that looks wrong.' },
  { id: 'patient', title: 'Who is the patient?', hint: 'The patient has to be a member on this policy.' },
  // Only for someone acting for the patient (DEV-025); it also comes back if consent is withdrawn or expires.
  { id: 'authority', title: 'Your authority to act', hint: 'Insurers accept a representative only with proof. Record what lets you act for the patient.', caregiver: true },
  { id: 'claimType', title: 'Type of claim', hint: 'Cashless is settled with the hospital. Reimbursement means you paid and claim it back.', optional: true },
  { id: 'discharge_summary', title: 'Discharge summary', hint: 'The summary the hospital gives at discharge.', optional: true },
  { id: 'hospital_bill', title: 'Final hospital bill', hint: 'The itemised final bill from the hospital.', optional: true },
]

// Stage order from the backend C1 review (and P1 payment check), used to tell which phases are behind us.
const STAGES = ['preparing', 'approved_to_submit', 'submitted', 'query_raised', 'decided', 'payment_reported', 'payment_mismatch', 'payment_verified']
const HEADLINES = {
  preparing: 'Preparing your claim',
  approved_to_submit: 'Ready for you to submit',
  submitted: 'Waiting for the insurer',
  query_raised: 'The insurer needs more',
  decided: 'The insurer has decided',
  payment_reported: 'Check the money arrived',
  payment_mismatch: 'The payment does not add up',
  payment_verified: 'The payment is in your account',
}

// Payment issues the user fixes by uploading a document (a bank statement).
const UPLOAD_FIX = new Set(['bank_statement_needed', 'statement_too_old'])

// Setup accounts for 20 points. Hospital documents count in claim preparation only.
const SETUP_PROGRESS = { policy: 7, confirm: 6, patient: 5, claimType: 2, authority: 0 }
const CLAIM_PROGRESS = { docs: 12, check: 8, approve: 10, submit: 10, review: 10, decision: 10, payment: 20 }

/** Return weighted journey completion from the existing onboarding and claim phase statuses. */
export function journeyProgress({ steps, phases }) {
  const setup = steps.reduce((total, step) => (
    total + (['done', 'skipped'].includes(step.status) ? (SETUP_PROGRESS[step.id] ?? 0) : 0)
  ), 0)
  return phases.reduce((total, phase) => (
    total + (phase.status === 'done' ? (CLAIM_PROGRESS[phase.id] ?? 0) : 0)
  ), setup)
}

/**
 * Mark each item done / now / todo / later: the first unfinished, non-later item is "now".
 * @param {Array<{done?: boolean, skipped?: boolean, later?: boolean}>} items
 * @returns {Array<object>} items with a status field
 */
function withStatus(items) {
  let nowSet = false
  return items.map((it) => {
    let status = it.done ? 'done' : it.skipped ? 'skipped' : it.later ? 'later' : 'todo'
    if (status === 'todo' && !nowSet) {
      status = 'now'
      nowSet = true
    }
    return { ...it, status }
  })
}

/**
 * Onboarding steps with status and phase summaries, from backend onboarding/claim state plus local form answers.
 * @param {{onboarding: object|null, pending: object|null, claim: object|null, answers: object, skipped: object, documents?: Array<object>}} s
 * @returns {Array<object>}
 */
function buildSteps({ onboarding, pending, claim, answers, skipped, documents, authority }) {
  const missing = onboarding?.missing ?? ['policy_document', 'role']
  const have = claim?.checklist?.have ?? []
  const confirming = pending?.type === 'confirm_policy'
  const done = {
    policy: !missing.includes('policy_document'),
    confirm: !confirming && !missing.includes('policy_document') && !missing.includes('policy_confirmation'),
    patient: !missing.includes('role') && !missing.includes('patient_on_policy'),
    authority: !missing.includes('authority'),
    claimType: Boolean(answers.claimType),
    discharge_summary: have.includes('discharge_summary'),
    hospital_bill: have.includes('hospital_bill'),
  }

  const polDoc = (documents || []).find((d) => d.doc_type === 'policy_document' || d.facts?.policy_number)
  const dsDoc = (documents || []).find((d) => d.doc_type === 'discharge_summary')
  const billDoc = (documents || []).find((d) => d.doc_type === 'hospital_bill')

  const summaries = {
    policy: polDoc
      ? `${polDoc.facts?.insurer || 'Policy'} (${polDoc.facts?.policy_number || 'Uploaded'})`
      : done.policy ? 'Policy schedule received' : null,
    confirm: done.confirm
      ? (pending?.policy ? `Sum insured: ${money(pending.policy.sum_insured)}` : 'Policy facts verified')
      : null,
    patient: done.patient
      ? `Patient: ${answers.members?.[0] || 'Confirmed policy member'}`
      : null,
    authority: authority?.status === 'active'
      ? `${authority.representative_name}, ${String(authority.basis).replaceAll('_', ' ')}`
      : null,
    claimType: done.claimType
      ? `${answers.claimType === 'cashless' ? 'Cashless' : 'Reimbursement'} claim`
      : null,
    discharge_summary: dsDoc
      ? `${dsDoc.facts?.hospital_name || 'Hospital summary'}: ${dsDoc.facts?.diagnosis || 'Discharged'}`
      : done.discharge_summary ? 'Discharge summary parsed' : null,
    hospital_bill: billDoc
      ? `Total charges: ${money(billDoc.facts?.total_amount)}`
      : done.hospital_bill ? 'Itemized hospital bill parsed' : null,
  }

  const acting = missing.includes('authority') || Boolean(authority)
  return withStatus(STEPS.filter((s) => !s.caregiver || acting).map((s) => ({
    ...s,
    done: done[s.id],
    skipped: s.optional && skipped[s.id],
    summary: summaries[s.id],
  })))
}

/** One-line state of the payment check (P1) for the payment phase. */
function paymentDetail(p) {
  if (!p) return null
  if (p.status === 'verified') return `${money(p.credit.amount)} credited on ${p.credit.date}`
  if (p.status === 'paid_to_hospital') return 'Paid to the hospital (cashless)'
  if (p.status === 'none_due') return 'Nothing to pay: claim rejected'
  if (p.status === 'mismatch') return 'Does not match, see Needs you'
  return p.reported ? 'Insurer says paid, bank not checked' : 'Waiting for the money'
}

// Where the dispute route stands (DEV-026), in words for the dispute phase.
const DISPUTE_TEXT = {
  open: 'You can challenge the deduction',
  grievance_approved: 'Letter approved: send it, then record the date',
  grievance_filed: 'Grievance sent, waiting for the reply',
  ombudsman_approved: 'Complaint approved: file it, then record the date',
  ombudsman_filed: 'With the Ombudsman',
  revised: 'The insurer revised its decision',
}

/**
 * Claim phases shown as a to-do list after onboarding. Dispute stays later work until there is something to dispute.
 * @param {object|null} claim C1 review from the backend
 * @param {object|null} dispute dispute view from the backend, or null
 * @returns {Array<object>}
 */
function buildPhases(claim, dispute) {
  const at = STAGES.indexOf(claim?.stage ?? 'preparing')
  const needed = claim?.checklist?.missing_required ?? ['discharge_summary', 'hospital_bill']
  const blocks = (claim?.issues ?? []).filter((i) => i.severity === 'block').length
  const d = claim?.decision
  return withStatus([
    { id: 'start', title: 'Get started', done: true },
    {
      id: 'docs', title: 'Collect hospital documents', done: needed.length === 0 || at >= 2,
      detail: needed.length ? `Needed: ${needed.map(docLabel).join(', ')}` : null,
    },
    {
      id: 'check', title: 'Check the documents agree', done: (needed.length === 0 && blocks === 0) || at >= 2,
      detail: blocks ? `${blocks} to fix` : null,
    },
    { id: 'approve', title: 'Approve the claim pack', done: at >= 1 },
    { id: 'submit', title: 'Submit to your insurer', detail: 'You do this on the insurer portal', done: at >= 2 },
    { id: 'review', title: 'Insurer review', detail: at === 3 ? 'The insurer asked for more' : null, done: at >= 4 },
    {
      id: 'decision', title: 'Understand the decision', done: at >= 4,
      detail: d ? `${money(d.approved)} of ${money(d.claimed)} approved` : null,
    },
    {
      id: 'payment', title: 'Check the payment', detail: paymentDetail(claim?.payment),
      done: ['verified', 'paid_to_hospital', 'none_due'].includes(claim?.payment?.status),
    },
    {
      id: 'dispute', title: 'Dispute a shortfall', later: !dispute, detail: DISPUTE_TEXT[dispute?.status] ?? null,
      done: dispute?.status === 'revised' && !dispute.disputable,
    },
  ])
}

/**
 * What needs the user now. Skipped onboarding items come back here once they block progress.
 * @param {{claim: object|null, answers: object, pending: object|null}} s
 * @returns {Array<{id: string, tone: 'block'|'ask'|'note', text: string, action?: string}>}
 */
function buildAlerts({ claim, answers, pending }) {
  if (!claim) return []
  const out = []
  const needed = claim.checklist?.missing_required ?? []
  const blocks = claim.issues.filter((i) => i.severity === 'block')

  if (claim.stage === 'preparing') {
    if (!answers.claimType) {
      out.push({ id: 'claimType', tone: 'ask', action: 'claimType', text: 'Is this a cashless or a reimbursement claim? The claim pack needs it.' })
    }
    for (const t of needed) {
      out.push({ id: `doc-${t}`, tone: 'ask', action: 'upload', text: `${docLabel(t)} is needed before the claim pack.` })
    }
  }
  claim.issues.forEach((i, n) => out.push(UPLOAD_FIX.has(i.code)
    ? { id: `issue-${n}`, tone: 'ask', action: 'upload', text: i.message }
    : { id: `issue-${n}`, tone: i.severity === 'block' ? 'block' : 'note', text: i.message }))

  // Next action for the current stage.
  if (claim.stage === 'preparing' && !needed.length && !blocks.length && !pending) {
    out.push({ id: 'prepare', tone: 'ask', action: 'prepare', text: 'Your documents are in order. Build the claim pack to review and approve it.' })
  }
  if (claim.stage === 'approved_to_submit') {
    out.push({ id: 'submitted', tone: 'ask', action: 'submitted', text: 'Submit the approved pack on your insurer portal, then tell us the date.' })
  }
  if (claim.stage === 'submitted') {
    out.push({ id: 'waiting', tone: 'note', action: 'upload', text: 'Upload any letter the insurer sends, a query or a decision.' })
  }
  for (const item of claim.query?.requested ?? []) {
    if (!item.already_provided) {
      out.push({ id: `req-${item.label}`, tone: 'ask', action: 'upload', text: `The insurer asks for: ${item.label}.` })
    }
  }
  if (claim.decision?.difference > 0) {
    out.push({ id: 'explain', tone: 'ask', action: 'explain', text: `${money(claim.decision.difference)} was deducted. Go through it line by line.` })
  }
  return out
}

/**
 * Everything a layout needs to render, derived from the hook state.
 * @param {object} cw state from useClaimwise
 * @returns {object} steps, current step, phases, alerts, headline and progress counts
 */
export function buildView(cw) {
  const steps = buildSteps(cw)
  const index = steps.findIndex((s) => s.status === 'now')
  const missing = cw.onboarding?.missing ?? []
  const phases = buildPhases(cw.claim, cw.dispute)
  return {
    onboarding: index !== -1,
    steps,
    index,
    total: steps.length,
    current: steps[index],
    patientMismatch: !missing.includes('role') && missing.includes('patient_on_policy'),
    phases,
    phaseDone: phases.filter((p) => p.status === 'done').length,
    now: phases.find((p) => p.status === 'now'),
    alerts: buildAlerts(cw),
    headline: HEADLINES[cw.claim?.stage] ?? HEADLINES.preparing,
  }
}
