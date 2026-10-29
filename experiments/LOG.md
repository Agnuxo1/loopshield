# Experiment log

Every run is listed, including negative and inconclusive ones. Machine-readable copy: `experiments/log.csv`.

## E-ENG-01 — engine invariants under random events (2026-10-29)

- Hypothesis: the engine never closes a case without evidence or a named clinician, never leaves an open case without an
  owner, never skips the urgent escalation, and its audit chain verifies.
- Config: `python sim/fuzz.py --n 100000 --seed 0` (100,000 sequences, 1,551,395 events, 2 pathways).
- Result: **0 violations**. 273,116 events accepted, 1,278,279 rejected as not allowed in the current state.
- Limitation found: random sequences reach the full evidence closure rarely (2 of 100,000 cases; 937 closed by clinician
  decision). The evidence-closure path is covered by unit tests (`tests/test_loopshield.py`), not by the fuzzer.
- Decision: pass. Its output file was later overwritten by E-ENG-02/03 and was not kept; the counts above are copied
  from the console output of that run.

## E-SIM-01 — positive-FIT cohort, pre-registered (2026-10-29)

- Config: `python sim/simulate.py --n 10000 --seeds 10` (10 replicates × 10,000 patients per arm and scenario, Windows,
  Python 3.13.7, NumPy 2.2.6, 30 s). Its output files were overwritten by later runs; O1–O4 below are identical in the
  final run (`results/sim/`), which is the one reported.
- Primary O1 (completion by day 365), difference vs usual care, mean [2.5–97.5 percentile over replicates]:
  - LoopShield (outreach + escalation, trial effect drawn from mFOCUS): **S-low +4.76 [+1.51, +6.38] points,
    S-high +1.97 [+1.12, +2.42]**. Pre-registered rule met (2.5th percentile above 0 in both scenarios).
  - Reminders-only tracker: S-low −1.18 [−5.18, +2.19], S-high −0.99 [−4.42, +0.14]: no benefit, as in the trial.
- Sensitivity (fixed Δ): 0 → no change by construction; 4.8 → +2.6 / +1.1; 8.5 → +4.4 / +1.8; 12.0 → +6.7 / +2.5 points
  (S-low / S-high). The benefit scales with the trial input; the simulation does not establish it.
- O4 silent loss: 0 % of unresolved cases at day 365 had no escalation in both tracker arms (measured on the engine),
  against an assumed 100 % without a tracking system. O5: median 0 days from the 60-day SLA to an escalation already on
  record (step-level escalations fire before the end-to-end SLA).
- Negative/caveat findings, kept:
  - Reminders-only arm comes out slightly below usual care on average (−1.0 to −1.2 points) because the trial's
    −0.2-point estimate is rescaled by a denominator (22.9 %) that differs from the simulated pool; the interval
    includes 0. Read as "no effect", not as harm.
  - Escalation burden: 11.0–11.2 escalations per case in S-low, 2.4–2.5 in S-high. In S-low most of this comes from the
    assumption that each step's duration stretches in proportion to the patient's total delay, so every step overruns
    its SLA. Alert fatigue is a real deployment risk; the ladder and SLAs must be tuned with the programme.
  - O3 uses associational cancer rates by delay (Corley 2017); it is an illustration, not a causal estimate.
- Decision: report as pre-registered. Effect size is an external input from one US trial; local validation is required.

## E-PHI-01 — PHI reaching an external model, local smoke without Presidio (2026-10-29)

- Config: `python bench/phi_payload.py --parquet <Gretel test parquet sha256 c89a6bff…> --no-presidio`, Windows.
- 251 health documents (domains `healthcare`, `healthcare-administration`), 10,239 PHI characters.
- PHI characters left visible E: raw 100 %, NAVAJO v1 28.3 %, **NAVAJO v2 12.9 %** (partitions 12.9 ± 1.5 %);
  precision v2 0.884; clinical measurements kept 100 % (33). Gateway refusal rate with v2: 0.4 % of notes.
- Status: smoke only, control missing. Full run with Presidio: E-PHI-02 on server-ia (ticket 191).

