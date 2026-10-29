---
name: cold-email
description: End-to-end PhD outreach (套磁) workflow - shortlist schools and programs (选校), find and rank potential advisors (找导师/选导师), then research, draft, check, and track personalized professor emails, follow-ups, reply handling, and thank-you notes. Use for a single email, batch drafting, advisor discovery, or a multi-professor campaign; do not use for generic job-sales outreach.
---

# Academic Outreach / 套磁

Produce concise, evidence-based outreach that connects the applicant's verified work to a professor's current research. The full pipeline has five stages; enter at whichever stage the request starts from.

```text
0. Profile    -> 1. Discover          -> 2. Verify     -> 3. Bridge + draft -> 4. Send, track, reply
   .local.md     programs + advisors     one target       per target           campaign files
```

| Request looks like | Start at | Read |
|---|---|---|
| "Which schools / professors should I contact?" | Stage 1 | [references/discovery.md](references/discovery.md) |
| One named professor | Stage 2 (single draft) | this file, [references/examples.md](references/examples.md) |
| A list or table of professors | Stage 2 (batch) | this file, examples |
| Organize, track, prioritize, follow up, "a professor replied" | Stage 4 (campaign) | [references/campaign.md](references/campaign.md), [references/email-types.md](references/email-types.md) |

Infer the smallest suitable mode. Do not ask a generic personalization question; ask only when research cannot resolve the answer or a subjective choice would materially change the result.

Never send, schedule, or otherwise contact recipients without the user's explicit authorization covering the exact recipient(s) and approved draft(s). A batch authorization may cover a clearly identified set. Drafting, saving mailbox drafts, and local tracking do not imply sending permission.

## Stage 0 - Applicant profile

Use information in this order, with newer direct user statements overriding older sources:

1. The user's current instructions and corrections.
2. A CV, target list, paper, or other material supplied in the current request.
3. The project-root `.local.md` applicant profile (schema: [references/profile-template.md](references/profile-template.md)).
4. Previously saved campaign data.

If `.local.md` is missing or lacks a field the request needs, ask for a CV or just the few missing facts; offer to save them in the template format. Do not force the user through a separate setup step when a small input suffices.

Do not invent research ownership, metrics, publication status, admissions plans, or professor recruiting status. Keep personal contribution separate from team results, exactly as the profile records them. Mark unverified or time-sensitive facts as unknown.

The profile's `current_standing` (existing offers, interviews, constraints) changes strategy: with an offer in hand, discovery should favor targets that are clearly better fits or better outcomes than that offer, and the user may want fewer, higher-effort emails.

## Stage 1 - Discover programs and advisors

When the user has no target list, or asks which schools or professors to contact, follow [references/discovery.md](references/discovery.md). It produces two tables - programs (选校) and advisor candidates (选导师) - with a transparent fit score and separated recruiting evidence. Present the shortlist for the user's review before drafting; the user decides who is contacted.

## Stage 2 - Verify one target

For each target, verify from primary or authoritative sources where possible:

- current institution, department, title, and official contact channel; whether they can advise students in the program the applicant is applying to;
- recent work, preferring papers from the last ~24 months where the professor is last or corresponding author (their own direction, not a minor collaboration);
- recruiting evidence, kept in two buckets: **confirmed** (official page or public statement) and **signals** (see discovery.md) - never promote a signal to a confirmation;
- any required subject line, form, or instruction that supersedes the normal email format (some labs ask applicants not to email, or to use a form).

Prefer the professor/lab/university page and the publication's official page; use bibliographic indexes as supporting sources. Distinguish publication status from preprint status. Record source URLs and the date checked. Re-verify a target whose `checked_on` is more than 30 days old before sending.

## Stage 3 - Bridge and draft

### Evidence bridge

Before drafting, write this chain explicitly:

`applicant evidence -> professor work -> plausible shared question -> proportionate ask`

Select one applicant project and one professor paper/project. Make the bridge technical: a shared problem, a method that could transfer, an evaluation gap, or a limitation that motivates a question. Two tests:

- **Not reusable**: the connection could not be sent unchanged to another professor.
- **Not abstract-only**: it uses something from the body of the paper (a stated limitation, an ablation, a dataset choice, a failure case) rather than only the abstract. If you could only read the abstract, say so to the user rather than faking depth.

### Draft

Default first-contact structure (English, ~150-220 words):

1. Subject that names the research hook, not just "Prospective PhD student" (see email-types.md).
2. Greeting; one sentence with identity, application cycle, and research focus.
3. Two or three sentences of applicant evidence: problem, personal contribution, credible result.
4. One concrete connection to the professor's work. Add a forward-looking question only if it is non-trivial and the applicant could discuss it; otherwise state a scoped idea or omit it. A weak question is worse than none.
5. A clear ask: whether they expect to advise students in this cycle and, if appropriate, a brief call.
6. Short sign-off with website and CV link/attachment note.

For applicants without substantial research experience, lead with relevant preparation and a scoped learning goal rather than inflating project maturity.

Write in the user's requested language; otherwise English for international and Hong Kong programs, or the professor's working language when reliably known. Calibrate against [references/examples.md](references/examples.md) - match the strong examples, avoid the failure patterns, and avoid the phrase list in `scripts/check_draft.py`.

For follow-ups, replies, thank-you notes, and other message types, read [references/email-types.md](references/email-types.md).

## Stage 4 - Batch, campaign, replies

For multiple targets, research and draft each email independently; never mail-merge with names swapped. Prioritize by research fit and evidence quality, not prestige alone. Keep the story consistent across professors at the same institution - they talk to each other.

For tracking, follow-up scheduling, mailbox drafts, and reply handling, read [references/campaign.md](references/campaign.md). Preserve existing user edits and make status transitions explicit.

The user may also be running the companion dashboard (a separate `dashboard/` folder in the same GitHub repo, not part of this skill), which reads and writes the same `targets.csv`, `programs.csv`, and `drafts/`. Re-read those files before editing rather than relying on an earlier copy, and keep the draft file format so both stay compatible. When it is running, its REST API (`http://127.0.0.1:8765/api/docs`, token in `~/.phd-outreach-dashboard/api_token`) is an alternative to editing files directly.

Before any authorized send action, show the exact final draft(s), recipients, subject lines, and attachment state. Stop if an address is ambiguous, a required attachment is missing, or the draft contains unresolved placeholders.

## Output

For a single draft, return:

- subject and ready-to-send body;
- one-line evidence bridge;
- verified sources (with date checked) and any unresolved facts;
- recruiting evidence, labeled confirmed or signal;
- suggested send window and follow-up date.

For discovery, return the program and advisor shortlist with scores and the reasons behind them. For batch/campaign work, also return a compact priority summary and where files were saved. Separate verified facts from strategic judgment. Do not expose the applicant's weaknesses in the email itself; discuss material risks privately with the user.

## Quality check

Run the deterministic checks when a shell is available (the scripts live in this skill's directory; the paths below are the user's campaign files):

```bash
python scripts/check_draft.py outreach/<cycle>/drafts/*.md      # placeholders, length, subject, stock phrases
python scripts/check_tracker.py outreach/<cycle>/targets.csv    # statuses, dates, follow-ups due, duplicates
```

Then confirm by judgment:

- identity, dates, metrics, contribution claims, and paper status match the latest sources and the profile;
- the bridge passes both the not-reusable and not-abstract-only tests;
- the ask is clear and does not presume admission, funding, a position, or collaboration;
- no generic praise, fabricated familiarity, or unsupported recruiting claim remains;
- subject, recipient, links, attachments, and follow-up timing are internally consistent.
