# LoopShield — technical documentation

Future Health Digital Innovation Challenge · Focus area Population Health · **Challenge 05: Closing the
Screening-to-Care Loop**. Prototype version 0.1, October 2026. Author: Francisco Angulo de Lafuente (individual entry).

## 1. Problem

An abnormal screening result helps only if it becomes a diagnosis and, when needed, treatment. Between the laboratory,
the screening programme, primary care and the specialist, results go unacknowledged, referrals do not become
appointments and nobody is clearly responsible for the next step. Published figures: 6.8–62 % of laboratory results
and 1–35.7 % of radiology results not followed up (systematic review, Callen et al. 2012); 18.1 % of critical imaging
alerts unacknowledged even inside an integrated electronic record (Singh et al. 2009); 58.1–83.8 % of patients with a
positive faecal test had colonoscopy within 12 months across four US systems (Chubak et al. 2016); colonoscopy after
10 months is associated with more and later-stage colorectal cancer (Corley et al. 2017). Sources: `docs/SOURCES.md`.

## 2. What LoopShield does

```
result issued ─► case opened with one accountable owner and a due time for the next step
                 │
                 ├─ every step done (notify, acknowledge, refer, accept, book, attend, result) moves the case on,
                 │   records who owns the next step and restarts its clock
                 ├─ step overdue ─► escalation ladder: owner → care navigator → clinical lead (every 7 days),
                 │   then a reminder to the clinical lead every 30 days while the step stays stuck
                 ├─ urgent flag  ─► clinical lead at once
                 ├─ patient outreach in the patient's language (English, Arabic), with reply codes the engine processes:
                 │   understanding or ask for a call
                 └─ closure only with evidence (report reference + next step) or a documented decision by a named
                     clinician (informed decline, unreachable after ≥ 3 attempts, care elsewhere confirmed …)

every change ─► hash-chained audit log      case ─► FHIR R4 Task / Communication / Provenance for the next provider
AI drafting  ─► NAVAJO privacy gateway: identifiers masked on the hospital machine, final check, answer restored locally
```

| Module | Purpose |
|---|---|
| `loopshield/engine.py` | case state machine, owners, due times, escalation timers, closure rules, audit chain, work-list board |
| `loopshield/pathways.py` | configurable pathways (positive FIT → colonoscopy; abnormal mammogram → diagnostic imaging) |
| `loopshield/messages.py` | deterministic patient messages, English and Arabic, urgent wording, reply codes |
| `loopshield/privacy.py` | NAVAJO v2 masking, hard-identifier guard that refuses to send, local restore |
| `loopshield/fhir.py` | FHIR R4 export for cross-provider hand-off |
| `demo/run_demo.py` | 300 synthetic cases + 1 urgent → `demo/out/dashboard.html` (board, worklist, case timeline, messages, masked prompt, FHIR) |
| `sim/simulate.py`, `sim/fuzz.py` | pre-registered simulation and engine fuzzing |
| `bench/phi_payload.py` | pre-registered PHI-exposure benchmark against Microsoft Presidio |

## 3. How it answers the six requirements of Challenge 05

1. **End-to-end case visibility.** Every actionable result is a case with a timeline from issue to documented closure;
   the board lists open, overdue, unassigned and urgent cases per owner.
2. **Clear ownership and timely progression.** Exactly one accountable role at every moment (checked as an invariant);
   per-step service levels; overdue cases escalate automatically; rejected referrals and missed appointments move the
   case back with a reason and a new owner, so they cannot disappear.
3. **Patient-centred communication.** Plain-language messages that say *screening result, not a diagnosis*, give one
   next action and ask the patient to confirm understanding or request a call; English and Arabic (Arabic pending
   native-speaker and clinical review); messages are specific to each pathway (positive FIT, abnormal mammogram); urgent
   wording points to same-day contact and the UAE ambulance number (998). Replies are events in the engine: 1 records
   notification and acknowledgement while the case is waiting for them (otherwise it is stored only); 2 (call me) and
   3 (another language) alert a care navigator at once.
4. **Cross-provider coordination.** FHIR R4 Task with owner, due date, business status and closure outputs;
   Communication resources for escalations; Provenance. Referral acceptance is a step of its own.
5. **Safe, human-governed escalation.** Urgent cases reach the clinical lead immediately; automatic closure is
   impossible: closing needs clinical evidence or a named clinician's documented decision, and "unreachable" needs at
   least three recorded attempts.
6. **Closure and patient-impact measures.** Engine-measured: time to each step, overdue and unresolved cases, silent
   loss, escalations per case, documented closure. Simulated: completion of the diagnostic test within 12 months
   (section 5).

## 4. Responsible AI, safety and data governance

- The core loop uses **no machine learning**: rules, timers and templates, fully auditable. AI is optional, for drafting
  messages or summaries, and only through the NAVAJO gateway.
- Two privacy modes: default NAVAJO v2 (no ML model, no extra dependency) and maximum NAVAJO v2 + Presidio
  (`privacy.presidio_detector()`), measured in section 5.