## E-PHI-02 — full pre-registered run with Presidio (2026-10-29)

- Config: `bench/phi_payload.py`, Windows venv on D: (presidio-analyzer 2.2.360, spaCy 3.8.7, en_core_web_lg 3.8.0,
  NumPy 2.2.6, pyarrow 21.0.0; `results/phi/pip_freeze_windows.txt`); data sha256 c89a6bff… (`results/phi/data_sha256.txt`).
  Ran on the PC because the server CPU lane was busy (13 s); Linux replication submitted to server-ia (ticket 192).
- PHI characters visible E: raw 100 %; Presidio 22.8 %; NAVAJO v1 28.3 %; **NAVAJO v2 12.9 %**; **v2 + Presidio 4.1 %**.
- Paired bootstrap v2 − Presidio: −9.9 points, CI [−13.7, −6.5] (seed 0), [−13.4, −6.7] (1), [−13.3, −6.5] (2).
  Hybrid − Presidio: −18.8, CI [−21.3, −16.3] / [−21.0, −16.5] / [−21.2, −16.4].
- Precision: v2 0.884, Presidio 0.823, hybrid 0.831. Clinical values kept: v2 100 %, Presidio and hybrid 90.9 % (n = 33,
  small). Notes with ≥ 1 PHI entity fully visible: v2 21.9 %, Presidio 49.8 %, hybrid 6.4 %.
- Decision: H1 supported. Default mode = v2 (no model, 0.3 ms); maximum mode = v2 + Presidio (lowest exposure, precision
  ≥ 0.8, the pre-registered selection rule). NAVAJO contribution inside the hybrid (hybrid − Presidio) = −18.8 points.
- Caveat: the v2 project's exploratory pilot had inspected 200 Gretel health documents; no rule was changed here.

## E-SIM-02 — re-run after an engine fix (2026-10-29, post hoc correction, same pre-registered design)

- Change: the engine now refuses events whose time is earlier than its clock. This exposed a bug in `run_engine`:
  closure events up to day 367 were fed before measuring "at day 365". Fixed by ignoring events after day 365.
- Effect: only `unresolved_365` changed (S-low A1 43.13 → 43.24 %, A2 37.19 → 37.30 %; S-high A1 17.108 → 17.110 %,
  A2 14.158 → 14.159 %). O1–O5, escalations and all differences are identical. The fuzzer (E-ENG-01) was re-run with
  in-order times and gave identical counts and 0 violations. Reported tables are from this run.

## Codex audit round 1 (2026-10-29): NO APROBADO — fixes applied

Findings and actions: UAE ambulance number is 998, not 999 (fixed in both languages); mammogram cases received
colonoscopy wording (messages are now per pathway, tested in both languages); README promised that identifiers never
leave the hospital, contradicting E-PHI (reworded with measured residual exposure); audit `verify()` missed a removed
last entry (now checks the head and accepts an external anchor); reply codes were promised but not processed (new
`patient_reply` event); O5 did not measure what it said (E-SIM-03); two latency figures did not match the results file
(fixed: Presidio 15.4 ms, hybrid 13.8 ms); FHIR import and messaging channels described as available (now "future");
fuzzer checked invariants only every 1,000 cases and urgent escalation loosely (E-ENG-02); demo count 301 = 300 + 1
urgent; full T&C saved as `evidencias/tnc.txt`.

## E-ENG-02 — stricter fuzzing (2026-10-29)

- Config: `python sim/fuzz.py --n 100000 --seed 0` (20 cases per engine so that clocks stay within realistic horizons),
  `patient_reply` added to the random events; case invariants after every event; audit chain per engine.
- New invariants: urgent cases escalated to the clinical lead at the exact time they are flagged and never below it
  afterwards; every call-back or language request alerts a navigator.
- Result: 1,544,139 events, 302,266 accepted, 1,241,873 rejected; 42,585 urgent cases, 23,133 call-back requests;
  **0 violations**. Evidence closure reached 3 times (unit tests cover it). Its output file was overwritten by E-ENG-03
  and not kept; the counts above are from the console output of that run.
