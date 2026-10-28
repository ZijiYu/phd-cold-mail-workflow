# Outreach campaign workflow

Use this reference when the user asks to organize, automate, batch, prioritize, track, or follow up with multiple professors.

## Recommended local structure

When persistent files would help, create them under a user-approved or clearly implied project location. Default to:

```text
outreach/<application-cycle>/
|-- targets.csv
|-- drafts/
|   `-- <institution>--<professor>.md
`-- notes.md
```

Do not overwrite an existing campaign. Inspect it, preserve user-authored fields, and update only the intended records.

## Tracker fields

Use CSV or a spreadsheet if the user prefers. Recommended fields:

| Field | Meaning |
|---|---|
| `target_id` | Stable slug, not a row number |
| `professor` | Current verified name |
| `institution` | Current verified institution |
| `department` | Department or program |
| `email` | Official address or blank if unverified |
| `homepage_url` | Official page |
| `research_anchor` | Specific recent paper/project |
| `applicant_anchor` | Applicant evidence used |
| `fit_rationale` | One-sentence evidence bridge |
| `fit_level` | High / medium / exploratory |
| `recruiting_status` | Confirmed / not confirmed / not recruiting, with source |
| `source_urls` | URLs supporting target facts |
| `checked_on` | ISO date of verification |
| `draft_path` | Local draft file |
| `status` | Controlled state below |
| `sent_at` | Timestamp only after confirmed send |
| `follow_up_due` | Planned date, not proof of scheduling |
| `response` | None / positive / neutral / negative / auto-reply |
| `next_action` | Concrete next step |

Controlled status values:

`researching -> ready_to_draft -> drafted -> user_approved -> sent -> follow_up_due -> replied -> closed`

Use `blocked` with a reason when a required fact, address, or attachment is missing. Never mark `sent` from an intent to send; require tool confirmation or the user's report.

## Draft file

Each draft should contain:

- target and verified email address;
- subject and body;
- evidence bridge;
- source URLs and date checked;
- unresolved facts/placeholders;
- revision status and approval note;
- attachment checklist;
- follow-up date rationale.

## Prioritization

Rank contacts using transparent evidence:

1. research fit and specificity of the bridge;
2. evidence that the applicant can contribute;
3. verified advising/recruiting relevance;
4. program and timing constraints;
5. confidence in contact information.

Institutional prestige can be shown separately but should not dominate the outreach order.

## Safe automation boundary

Automation may research, normalize records, score fit, draft messages, check placeholders, and calculate follow-up dates. It may not silently send, schedule, or repeatedly retry contact.

Before sending, obtain explicit authorization that identifies the approved recipient(s) and draft(s). Reconfirm if a recipient, subject, body, attachment, or scheduled time changes materially after approval. Record successful sends and failures separately; do not retry a failed external action without inspecting the cause and remaining within the user's authorization.

## Campaign review output

Summarize:

- counts by status;
- top-priority targets and why;
- blocked records and missing facts;
- drafts awaiting approval;
- follow-ups due, with original-send dates;
- responses requiring user judgment.
