// Icon and short label for each onboarding step and claim phase, shared by both progress bars.
import { createElement } from 'react'
import {
  FileCheck, FileHeart, Flag, FolderOpen, Gavel, Hourglass, Landmark, ReceiptText,
  Scale, ScanSearch, Send, ShieldCheck, UserRound, UserRoundCheck, Wallet,
} from 'lucide-react'

const META = {
  policy: [ShieldCheck, 'Policy'],
  confirm: [ScanSearch, 'Details'],
  patient: [UserRound, 'Patient'],
  authority: [UserRoundCheck, 'Authority'],
  claimType: [Wallet, 'Claim type'],
  discharge_summary: [FileHeart, 'Discharge'],
  hospital_bill: [ReceiptText, 'Final bill'],
  start: [Flag, 'Start'],
  docs: [FolderOpen, 'Documents'],
  check: [ScanSearch, 'Checks'],
  approve: [FileCheck, 'Approve'],
  submit: [Send, 'Submit'],
  review: [Hourglass, 'Review'],
  decision: [Scale, 'Decision'],
  payment: [Landmark, 'Payment'],
  dispute: [Gavel, 'Dispute'],
}

/** Icon element for a step or phase id (an element, not a component, so callers render it directly). */
export const stepIcon = (id, props) => createElement(META[id]?.[0] ?? Flag, props)

/** Short label for a step or phase id, falling back to its full title. */
export const shortFor = (item) => META[item.id]?.[1] ?? item.title
