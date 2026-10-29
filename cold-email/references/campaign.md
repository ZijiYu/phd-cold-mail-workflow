# Outreach campaign workflow

Use this reference when the user asks to organize, automate, batch, prioritize, track, or follow up with multiple professors, or when a reply comes in.

## Local structure

When persistent files would help, create them under a user-approved or clearly implied project location. Default to:

```text
outreach/<application-cycle>/
|-- programs.csv          # one row per program (选校), see discovery.md
|-- targets.csv           # one row per professor (选导师 + outreach state)
|-- drafts/
|   `-- <institution>--<professor>.md
|-- briefs/               # meeting briefs, see email-types.md
`-- notes.md
```

Do not overwrite an existing campaign. Inspect it, preserve user-authored fields, and update only the intended records. If an older tracker uses different column names, map them rather than rewriting the file.

## Tracker fields (`targets.csv`)

| Field | Meaning |
|---|---|
| `target_id` | Stable slug, e.g. `lakeview--dana-whitfield`; never a row number |
| `program_id` | Matching row in `programs.csv` (optional when no program table exists) |
| `professor`, `institution`, `department` | Current verified values |
| `email` | Official address, or blank if unverified |
| `homepage_url` | Official page |
| `research_anchor` | The one paper/project the email uses |
| `applicant_anchor` | The applicant project the email uses |
| `fit_rationale` | One-sentence evidence bridge |
| `fit_score` | Total from discovery.md, e.g. `8` |
| `fit_components` | e.g. `topic=3;contrib=2;bridge=2;signals=0;program=1` |
| `recruiting_confirmed` | `confirmed` with source, or `not confirmed` |
| `recruiting_signals` | Indirect signals with sources; never quoted in an email |
| `source_urls` | URLs supporting target facts, separated by spaces |
| `checked_on` | ISO date of last verification |
| `draft_path` | Local draft file |
| `variant` | Optional label for the subject/bridge style, used for the review below |
| `status` | One of the values below |
| `sent_at` | ISO date of the first send, only after a confirmed send |
| `follow_up_count` | Number of follow-ups sent (0, 1, 2) |
| `last_contact_at` | ISO date of the latest message sent by the applicant |
| `follow_up_due` | Planned ISO date; a reminder, not proof of scheduling |
| `response_summary` | One line summarizing the latest reply |
| `close_reason` | Required when `status=closed` |
| `next_action` | Concrete next step; required when `status=blocked` |

### Status values

```text
researching -> drafted -> approved -> sent -> replied -> meeting_scheduled
                                        |         |---> apply_and_mention
                                        |         |---> redirected
                                        |         `---> closed
                                        |---> bounced
                                        `---> closed (no response after follow-ups)
blocked   (any time a required fact, address, or attachment is missing; put the reason in next_action)
```

Rules:

- A follow-up is not a status. Use `follow_up_count`, `last_contact_at`, and `follow_up_due`; the record stays `sent` until something comes back.
- Never mark `sent` from an intent to send; require a tool confirmation or the user's report. Record send failures in `notes.md`, not as `sent`.
- An auto-reply leaves the status at `sent` and moves `follow_up_due`.
- A `redirected` record spawns a new target for the colleague, researched from scratch.
- `scripts/check_tracker.py` validates these values and the required-field rules.

## Draft file

Each draft contains:

- target and verified email address;
- subject and body;
- evidence bridge;
- source URLs and date checked;
- unresolved facts/placeholders;
- revision status and approval note;
- attachment checklist;
- suggested send window and follow-up date rationale.

Put the subject on a line starting `Subject:`, the body directly below it, and end the body with a `---` line or a `## ` heading before the notes, so `scripts/check_draft.py` checks only the email itself.

## Prioritization

Rank contacts using transparent evidence:

1. research fit and specificity of the bridge (the discovery score components);
2. evidence that the applicant can contribute;
3. confirmed recruiting first, then signals;
4. program deadlines - targets whose deadline is close move up;
5. confidence in contact information.

Institutional prestige can be shown separately but should not dominate the order.

## Same-institution coordination

Faculty in the same department talk to each other and sometimes forward emails.

- Contact at most `max_contacts` professors per program (usually 1-3).
- Each email must have its own bridge; never imply to any of them that they are the only professor contacted.
- Keep the applicant's research story consistent across them.
- Space sends to the same department by a few days, highest fit first, unless deadlines force otherwise.
- For two professors who co-advise a group, prefer one email to the better-fit professor and mention the shared work.

## Mailbox integration

When a mail connector (Gmail, Outlook) is available in the session:

- Creating a **draft** in the user's mailbox is allowed after the user approves the content; it saves copy-paste errors. Record the draft link or id in the draft file.
- Searching the mailbox for replies from tracked addresses after `sent_at` is allowed when the user asks for a campaign update. Summarize each reply and propose the status change; ask the user when a reply's meaning is ambiguous.
- Sending still requires explicit authorization for the exact recipients and drafts.

The companion dashboard (the `dashboard/` folder next to this skill in its GitHub repo) implements this boundary for Gmail with the user's own OAuth client: it proposes status changes from sends, replies, auto-replies, and bounces for the user to confirm, and saves approved drafts into Gmail drafts without sending. If the user has it connected, their tracker may already reflect Gmail activity.

Without a connector or the dashboard, ask the user to report sends and replies, and update the tracker from that.

## Safe automation boundary

Automation may research, normalize records, score fit, draft messages, create mailbox drafts, check placeholders, and calculate follow-up dates. It may not silently send, schedule, or repeatedly retry contact.

Before sending, obtain explicit authorization that identifies the approved recipient(s) and draft(s). Reconfirm if a recipient, subject, body, attachment, or scheduled time changes materially after approval. Do not retry a failed external action without inspecting the cause and staying within the user's authorization.

## Campaign review output

Run `python scripts/check_tracker.py outreach/<cycle>/targets.csv` first, then summarize:

- counts by status;
- follow-ups due today or overdue, with original send dates;
- replies needing the user's judgment and the proposed response;
- top-priority targets not yet contacted, and why;
- blocked records and missing facts; records whose verification is stale;
- drafts awaiting approval;
- when at least ~15 emails have been sent, reply rates by `variant`, presented as a weak signal given the small sample.
