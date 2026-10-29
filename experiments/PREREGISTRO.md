# Pre-registration — LoopShield (Future Health Digital Innovation Challenge, Challenge 05)

Written 2026-10-29, before any experiment was run. Nothing below is changed after results are seen; later analyses go in
`experiments/LOG.md` marked *post hoc*.

## Questions

1. **E-SIM (care loop).** In a simulated cohort of positive faecal immunochemical tests (FIT+), does a closed-loop tracker
   with outreach and escalation (LoopShield) increase colonoscopy completion within 12 months, and reduce silent loss to
   follow-up, compared with usual care and with a reminders-only tracker?
2. **E-PHI (privacy, own technology).** When LoopShield sends a case note to an external language model to draft patient
   messages, how much protected health information (PHI) reaches the model with Project NAVAJO v2 compared with
   Microsoft Presidio (the professional control) and with no masking?
3. **E-ENG (software safety).** Does the case engine keep its safety invariants under random event sequences?

## E-SIM design

- Pathway: FIT+ → diagnostic colonoscopy. Day 0 = result issued.
- Usual care (A0): each patient completes colonoscopy at a time drawn from a log-normal (σ = 0.8) with the scenario median,
  with probability `p_ever`; `p_ever` is set so that completion by day 365 equals the scenario value. Scenarios taken from
  Chubak et al. 2016 (doi:10.1158/1055-9965.EPI-15-0470), the extremes across four US systems:
  - S-low: 58.1 % by 12 months, median 174 days;
  - S-high: 83.8 % by 12 months, median 41 days.
- Reminders-only tracker (A1): EHR reminders to the clinician. Effect taken from the mFOCUS trial (Atlas et al. 2023,
  doi:10.1001/jama.2023.18755): completion within 120 days 22.7 % vs 22.9 % usual care, i.e. Δ = −0.2 points.
- LoopShield (A2): tracker + patient outreach in the patient's language + navigation/escalation. Effect from the same trial,
  outreach + navigation arm: Δ = +8.5 points [95 % CI 4.8–12.0] completion within 120 days among overdue results.
- Mechanism for A1/A2: a case is *overdue* when not completed by the SLA (default 60 days, configurable, an assumption).
  Among overdue cases that would not complete within the next 120 days under usual care, a fraction
  c = Δ / (1 − 0.229) is converted to completion at a uniform time in the next 120 days. Δ is drawn per replicate from
  N(mean, sd) with sd = (12.0 − 4.8)/3.92 = 1.84 points (A1 uses the same sd around −0.2). Negative c is applied as
  conversion of would-be completers into non-completers.
- The simulated events drive the real LoopShield engine (`loopshield.engine`), so visibility metrics are measured on the
  software, not assumed.
- 10 replicates (seeds 0–9) × 10,000 patients per arm and scenario. Report mean, SD and 2.5–97.5 percentiles over
  replicates.
- Outcomes:
  - **Primary O1:** % colonoscopy completed by day 365.
  - O2: % not completed by day 300 (≥ 10 months, the delay group with higher cancer risk in Corley et al. 2017,
    doi:10.1001/jama.2017.3634).
  - O3: expected colorectal cancers per 1,000 FIT+ patients, applying Corley's associational rates by delay bin
    (8–30 d: 30; 2 m: 28; 3 m: 31; 4–6 m: 31; 7–9 m: 43; 10–12 m: 49; > 12 m or never: 76). Associational, not causal;
    reported as illustration only.
  - O4: % of cases unresolved at day 365 that no accountable owner has been alerted about (*silent loss*). For usual care
    this is assumed to be all unresolved cases (no tracking system); for A1/A2 it is measured on the engine.
  - O5: median days from the SLA breach to the first escalation recorded by the engine.
- Decision rule: A2 is reported as beneficial for O1 if its 2.5th percentile over replicates of (A2 − A0) is above 0 in both
  scenarios. The size of the benefit is an input from one US trial, so the simulation cannot confirm it; it shows what the
  trial effect would mean for the pathway and how much depends on it (sensitivity: Δ at 0, 4.8, 8.5, 12.0 points).

## E-PHI design

- Data: Gretel `gretel-pii-masking-en-v1` (Apache-2.0), **test** split, documents whose `domain` contains "health"
  (all of them, fixed before scoring). Gold spans = every exact occurrence of each listed entity string.
- Systems (frozen, no tuning on this data):
  - Raw note (what is sent today without protection);
  - Presidio Analyzer, default English recognisers with spaCy `en_core_web_lg` (professional control);
  - NAVAJO v1 (navajo-egp 0.1 regex) and **NAVAJO v2** (clinical layer, frozen at Agnuxo1/edge-privacy-gateway commit
    1bea827, lexicon built only from Nemotron-PII train);
  - Hybrid v2 + Presidio (union of spans).
- Gretel health documents were partly inspected (200 documents) in that repository's exploratory pilot; no NAVAJO rule is
  changed here. This is declared, and the test is therefore not wholly unseen for that project.
- Metrics: **primary** PHI character exposure E = PHI characters left visible / PHI characters; documents with at least
  one PHI entity fully visible; precision of masked characters; clinical measurements left intact; ms per document.
- Uncertainty: three disjoint partitions by uid hash (mean ± SD) and paired bootstrap 95 % CI over documents
  (1,000 resamples, seeds 0, 1, 2) for v2 − Presidio and hybrid − Presidio on E.
- H1 (own technology): E(v2) < E(Presidio), CI of the paired difference below 0. If rejected, the hybrid is tested and
  reported; the system shipped is the one with the lowest E whose precision stays ≥ 0.8, and its NAVAJO contribution is
  measured by ablation (hybrid − Presidio).

## E-ENG design

- 100,000 random event sequences (seed 0) of length 1–30 drawn from all event types, including invalid ones.
- Invariants: (i) no case closes without closure evidence or a named human decision; (ii) every non-terminal case has an
  accountable owner; (iii) the audit chain verifies; (iv) an urgent case is escalated to a clinician at once.
- Pass = zero violations.

## What will not be claimed

No clinical effectiveness, no deployment, no regulatory status, no Arabic de-identification performance (Arabic is limited
to patient message templates pending native-speaker and clinical review).
