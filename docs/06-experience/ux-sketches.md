# UX sketches

**Status:** Draft wireframes mapped to the current Dossier. Boxes represent screen regions. The prototype uses one workspace and updates its stage from the case state. [Dossier layout](../../frontend/src/layouts/Dossier.jsx) · [View model](../../frontend/src/flow.js)

## Setup and goal

~~~text
Case file                    Upload your policy
Stage · Documents · To fix  [Drop a PDF or image] [Choose file]
                             Then: check facts, patient and claim type
~~~

The policy card shows what was extracted and lets the user correct fields or decline confirmation. Setup asks who the patient is and whether the user is acting for them. The caregiver authority step collects basis, scope and applicable proof. Optional steps can be skipped and return as alerts if the claim needs them. [Setup forms](../../frontend/src/components/StepForm.jsx) · [Policy confirmation](../../frontend/src/components/ConfirmPolicy.jsx)

## Progress and needs input

~~~text
Journey progress              Current step
Case file and documents       Needs you [reason] [next action]
                              Notifications [new update]
                              Conversation [ask about this claim]
~~~

The progress indicator summarizes the current tasks. The attention area explains what is missing and who acts next. A submitted claim can show a waiting state, a new request, or a provider update. Pending approvals take precedence over other action buttons. [Progress and alerts](../../frontend/src/flow.js) · [Notifications](../../frontend/src/components/Notifications.jsx)

## Comparison, approval and outcome

~~~text
Evidence                      Decision and payment
[Current policy] [Other cover] Claimed | Approved | Payment evidence
[Original or extracted facts] Match status and supporting records

Review claim pack
[Originals] [Download PDF or email] [Review for approval]
~~~

Households can select the policy for the current round. The case record distinguishes decision and payment evidence. The pack viewer shows the included documents and supports review and export. Approval is a separate card. A connected mock submission is available only when the current action is offered. [Case record](../../frontend/src/components/CaseRecord.jsx) · [Pack viewer](../../frontend/src/components/ClaimPack.jsx) · [Approval card](../../frontend/src/components/ApproveSubmission.jsx)

## Correct and resume

Use the policy confirmation fields to correct extraction or add a corrected document to the same thread. For supported document types the workspace asks whether to replace the earlier version or keep both. Review the new pack after an approval is invalidated. Reopening a saved session restores the case view. The in-tab document preview may depend on the original selected file. [Document review](../../frontend/src/components/DocumentModal.jsx) · [Session state](../../frontend/src/useClaimwise.js)

---

Previous: [Complete journeys](journeys.md) | [Index](../../README.md) | Next: [Phased implementation plan](../07-delivery/implementation-plan.md)
