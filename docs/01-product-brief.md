# Claimwise product brief

**Status:** Draft for scope review. The prototype uses synthetic records and mock providers. The proposed first release below is a design decision for review.

## Product and audience

Claimwise keeps the evidence, decisions, and next action for a health insurance claim in one case file. It could replace the claimant's working combination of a document folder, insurer inbox, reminder list, and payment spreadsheet. The insurer portal, hospital helpdesk, bank, and grievance bodies remain authoritative for the actions and records they own. [Alternatives](02-research/alternatives.md)

| User | Goal | What the case file needs to show |
| --- | --- | --- |
| Patient | Submit a complete claim and confirm what was paid. | Required documents, the approved pack, the insurer reference, and matched payment evidence. |
| Authorized caregiver | Act for another person within a verified scope. | Who is acting, whose records they concern, the basis and expiry of authority, and whether the next action is permitted. |
| Household with multiple covers | Choose a primary policy and coordinate the remaining eligible amount. | The selected cover, earlier decisions and payments, and evidence needed for a separate balance claim. |

Repeated document requests, missing explanations for deductions, and a portal status with no bank credit motivate keeping one case across stages. These are qualitative signals. Some claimants report smooth settlement, and the research has yet to find firsthand evidence for a mid-case authority withdrawal or the exact bank-credit mismatch scenario. [Evidence register](02-research/evidence-register.md) · [Personas and situations](02-research/personas-and-situations.md)

## Proposed first release

Use India as the research and demonstration context, with reimbursement preparation and follow-through as the starting route. Support cashless coordination through user or hospital handoffs. The prototype accepts both route labels and includes a cashless mock, which is evidence of demo coverage rather than a decision to launch cashless preauthorization. [Scope questions](decisions.md#open-questions) · [Integration access](05-technical/api-tool-matrix.md)

| Capability | Prototype today | Proposed first release |
| --- | --- | --- |
| Prepare the case | Reads synthetic PDFs or images, asks the claimant to confirm policy facts, flags gaps, and builds a reviewable pack. | Execute evidence organization and checks. Ask a human to correct unclear facts. |
| Submit and track | Offers PDF and email drafts. A connected mock payer can receive an approved pack and supply claim status. | Coordinate through a claimant unless authorized live access has been verified. |
| Handle requests and decisions | Surfaces requests and decision details, flags repeated requests, and prepares evidence or drafts. | Execute review and drafting. Claimant confirms recipients, replies, or seeks specialist help. |
| Verify payment and continue | Compares available evidence and can prepare a balance claim or reopen payment checks after a revised decision. | Execute reconciliation and flag uncertainty. The bank or payer confirms ambiguous transactions. |
| Dispute and close | Drafts grievance or Ombudsman letters and tracks user-recorded filing and revised evidence. | Coordinate through a human. Defer automatic filing, legal representation, and medical judgment. |

## User control and success

The user starts with the patient and policy, selects a route or cover where needed, and delegates preparation, comparison, and follow-up. The workspace shows missing information, blockers, and the next action. Users correct extracted facts and review the exact pack before approval. A changed pack needs fresh approval. A claimant can record a manual submission, while an authoritative receipt or mock payer record provides stronger evidence. A decision and payment verification are separate outcomes. [UX sketches](06-experience/ux-sketches.md) · [Permissions and data](05-technical/actions-permissions-and-data.md)

The caregiver record describes authority and proof in the prototype. The external provider decides whether it accepts the representative. The proposed release requires verified user identity, scoped access and revocation, and data-handling controls before using real records. [Delivery and rollout](07-delivery/feasibility-and-rollout.md)

---

[Index](../README.md) | Next: [Evidence register](02-research/evidence-register.md)