- Note: with 1,000 cases per engine the accumulated clock kept abandoned cases receiving 30-day reminders for
  simulated years and the run became very slow; the per-engine size was reduced, which does not change what is checked.

## E-SIM-03 — O5 corrected and escalation ladder that does not run out (2026-10-29, post hoc)

- O5 as pre-registered (`O5_median_days_sla_to_escalation`) took the first escalation of any step and truncated at 0,
  so its value 0 said nothing about oversight after the 60-day SLA. Added `O5b`: days from day 60 to the first
  escalation recorded on or after day 60, its 90th percentile, and the share of late, still-open cases with no
  escalation after day 60.
- With the v0.1 engine: share of late cases with no alert after day 60 was first computed over *all* late cases
  (S-low 15.3 % / 13.1 %, S-high 33.4 % / 27.6 %, A1 / A2). Codex round 2 found the denominator wrong (the numerator
  counts only still-open cases); corrected values in E-SIM-04. The 3-level ladder was used up before day 60.
- Change (hypothesis: continued reminders close that gap): after the ladder, remind the clinical lead every 30 days
  while the step is stuck (`repeat_after_ladder_days`).
- Result (`results/sim/`): no-alert share **0 %** in all tracker arms; median days from day 60 to next alert
  S-low 4.1 (A1) / 4.6 (A2), S-high 6.8 / 6.9; 90th percentile 23.9–28.5. Cost: escalations per case rise to
  S-low 15.2 / 14.4 and S-high 4.2 / 4.0. O1–O4 unchanged (completion times do not depend on alerts in this model).

## Codex audit round 2 (2026-10-29): NO APROBADO — fixes applied

All 11 round-1 findings confirmed fixed. New: FHIR exported engine alerts as sent Communications (now `preparation`,
no `sent`; docs say alerts are recorded, delivery not measured); O5b denominator (E-SIM-04); reply "1" to the first
message did not record acknowledgement in `ISSUED` (now ISSUED → NOTIFIED → ACKNOWLEDGED, tested; ignored in later
states); log entries pointed to overwritten files (fixed above); T&C summary for Fran missed the perpetual sublicensable
marketing licence and the 10-year image/voice release (added).

## E-SIM-04 — O5b with the correct denominator (2026-10-29)

- `sim/simulate.py --ladder-only --out results/sim_v01_ladder_exhausts` (v0.1 behaviour, 32.9 s) and
  `sim/simulate.py --out results/sim` (current engine, 42.7 s).
- Late, still-open cases with no alert after day 60: **v0.1 S-low 33.0 % (A1) / 33.0 % (A2), S-high 82.9 % / 82.9 %;
  current 0 %** in all tracker arms. Median days from day 60 to next alert: v0.1 3.4 / 3.4 and 5.5 / 5.9 (among cases
  that got one); current 4.1 / 4.6 and 6.8 / 6.9. Escalations per case: v0.1 11.2 / 11.0 and 2.4 / 2.5; current
  15.2 / 14.4 and 4.2 / 4.0. O1–O4 identical in both runs and to E-SIM-01.

## E-ENG-03 — fuzzing after the reply change (2026-10-29)

- Same config as E-ENG-02; `results/fuzz.json`. 1,544,139 events, 302,630 accepted, 1,241,509 rejected,
  42,585 urgent cases, 23,133 call-back requests, **0 violations**; evidence closure 3, decision closure 897.

## E-PHI-03 — Linux replication on server-ia (2026-10-29)

- server-ia CPU lane, job 8a8d1b5fa721403f (ticket 192), Debian, Python 3.13.5, same pinned packages
  (presidio-analyzer 2.2.360, spaCy 3.8.7, en_core_web_lg 3.8.0, NumPy 2.2.6, pyarrow 21.0.0), same data file.
- Every exposure, precision, partition and bootstrap value is **identical** to E-PHI-02; only latency differs
  (Linux: v2 0.25 ms, Presidio 9.1 ms, hybrid 8.1 ms per note). Output `results/phi_linux/phi_results.json`.
- GitHub Actions CI (Ubuntu, Python 3.12) on the public repo: 21 tests, demo, fuzz 5,000, simulation 2,000 × 3: all pass.
