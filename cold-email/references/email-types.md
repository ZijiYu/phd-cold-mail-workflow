# Email types, timing, and reply handling

Read only the section relevant to the requested message. Calibration examples for first contact and follow-up are in [examples.md](examples.md).

## First contact

Subject line, in order of precedence:

1. An official professor/lab instruction (some specify an exact subject or a form).
2. The user's saved subject-line preference in `.local.md`.
3. Default: cycle plus research hook, e.g. `Fall 2027 PhD inquiry: <specific topic in under 8 words>`. The topic should come from the evidence bridge, so the subject differs per professor.

Avoid subjects that carry no information (`Prospective PhD Student`, `Inquiry`, `Hello`).

Ask whether the professor expects to advise students in the relevant cycle. Do not ask for "admission" directly.

Send window: suggest a weekday morning in the recipient's time zone, avoiding the week before a major deadline they are likely busy with (their main conference, end of term). This is a suggestion to the user; do not schedule a send without authorization.

## No-response follow-up

- Check the date of the original email.
- Usually recommend one follow-up after 7-14 calendar days, adjusted for weekends, holidays, deadlines, and any user-specified timing. If an auto-reply gave a return date, follow up a few working days after it instead.
- Reply in the same thread so the original is visible; keep it shorter than the original.
- Add genuine value when it exists: a project update, a new result, a sharper question. Do not fabricate an update; a two-sentence polite reminder is fine.
- After a second unanswered message, stop unless the professor invited further contact or there is a material update (e.g. a paper acceptance) close to the deadline.

## After the application is submitted

For high-fit professors in committee-admission programs, a short note after submitting can help the application get read: the program name, that the application is in, and one line on the research connection. Do not send this to professors who did not reply to two earlier emails.

## Handling replies

When the user reports or forwards a reply, classify it, update the tracker (see campaign.md), and draft the response. Typical cases:

| Reply | Tracker status | What to draft or do |
|---|---|---|
| Interested, offers a call | `meeting_scheduled` once a time is set | A brief reply proposing times in the professor's time zone; then a **meeting brief** (below) |
| "Apply and mention my name" | `apply_and_mention` | A two-line thank-you confirming the program; add a note to the program record so the user names the professor in the application |
| "Not taking students this cycle" | `closed` (reason: not recruiting) | A short gracious thanks; optionally ask whether they would suggest a colleague working on related problems - only if the reply leaves room for it |
| Redirects to a colleague or a co-advisor | `redirected` | Thank the professor; create a new target for the colleague and research them from scratch (do not reuse the original bridge) |
| Asks for materials or a task | `replied` | Check exactly what is requested and the deadline; draft the cover note; never send unrequested extra material |
| Out-of-office auto-reply | stays `sent`; `follow_up_due` moved | No reply; shift the follow-up to after the stated return date |
| Bounce | `bounced` | Re-verify the address from an official page before any retry |

### Meeting brief

Before a call with a professor, prepare a one-page brief for the user (not for sending):

- the professor's last three relevant papers, one line each, and which one the email cited;
- the applicant's 2-minute project explanation, plus a 30-second version;
- three questions to ask (group direction, how students choose projects, advising style, funding and timeline only if appropriate);
- likely questions the professor may ask, with honest short answers drawn from the profile;
- anything in the applicant's materials that might come up and how to address it.

## Interview or meeting thank-you

- Send promptly, normally within 24 hours.
- Refer to one real discussion point and one concrete takeaway.
- Reiterate interest without treating the conversation as a commitment.

## Reference reminder

- State the program, exact deadline with timezone when known, and submission mechanism.
- Be appreciative and easy to act on. Offer the latest CV/materials and resend the submission link only if appropriate.
- Avoid urgency language unless the deadline is genuinely close.

## Admission or funding inquiry

- Express gratitude and ask one or two precise questions about funding, timeline, start date, rotation, or decision logistics.
- Do not frame ordinary clarification as negotiation. For an actual competing offer or deadline, state the verified facts neutrally, using `current_standing` in the profile.

## Rejection follow-up

- Acknowledge the decision without arguing.
- Ask about future research opportunities only when there is a concrete basis, such as a project opening, later cycle, or invited continued contact.
- Keep the note brief and do not request admissions reconsideration unless the institution provides an appeal route.
