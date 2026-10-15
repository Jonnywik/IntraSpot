# Part 1: Simulated User Walkthroughs and Resolution Plan

**Prepared:** 2026-10-04  
**Status:** Role-play review complete; prototype fixes and representative-user validation remain open.

## What this review covers

Four agents role-played the people expected to use IntraSpot: a public visitor, an eligible attendee, an organization owner, and a platform admin. I also checked the corresponding clickable Penpot flows where the preview was available.

This is a simulated walkthrough, not user research. The role-play agents could not independently operate the live preview, so their feedback is combined with the directly observed prototype paths below. It does not count as the representative-user testing required by the project handoff.

## Combined findings

| Role | What appears to work | Problem or remaining question | Evidence |
|---|---|---|---|
| Public visitor | The desktop guest flow goes from Discover to event details. The detail screen shows event information and directs visitors to sign in to participate. | Actual visitors have not confirmed that they can find, understand, or distinguish a published event. Public visibility of comment previews is still an open product question. | Discover → Event details was checked in the preview. Comprehension is untested. Comment visibility is unresolved in `Open Questions.md`. |
| Eligible attendee | The simulated eligible path reaches profile setup, registration review, a pending request, My Events, and the event detail. The screens say a request is not a confirmed place. | **Post** on the comments screen has no visible effect. Eligibility and registration are simulated; no real request is submitted. | The route was checked in the prototype. The no-op Post interaction was observed in the prior walkthrough. |
| Organization owner | The owner can move from application to pending status, edit a draft, and save back to the pending workspace. Publishing is unavailable while pending. The approved path reaches publish review and a published listing. | **Preview** in the pending draft editor stays on the same screen. The owner cannot inspect the draft as an event preview from that point. | The pending Preview control was clicked in the preview and did not navigate. The approved publishing path was also checked. |
| Platform admin | The approval path goes from the queue through offline assessment and confirmation to an approved queue and decision view. The view contains sample outcomes, admin names, and dates/times. | The rejection path has not been walked end to end. The decision rows are illustrative prototype data, not persisted decisions. | The approval path and sample decision view were checked. Rejection remains unverified. |

## Fix plan

### 1. Make pending-draft Preview usable

1. Connect the pending editor’s **Preview** control to the intended pending-draft preview screen. The board list includes a candidate named `39P • Organizer / Pending draft preview`; confirm it shows the same draft before wiring the link.
2. Add a clear way to return to editing.
3. Keep the preview labeled as a private draft or pending review. It must not look published or appear in the public Discover flow.
4. Walk the owner path again: pending → draft editor → preview → back to edit → save. Confirm the owner can explain that the draft is not public.

### 2. Give comment submission visible prototype feedback

1. Make **Post** respond in the prototype, for example by showing the submitted comment in the current preview session or displaying a clear submission confirmation.
2. Keep the interaction within the existing access rule: signed-in PLM stakeholders may read and add comments before the event starts.
3. Label the result as simulated if it is not saved. Do not decide whether guests can see comment previews; that is still unresolved in `Open Questions.md`.
4. Walk the flow again and confirm the user can tell whether the action worked and whether the comment was saved.

### 3. Verify the admin rejection journey

1. Start from the admin accreditation queue and follow the **not approved/reject** branch through its confirmation.
2. Confirm the organization’s resulting status is clear in the queue.
3. Open the decision view and confirm the sample record communicates the outcome, admin, and date/time, as the approval example does.
4. Keep sample records visibly illustrative; the prototype does not persist real admin decisions.

### 4. Run a self-guided rehearsal

After the three fixes, walk the tasks below without using the screen names as hints. This checks whether the prototype is ready for other people; it does not replace representative-user testing.

| Task | Pass condition |
|---|---|
| As a visitor, find a published event and decide whether you can participate. | Find its details and correctly identify what is public and what requires sign-in. |
| As an eligible attendee, request a place and find the request afterward. | Reach My Events and correctly explain that pending does not mean confirmed. |
| As an owner, save a draft while approval is pending, preview it, and find the publish control. | Explain that the draft is private and publishing is blocked until approval. |
| As an admin, reject one application and approve another. | Reach both outcomes and locate decision information including the outcome, admin, and date/time. |

For each task, record: completed without a hint (yes/no), where you hesitated, what you thought the current status meant, and what you would change. If you already know the screens, mark the result as a rehearsal rather than evidence of first-time usability.

### 5. Complete the actual Part 1 validation gate

When participants are available, run the same tasks with representative organization members, students/faculty, and a public visitor on both mobile and desktop. Define pass/fail measures before the sessions and record misunderstandings about eligibility, pending versus approved, and public versus private states. The handoff’s exit gate is complete only when representative users can complete and explain their journeys without the author interpreting the interface for them.

## Suggested order

1. Fix pending-draft Preview.
2. Fix comment Post feedback.
3. Walk and clarify the admin rejection branch.
4. Run the self-guided rehearsal; revise any unclear state labels.
5. Run representative-user sessions on mobile and desktop; assess the handoff’s pass conditions.

The first three are prototype interaction fixes. The fourth is a solo rehearsal. Only the fifth can establish the representative-user validation required to close Part 1.

## Source of requirements

The canonical source is the IntraSpot project area in the Obsidian vault, starting from `AI Index.md`. This review used:

- `Development Handoff.md`: “Start here now: build the clickable prototype,” “Prototype exit gate,” and “Pass condition.”
- `Functionality.md`: “Comments and event moderation.”
- `UI & UX.md`: event details and comments behavior.
- `Open Questions.md`: public comment visibility.

The workspace copies of `Development Handoff.md` and `IDEA.md` are not authoritative.
