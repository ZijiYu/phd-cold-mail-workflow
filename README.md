# PhD cold-mail workflow / 套磁工作流

Two independent parts, in two folders:

| Folder | What it is | How you use it |
|---|---|---|
| [`cold-email/`](cold-email/) | The agent skill: shortlist programs (选校), find and rank advisors (选导师), write evidence-based emails (套磁), track follow-ups and replies | Copy or symlink this folder into your agent's skills directory |
| [`dashboard/`](dashboard/) | A local web dashboard + REST API over the same campaign files, with Gmail reply sync and drafts | Run it from this repo; it does not need to live in a skills directory |

They share data, not code: the skill writes `outreach/<cycle>/targets.csv`, `programs.csv` and `drafts/`, and the dashboard reads and edits the same files. The dashboard keeps its own copy of the two check scripts, and a test fails if that copy drifts from the skill's.

```text
skill:      0. Profile -> 1. Discover -> 2. Verify -> 3. Bridge + draft -> 4. Send, track, reply
dashboard:                                             edit + check      Gmail sync, drafts, API
```

## Install the skill

```bash
# Claude Code / agents that read ~/.agents/skills
ln -s "$PWD/cold-email" ~/.agents/skills/cold-email
# or copy it
cp -r cold-email ~/.agents/skills/cold-email
```

The skill folder contains:

| Path | Purpose |
|---|---|
| `cold-email/SKILL.md` | Entry point: stages, rules, output, quality check |
| `cold-email/references/discovery.md` | Program table, advisor candidate sources, fit scoring, recruiting evidence |
| `cold-email/references/profile-template.md` | Schema for the applicant's `.local.md` |
| `cold-email/references/examples.md` | Fictional strong/weak emails for calibration |
| `cold-email/references/email-types.md` | Subjects, follow-ups, reply handling, meeting brief, other message types |
| `cold-email/references/campaign.md` | Tracker fields, status machine, same-school coordination, mailbox drafts |
| `cold-email/scripts/` | `check_draft.py`, `check_tracker.py` |
| `cold-email/agents/openai.yaml` | Interface metadata for agents that read it |

## Run the dashboard

```bash
dashboard/start.sh                    # ./outreach (created if missing)
dashboard/start.sh path/to/outreach   # your campaign folder
```

The first run creates `dashboard/.venv` and installs dependencies (Python 3.10+). Gmail setup and the API reference are in [dashboard/README.md](dashboard/README.md).

Personal data stays out of git: `.local.md`, `/outreach/` and dashboard tokens are ignored.

## Tests

```bash
python -m unittest discover cold-email/tests   # skill scripts, stdlib only
python -m unittest discover dashboard/tests    # dashboard (needs dashboard/requirements.txt)
```

Neither part sends email on its own: sending stays a manual action in your mail client.
