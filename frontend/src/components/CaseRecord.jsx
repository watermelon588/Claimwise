// Case record (Wave 4): which policy this claim goes to and earlier rounds, who acts and on what authority,
// where a dispute stands, and the audit log of who did what. Everything comes from the API; nothing is derived here.
import { useState } from 'react'
import { money } from '../flow.js'
import { Outline, Quiet } from './ui.jsx'
import { EYEBROW } from './tokens.js'

const BASIS = {
  policyholder: 'policyholder', patient_consent: 'written consent',
  insurer_registration: 'registered with the insurer', power_of_attorney: 'power of attorney',
}

/** One labelled row. */
function Row({ label, children }) {
  return (
    <div className="flex justify-between gap-4 border-b border-line/70 py-2 text-sm">
      <dt className="text-muted">{label}</dt>
      <dd className="text-right font-medium">{children}</dd>
    </div>
  )
}

/** Policies on file and earlier claim rounds (DEV-024). */
function Household({ household }) {
  if (!household || (household.policies.length < 2 && !household.history.length)) return null
  return (
    <div>
      <h3 className={EYEBROW}>Policies</h3>
      <dl className="mt-2">
        {household.policies.map((p) => (
          <Row key={p.doc_id} label={`${p.insurer} ${p.policy_number}`}>
            {p.doc_id === household.chosen ? `This claim (round ${household.round})` : (p.policy_type ?? 'On file')}
          </Row>
        ))}
        {household.history.map((h) => (
          <Row key={h.round} label={`Round ${h.round}: ${h.insurer}`}>
            {money(h.approved)} of {money(h.claimed)}, claim {h.claim_number}
          </Row>
        ))}
      </dl>
      {household.balance_of && (
        <p className="mt-2 text-xs text-muted">Balance claim: {money(household.balance_of.balance)} not paid by {household.balance_of.previous}.</p>
      )}
    </div>
  )
}

/** The caregiver's authority, with a two-step withdraw (DEV-025). */
function Authority({ cw }) {
  const [confirming, setConfirming] = useState(false)
  const a = cw.authority
  if (!a) return null
  return (
    <div>
      <h3 className={EYEBROW}>Acting for the patient</h3>
      <dl className="mt-2">
        <Row label="Representative">{a.representative_name}</Row>
        <Row label="Basis">{BASIS[a.basis] ?? a.basis}</Row>
        <Row label="Covers">{a.scope.map((s) => s.replaceAll('_', ' ')).join(', ')}</Row>
        <Row label="Valid until">{a.expires_on ?? 'No end date'}</Row>
        <Row label="Status"><span className={a.status === 'active' ? '' : 'text-coral-ink'}>{a.status}</span></Row>
      </dl>
      {a.status === 'active' && (confirming ? (
        <div className="mt-3 flex flex-wrap items-center gap-2 text-sm">
          <span>Withdraw consent? Work pauses and any approval is cancelled.</span>
          <Outline onClick={() => { setConfirming(false); cw.withdrawAuthority() }} disabled={cw.busy}>Yes, withdraw</Outline>
          <Quiet onClick={() => setConfirming(false)}>Keep</Quiet>
        </div>
      ) : (
        <Quiet onClick={() => setConfirming(true)} disabled={cw.busy} className="mt-2 h-8 text-xs">Patient withdrew consent</Quiet>
      ))}
    </div>
  )
}

/** Grievance and Ombudsman dates and eligibility (DEV-026). */
function Dispute({ dispute }) {
  if (!dispute || dispute.status === 'open') return null
  return (
    <div>
      <h3 className={EYEBROW}>Dispute</h3>
      <dl className="mt-2">
        <Row label="In dispute">{money(dispute.disputed_amount)}</Row>
        {dispute.grievance_filed_on && <Row label="Grievance sent">{dispute.grievance_filed_on}</Row>}
        {dispute.grievance_due && <Row label="Reply due by">{dispute.grievance_due}</Row>}
        {dispute.insurer_reply_on && <Row label="Insurer replied">{dispute.insurer_reply_on}</Row>}
        {dispute.ombudsman_from && !dispute.ombudsman_filed_on && (
          <Row label="Ombudsman">{dispute.ombudsman_eligible ? 'Open now' : `From ${dispute.ombudsman_from} or the insurer's reply`}</Row>
        )}
        {dispute.ombudsman_filed_on && <Row label="Ombudsman filed">{dispute.ombudsman_filed_on}</Row>}
        {dispute.status === 'revised' && <Row label="Revised decision">{money(dispute.approved_now)} approved</Row>}
      </dl>
    </div>
  )
}

/**
 * Case record section; renders nothing when there is nothing beyond a single, self-run claim.
 * @param {{cw: object}} props
 * @returns {JSX.Element|null}
 */
export default function CaseRecord({ cw }) {
  const parts = [<Household key="h" household={cw.household} />, <Authority key="a" cw={cw} />, <Dispute key="d" dispute={cw.dispute} />]
  const shown = Boolean(cw.authority) || (cw.dispute && cw.dispute.status !== 'open')
    || (cw.household && (cw.household.policies.length > 1 || cw.household.history.length > 0))
  if (!shown && !cw.audit.length) return null
  return (
    <section aria-labelledby="dossier-record" className="mt-12 space-y-6">
      <h2 id="dossier-record" className={EYEBROW}>Case record</h2>
      {parts}
      {cw.audit.length > 0 && (
        <details className="group">
          <summary className={`cursor-pointer list-none ${EYEBROW} hover:text-ink`}>Who did what ({cw.audit.length})</summary>
          <ul className="mt-2 divide-y divide-line text-sm">
            {cw.audit.map((e) => (
              <li key={e.id} className="py-2">
                <p>{e.detail}</p>
                <p className="mt-0.5 font-mono text-[10px] uppercase tracking-[0.12em] text-muted">{e.actor} · {e.at.slice(0, 16).replace('T', ' ')}</p>
              </li>
            ))}
          </ul>
        </details>
      )}
    </section>
  )
}
