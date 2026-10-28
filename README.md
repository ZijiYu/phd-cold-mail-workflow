# PhD cold-mail workflow / 套磁工作流

An agent skill for the full PhD outreach pipeline: shortlist programs (选校), find and rank advisors (选导师), write evidence-based emails (套磁), and track follow-ups and replies.

```text
0. Profile    -> 1. Discover          -> 2. Verify     -> 3. Bridge + draft -> 4. Send, track, reply
   .local.md     programs + advisors     one target       per target           campaign files
```

## Files

| Path | Purpose |
|---|---|
| `SKILL.md` | Entry point: stages, rules, output, quality check |
| `references/discovery.md` | Program table, advisor candidate sources, fit scoring, recruiting evidence |
| `references/profile-template.md` | Schema for the applicant's `.local.md` |
| `references/examples.md` | Fictional strong/weak emails for calibration |
| `references/email-types.md` | Subjects, follow-ups, reply handling, meeting brief, other message types |
| `references/campaign.md` | Tracker fields, status machine, same-school coordination, mailbox drafts |
| `scripts/check_draft.py` | Placeholders, length, subject, greeting, stock phrases, admission asks |
| `scripts/check_tracker.py` | Status values, required fields, dates, duplicates, due follow-ups, contact limits |
| `agents/openai.yaml` | Interface metadata for agents that read it |
| `dashboard/` | Local dashboard + REST API over the same campaign files, with Gmail reply sync and drafts ([details](dashboard/README.md)) |

## Quick start

1. Copy the template in `references/profile-template.md` into `.local.md` at your project root and fill it in.
2. Ask the agent, for example: "Shortlist programs and advisors that fit my profile", or "Draft a first email to Prof. X at Y".
3. Check drafts and the tracker:

```bash
python scripts/check_draft.py outreach/fall-2027/drafts/*.md
python scripts/check_tracker.py outreach/fall-2027/targets.csv
```

## Dashboard

A local web dashboard shows schools and professors in a sidebar, the outreach pipeline, and each email draft. It can bind your Gmail (read replies, save drafts, never send) and exposes a REST API.

```bash
pip install -r dashboard/requirements.txt
python -m dashboard --data dashboard/sample/outreach --open   # fictional sample data
python -m dashboard --data outreach --open                    # your campaign
```

Setup for Gmail and the API reference are in [dashboard/README.md](dashboard/README.md).

## Tests

```bash
python -m unittest discover tests            # skill scripts, stdlib only
python -m unittest discover dashboard/tests  # dashboard API (needs dashboard/requirements.txt)
```

The skill never sends email on its own: sending requires explicit approval of the exact recipients and drafts.
