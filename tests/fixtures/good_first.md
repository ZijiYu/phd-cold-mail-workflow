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

---
## Evidence bridge
notes [Name] here should be ignored