- Data minimisation: the prompt carries pathway, step, urgency and language only; free text is masked locally; a final
  guard refuses to send if an e-mail, Emirates ID pattern, phone number or long number is still visible; the
  placeholder mapping lives in memory for one request.
- Masking reduces exposure; it does not anonymise. Pseudonymised data remain personal data (GDPR, UAE PDPL and
  Abu Dhabi health data rules); an external model still needs a data-processing agreement or a local deployment.
- Tamper-evident audit: SHA-256 chain over every event; `verify()` detects edits, reordering and removed entries
  (including the last one); storing the head hash elsewhere (`verify(anchor=...)`) also detects a rewritten log.
- Human oversight: escalation targets are human roles; closure decisions are attributed to a named clinician.
- Not a medical device in this form; it does not make diagnostic or treatment decisions. Any deployment needs clinical
  safety assessment (e.g. DCB0129/0160-style hazard log) and local regulatory review.

## 5. Evidence (pre-registered in `experiments/PREREGISTRO.md`; full log in `experiments/LOG.md`)

- **Engine (E-ENG):** 100,000 random event sequences, 1.54 M events, case invariants checked after every event:
  0 violations. The evidence-closure path is reached rarely by random events and is covered by unit tests.
- **Simulated pathway (E-SIM):** 10 replicates × 10,000 positive-FIT patients, two calibration scenarios (Chubak 2016),
  intervention effect from the mFOCUS trial (Atlas et al. 2023). Completion by 12 months vs usual care:
  LoopShield **+4.8 points** [+1.5, +6.4] in a low-performing system and **+2.0** [+1.1, +2.4] in a high-performing
  one; reminders-only tracking ≈ 0 (as in the trial). Silent loss falls from all unresolved cases (assumed, no tracking)
  to 0 % (measured on the engine). The effect size is an input from one US trial: the simulation shows what that effect
  means for the pathway, it does not prove it. Escalation burden: about 14 escalations per case in the slow system
  and 4 in the fast one. A first version stopped alerting after the 3-level ladder (33 % of late open cases in the slow
  system and 83 % in the fast one got no alert after day 60); the current one reminds the clinical lead every 30 days
  (0 %; median 4.6–6.9 days from day 60 to the next alert). Alerts are escalations recorded by the engine; delivery is
  not implemented or measured, and FHIR exports them as Communications with status `preparation`.
- **Privacy (E-PHI, own technology):** 251 public synthetic health notes (Gretel, English). PHI characters left visible
  to an external model: raw 100 %, Microsoft Presidio 22.8 %, **NAVAJO v2 12.9 %** (−9.9 points vs Presidio, 95 % CI
  [−13.7, −6.5]), **NAVAJO v2 + Presidio 4.1 %** (−18.8 [−21.3, −16.3]); precision 0.88 / 0.83; NAVAJO v2 runs in
  0.3 ms per note without any model. Details in `README.md` and `results/phi/phi_results.json`.

## 6. Scalability and deployment readiness

- Pure Python standard library for the engine (NumPy only for simulation); 10,000 cases × 9 events processed in about
  1–2 s on a desktop CPU; event-driven timers (heap), no polling.
- Implemented: FHIR R4 export; message templates; privacy gateway for any language model (or none).
  Future integration points (not built yet): FHIR import from laboratory/EHR systems, SMS/WhatsApp/app delivery and
  inbound reply webhooks feeding the `patient_reply` event.
- New pathways are configuration (steps, owners, service levels), e.g. cervical screening, newborn screening, diabetic
  retinopathy, Well-Child follow-up.

## 7. Path to pilot and commercial model

- Pilot: one screening programme and two receiving providers, 6 months, stepped-wedge by clinic; primary outcome
  diagnostic follow-up within 120 days of an overdue result (the mFOCUS measure), plus time to notification, documented
  closure, patient understanding and escalation burden.
- Model: open-source core (MIT) + paid integration, hosting in-country and support for health systems.

## 8. Assumptions, dependencies and limitations

- Assumptions: service levels per step (defaults in `pathways.py`, to be set by the programme); usual-care timing from
  four US systems; intervention effect from one US trial transferred to Abu Dhabi; drop-off point of non-completers
  uniform over steps; usual care has no tracking (silent loss 100 %).
- Dependencies: Python ≥ 3.10; NumPy (simulation); pyarrow, Presidio and spaCy only for the privacy benchmark.
  Project NAVAJO core and NAVAJO v2 detector vendored (MIT) from Agnuxo1/edge-privacy-gateway commit 1bea827.
- Limitations: synthetic data only; no clinical users yet; no integration with a real EHR, laboratory or messaging
  gateway; Arabic is limited to message templates (no Arabic de-identification evaluated); escalation burden in
  low-performing systems can be high and needs tuning; FHIR resources are structurally tested, not validated with the
  official validator; NAVAJO v2 name detection depends on a lexicon built from English synthetic data.
- No data were provided by the organisers; all sources are public and declared (`docs/SOURCES.md`).
