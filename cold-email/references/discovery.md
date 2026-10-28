# Discovery: programs (选校) and advisors (选导师)

Use this reference when the user has no target list yet, wants more targets, or asks which schools or professors to contact. The output is two reviewable tables, not emails. Drafting starts only after the user approves the shortlist.

```text
A. Research map  ->  B. Candidate long list  ->  C. Program table  ->  D. Score advisors  ->  E. Shortlist for review
```

## A. Research map

From the applicant profile (`.local.md`, CV, papers), write down:

- 3-5 specific sub-problems the applicant has worked on or wants to work on (not broad areas: "calibrated uncertainty for vision-language models", not "multimodal learning");
- the venues where that work appears or would appear;
- the methods the applicant can actually execute (the skills a lab would use them for);
- constraints: regions, cycle, number of applications, funding needs, and `current_standing` (existing offers or interviews).

With an existing offer, raise the bar: only targets that are a clearly better research fit or a better outcome than the offer are worth an email. Say this to the user rather than silently filtering.

## B. Candidate long list

Generate candidates from several independent sources, so the list is not just "famous labs":

1. **Citation graph.** Last/corresponding authors of papers the applicant builds on heavily, and authors who cite the applicant's work. Semantic Scholar or OpenAlex are useful when reachable; otherwise use web search and paper pages.
2. **Venue sweep.** Accepted papers from the last two years at the applicant's venues, filtered to the sub-problems in A; take faculty last authors.
3. **Area rankings as a directory, not a score.** For US CS, CSRankings filtered by area lists faculty who publish in that area. Use it to find people, not to rank fit.
4. **Warm network.** Collaborators, former students, and postdocs of the applicant's current advisors and recommenders. Note any real connection; never imply one that does not exist.
5. **New faculty.** Department "new faculty" announcements from the last 1-3 years. New assistant professors often build their groups quickly.
6. **Explicit openings.** Lab "prospective students" pages and public recruiting posts.

Aim for a long list of roughly 2-3x the number the user plans to contact. Deduplicate by person, not by name spelling.

## C. Program table (`programs.csv`)

Outreach timing and value depend on the program, so record programs separately from professors.

| Field | Meaning |
|---|---|
| `program_id` | Stable slug, e.g. `cmu-mld-phd` |
| `institution`, `department`, `degree` | Verified names |
| `admission_model` | `committee` / `advisor_driven` / `hybrid` / `unknown`, with source |
| `deadline`, `deadline_tz` | Verified application deadline |
| `can_name_faculty` | Whether the application asks for faculty of interest |
| `cross_dept_advising` | Whether faculty in other departments can advise this program's students |
| `fee_waiver`, `gre` | Only when verified for this cycle |
| `tier` | `reach` / `match` / `safety`, relative to this applicant, with a one-line reason |
| `max_contacts` | Planned number of professors to contact here (usually 1-3) |
| `source_urls`, `checked_on` | Evidence and ISO date |

Notes:

- In committee-admission programs, an email rarely decides admission, but a reply can still put a name on the application. In advisor-driven programs, outreach matters more. Verify the model per program; do not generalize by country or field.
- A professor's home department may differ from the program the applicant is applying to. Check that they can advise in that program before scoring them high.
- Keep the deadline in view: first contact is most useful roughly 4-10 weeks before it. After the deadline, a short "I have applied" note to a high-fit professor replaces cold outreach.

## D. Score advisors

Score each candidate with visible components. Show the components, not just the total, so the user can disagree with a specific judgment.

| Component | Points | Rubric |
|---|---|---|
| Topical fit | 0-3 | 3: their recent last-author work addresses the same sub-problem; 2: adjacent problem or shared method; 1: same broad area; 0: keyword overlap only |
| Contribution fit | 0-2 | 2: the applicant has a concrete result or skill their agenda would use; 1: plausible but generic; 0: none visible |
| Bridge specificity | 0-2 | 2: a specific paper and question can be named now; 1: a paper but no sharp question; 0: neither |
| Advising signals | 0-2 | From the signal list below; 0 if negative signals dominate |
| Program and contact fit | 0-1 | Can advise in the target program and has a verified contact channel |

Totals: 8-10 high, 5-7 medium, 0-4 exploratory. Prestige can appear as a separate column; it never enters the score.

### Recruiting evidence

Keep two separate fields:

- `recruiting_confirmed`: an official page, post, or direct statement for this cycle, with source. Otherwise `not confirmed`.
- `recruiting_signals`: indirect evidence, each item with a source. Positive signals include: assistant professor in years 1-4; a recent large grant naming new student positions; senior students graduating this year; an open-positions page updated recently. Negative signals include: sabbatical or industry leave, a move to another institution, emeritus status, an explicit "not taking students" statement (exclude the target).

Signals inform priority; they never become a claim in the email.

### Exclusions and flags

Exclude when the professor says not to email, is not taking students, or cannot advise in any program the applicant is applying to. Flag (do not silently drop) when contact information is unverified, the only relevant paper is old, or the applicant's evidence for this target is thin.

## E. Shortlist for review

Return:

1. the program table, grouped by tier, with deadlines;
2. the advisor table sorted by score, with the components, the proposed research anchor (one paper), the proposed applicant anchor (one project), recruiting evidence, and flags;
3. a short note on portfolio balance (tiers, regions, deadlines) and on any target the user should look at personally.

Ask the user to confirm, remove, or add targets. Approved rows become `targets.csv` records with status `researching` (see campaign.md).
