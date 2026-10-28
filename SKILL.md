---
name: cold-email
description: Research and draft personalized academic outreach emails, including professor cold emails (套磁), follow-ups, thank-you notes, and multi-professor outreach campaigns. Use for a single email, batch drafting, or campaign tracking; do not use for generic job-sales outreach.
---

# Academic Outreach / 套磁

Produce concise, evidence-based outreach that connects the applicant's verified work to a professor's current research. Support three modes:

- **Single draft**: one recipient and one email.
- **Batch drafts**: individualized drafts for a supplied professor list.
- **Campaign**: drafts plus a target tracker, review state, and follow-up schedule.

Never send, schedule, or otherwise contact recipients without the user's explicit authorization covering the exact recipient(s) and approved draft(s). A batch authorization may cover a clearly identified set. Drafting and local tracking do not imply sending permission.

## Inputs and source priority

Use information in this order, with newer direct user statements overriding older sources:

1. The user's current instructions and corrections.
2. A CV, target list, paper, or other material supplied in the current request.
3. The project-root `.local.md` CV profile and writing preferences.
4. Previously saved campaign data.

At the start, locate `.local.md` from the current project root. Do not use legacy `${CLAUDE_PLUGIN_ROOT}` variables. If no usable applicant profile exists, ask for a CV or the few facts needed for the requested email; do not force the user to run another skill when a small missing input can be supplied directly.

Do not invent research ownership, metrics, publication status, admissions plans, or professor recruiting status. Mark unverified or time-sensitive facts as unknown and either research them or ask only when the missing fact materially affects the draft.

## Choose the mode

Infer the smallest suitable mode from the request. Do not ask a generic personalization question.

- For one named professor, use **single draft**.
- For multiple named professors or a table/list, use **batch drafts**.
- When the user asks to organize, automate, track, prioritize, or follow up, use **campaign**.
- If the user asks to find professors rather than contact known targets, use the available professor-matching workflow first, then return here for outreach.

If the user has not provided a target, ask for the professor/lab name and institution. Ask further questions only when research cannot resolve the answer or a subjective choice would materially change the result.

## Research and verification

For each target, verify from primary or authoritative sources where possible:

- current institution, department, title, and official contact channel;
- one recent, relevant paper or active project;
- whether an official page states recruiting or application instructions;
- any required subject line, form, or instruction that supersedes the normal email format.

Prefer the professor/lab/university page and the publication's official page. Use bibliographic indexes as supporting sources. Distinguish publication year/status from preprint year/status. Record source URLs and the date checked for campaign work.

Do not infer that a professor is recruiting because their lab is active. Say “not publicly confirmed” when appropriate.

## Build the evidence bridge

Before drafting, identify this chain:

`applicant evidence -> professor work -> plausible shared question -> proportionate ask`

Select one applicant project and one professor paper/project. Make the bridge technical and specific: a shared problem, a method that could transfer, an evaluation gap, or a limitation that motivates a research question. Do not merely state that interests align, and do not imply an established collaboration.

Use only the strongest relevant evidence. Preserve distinctions between the applicant's personal contribution and team-level results. Respect any wording preferences in `.local.md`.

## Draft the email

Default first-contact structure:

1. Specific subject line.
2. Greeting and one-sentence identity, application cycle, and research focus.
3. Two or three sentences of applicant-first evidence: problem, contribution, and credible result.
4. One concrete professor-work connection and a focused forward-looking question.
5. A clear ask about advising availability and, if appropriate, a brief conversation.
6. Short sign-off with website and CV attachment/link note when available.

For applicants without substantial research experience, lead with relevant preparation and a scoped learning goal rather than exaggerating project maturity.

Write in the user's requested language. Otherwise, normally use English for international/Hong Kong programs and the professor's working language when reliably known. Optimize for clarity and naturalness, not flattery. Keep an English first contact roughly 150–250 words unless the user requests otherwise.

For other email types and timing rules, read [references/email-types.md](references/email-types.md).

## Batch and campaign workflow

For multiple targets, research and draft each email independently. Never create a mail-merge body with only names swapped. Prioritize by research fit and evidence quality, not institutional prestige alone.

When campaign organization is requested, read [references/campaign.md](references/campaign.md). Create or update campaign artifacts only when useful to the request, preserve existing user edits, and make status transitions explicit.

Before any authorized send action, show or reference the exact final draft(s), recipients, subject lines, and attachment state. Stop if an address is ambiguous, a required attachment is missing, or the draft contains unresolved factual placeholders.

## Output

For a single draft, return:

- subject;
- ready-to-send body;
- one-line evidence bridge;
- verified sources and any unresolved facts;
- suggested follow-up date when relevant.

For batch/campaign work, also return a compact priority summary and where the tracker/drafts were saved. Separate verified facts from strategic judgment. Do not expose the applicant's weaknesses in the email itself; discuss material risks privately with the user.

## Quality check

Before delivery, confirm:

- identity, dates, metrics, contribution claims, and paper status are consistent with the latest sources;
- the professor connection could not be reused unchanged for another recipient;
- the ask is clear and does not presume admission, funding, a position, or collaboration;
- no generic praise, fabricated familiarity, hidden placeholders, or unsupported recruiting claim remains;
- subject, recipient, links, attachments, and follow-up timing are internally consistent.
