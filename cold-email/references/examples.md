# Calibration examples

All people, institutions, papers, and numbers below are **fictional**. Use these to calibrate tone, length, and specificity - never reuse their wording, topics, or structure verbatim.

## 1. Strong first contact (applicant with a research result)

```text
Subject: Fall 2027 PhD inquiry: test-time adaptation that knows when to abstain

Dear Professor Whitfield,

I am a second-year MS student in Computer Science at Northfield University,
applying to PhD programs for Fall 2027. I work on making medical image
segmentation reliable under scanner and site shift.

In my thesis project I built a test-time adaptation method for cross-site MRI
segmentation that updates only normalization statistics and stops adapting
when prediction entropy rises across consecutive batches. I designed the
stopping rule and ran all experiments; on a held-out site it raised Dice from
0.71 to 0.78 over the unadapted model. The paper is under review at MICCAI.

Your recent paper on selective prediction under shift shows that
confidence-based abstention breaks down once a model is adapted, because the
adapted model becomes overconfident (Section 5). I hit the same effect: my
stopping rule fires late on the hardest site. I would like to study whether
an abstention signal estimated before adaptation can decide both when to
adapt and when to defer to a clinician.

Do you expect to advise new PhD students in the Fall 2027 cycle? If so, I
would welcome a short conversation. My CV is attached, and my papers are at
linchen.github.io.

Best regards,
Lin Chen
```

Why it works:

- The subject names the research hook, so it is distinguishable in an inbox.
- Personal contribution ("I designed... and ran...") is separated from the outcome, the metric has a baseline, and the paper status is exact.
- The connection cites something from the body of the professor's paper (Section 5), ties it to a problem the applicant actually observed, and proposes a question the applicant could discuss on a call.
- The ask is about advising in a specific cycle, not about admission.
- ~200 words, no adjectives about the professor.

## 2. The same email, done badly

```text
Subject: Prospective PhD Student

Dear Professor,

I hope this email finds you well. My name is Lin Chen and I am deeply
passionate about machine learning. I have carefully read your outstanding
work and was deeply impressed by your groundbreaking contributions to
trustworthy AI, which align perfectly with my research interests.

During my master's studies, our lab developed a state-of-the-art domain
adaptation framework that achieved significant improvements on several
benchmarks. I am confident that my skills would make me a great fit for
your lab.

I would be grateful if you could consider me for admission to your group.
I look forward to hearing from you.
```

Failure patterns, each of which `scripts/check_draft.py` or the quality check should catch:

| Pattern | Where |
|---|---|
| Generic subject with no cycle or topic | Subject |
| No name in the greeting | "Dear Professor," |
| Stock opener and praise vocabulary | "hope this email finds you well", "deeply impressed", "groundbreaking", "align perfectly" |
| Claims to have read the work but names no paper | Paragraph 1 |
| Team result presented without the applicant's role | "our lab developed" |
| Unverifiable superlatives instead of numbers | "state-of-the-art", "significant improvements" |
| Self-assessment instead of evidence | "great fit for your lab" |
| Asks for admission rather than advising availability | Last paragraph |
| Reusable for any professor in the field | Whole email |

## 3. Strong first contact (early-stage applicant)

```text
Subject: Fall 2027 PhD inquiry: data selection for low-resource speech recognition

Dear Professor Okafor,

I am a final-year undergraduate in Electrical Engineering at Riverside
Institute of Technology, applying to PhD programs for Fall 2027.

I have not yet published, but over the past year I have been working toward
speech recognition for low-resource languages. For my capstone I fine-tuned a
pretrained ASR model on 12 hours of Yoruba speech and found that removing the
noisiest 20% of clips by a simple alignment score lowered word error rate from
41% to 36%. I wrote the filtering and evaluation code myself.

Your group's paper on uncertainty-based data selection for ASR reports that
selection helps less as the labeled pool grows. I would like to understand
whether that holds when the pool is tiny and very noisy, which is the regime
I have been working in.

Will you be taking new PhD students for Fall 2027? I would be glad to share
more about my project. My CV is attached.

Best regards,
Amara Nwosu
```

Why it works: it states the experience level plainly instead of inflating it, offers a small but real result with the applicant's own role, and the question follows directly from that result.

## 4. Strong no-response follow-up

```text
Subject: Re: Fall 2027 PhD inquiry: test-time adaptation that knows when to abstain

Dear Professor Whitfield,

I am following up on my email from October 6 about PhD advising for Fall
2027. Since then I tested pre-adaptation abstention on two more sites: it
flags 80% of the cases where adaptation later hurts Dice, at a 15% deferral
rate. A one-page summary is at linchen.github.io/tta-abstain.

If you are considering new students this cycle, I would be glad to talk.

Best regards,
Lin Chen
```

Why it works: shorter than the original, adds a real update, and does not apologize for writing again. If there is no genuine update, a two-sentence polite reminder is better than a manufactured one.
