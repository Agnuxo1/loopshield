# E-ROBUST-01 — prospective reliability checks, 9 November 2026

Author: Francisco Angulo de Lafuente · ORCID https://orcid.org/0009-0001-1634-7063

Baseline: public commit `19cb775cbbc7e23e84d175f8052148d43b14891a`; 21 existing tests pass locally. This protocol is written after inspecting the implementation, before executing the new checks or editing the engine/exporter. It is a targeted engineering audit, not a blinded evaluation or a clinical study.

Hypotheses:

1. Public engine operations reject non-finite or non-numeric day timestamps before changing cases, timers, the audit log or clock. A direct urgent flag must obey the engine clock. Valid finite chronological inputs continue to work.
2. FHIR export produces resource identifiers matching `[A-Za-z0-9-.]{1,64}` and internally consistent references for synthetic case IDs with punctuation, Unicode and long strings. IDs are deterministic, distinct across the listed inputs and retain current short safe IDs where possible.
3. FHIR dateTime values for naive and timezone-aware origins denote the intended instant. Naive origins keep the existing convention of UTC; aware origins are converted to UTC. Never append `Z` to an existing offset.

Method: run `python bench/robustness_checks.py --out results/robustness/baseline.json` before corrections; preserve failures. Compare the same named checks after corrections in `candidate.json`. Record the SHA-256 of the ten existing FHIR scenario bundles as a positive compatibility control. Neither real patient data nor network/model calls are used. Infinite advancement with already-active repeating timers is not executed in the baseline process; rejection probes use an empty engine or NaN to keep the diagnostic bounded. A potential unbounded loop is a code observation until separately reproduced under process limits.

Acceptance: all defined new checks pass; existing tests remain green; the ten default scenario hashes remain identical unless a disclosed correction requires a change. Validate new FHIR scenarios with the official HL7 validator and deliberately broken controls if the pinned local validator is available. Report local format checks separately from official validation. Preserve negative findings and avoid any claim of clinical benefit, anonymisation or production readiness.

Scope excludes new messaging integrations, authentication, persistent storage, deployment and clinical decisions. Any additional issue found by independent review gets its own reproduction and correction record.
