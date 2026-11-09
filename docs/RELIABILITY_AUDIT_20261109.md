# Targeted reliability audit — 9 November 2026

Francisco Angulo de Lafuente · https://orcid.org/0009-0001-1634-7063

Three implementation defects were reproduced and corrected: non-finite engine timestamps were accepted, some case IDs produced invalid FHIR resource IDs, and timezone-aware origins produced invalid dateTime strings. These are engineering corrections to a synthetic prototype. They do not establish clinical effectiveness, anonymisation or readiness for live care.

## Protocol and comparison

The [protocol](../experiments/PREREGISTRO_RESCUE_20261109.md) and first diagnostic harness were committed as `71ca253` before engine/exporter corrections. Source baseline: `19cb775cbbc7e23e84d175f8052148d43b14891a`. The 21 existing tests passed before changes. Code inspection informed the targeted cases; this was not blinded or a representative error-rate estimate.

| Check | Baseline | Corrected |
|---|---:|---:|
| Defined synthetic acceptance cases | 4 / 26 | 26 / 26 |
| Existing regression tests | 21 / 21 | 21 / 21 |
| Additional regression cases | — | 11 / 11 |
| Ten default FHIR scenario hashes | Reference | All identical |
| Six new FHIR bundles, official validator | Not run | 0 errors, 0 warnings in each |
| Three deliberately broken controls | Not run | Each reported errors |

The 26 cases include related variations of the same three contracts and positive controls. They are not 26 independent defects. Raw [baseline](../results/robustness/baseline.json) and [candidate](../results/robustness/candidate.json) reports include measurement and implementation hashes.

## Corrections

- Engine clock operations normalise supported real day timestamps to finite floats and reject NaN, infinity, booleans and non-numeric values with `TransitionError` before mutation. Direct urgent flags now obey the same chronological clock and reject unknown cases explicitly. Due timers run before an urgent flag applies; a sequence boundary distinguishes pre-activation from later alerts at the same timestamp. All later overdue alerts must target the clinical lead, including equal-time ones.
- FHIR resource IDs keep existing short safe case IDs. Longer, reserved-prefix or non-ASCII/punctuated IDs get a deterministic bounded SHA-256-derived stem. Internal Task, Communication and Provenance references use the same stem. This encodes identifiers; it does not make sensitive identifiers anonymous.
- Naive datetime origins retain the existing UTC convention. Aware origins are converted to UTC before adding elapsed days and formatting with one `Z` suffix. Microseconds are retained when present. See the [FHIR R4 primitive type definitions](https://hl7.org/fhir/R4/datatypes.html).

## Official FHIR validation

HL7 FHIR Validator **7.0.5**, base **R4 4.0.1**, `-tx n/a`, CPU only on Debian. Pinned validator SHA-256: `9dfe9f305b0f9389eceade2a4a1c9a2740d7b0e614066fdf07a78b571c76d92f`. Isolated Temurin JRE 21.0.13+9, downloaded from the official Adoptium release and verified against its published SHA-256. Java used at most 1 GiB heap and two active processors; no GPU job was launched or changed.

Two pathways × three scenarios: patient callback with Unicode/punctuation ID; urgent reassigned case with a long ID; patient acknowledgement with timezone-aware origin. Controls independently contain an illegal ID, an invalid offset-plus-`Z` dateTime, and missing Task intent. The validator reports 2, 2 and 1 errors respectively; its process exit code is zero even for these controls, so acceptance uses issue severities and exact input/outcome counts. Scope is base R4; no terminology server, Abu Dhabi profile or live exchange was tested.

## Measurement corrections and negative results

1. The first harness compared a deep-copied `AuditLog` object by identity, causing false mutation failures in corrected code. It was changed to compare actual audit fields; both source versions were rerun with that same corrected harness. Initial outputs remain as `*_harness_v1.json`.
2. The first server validation attempt stopped because Java was absent from PATH. The pinned JRE was then installed only in the task's own directory.
3. The next attempt validated numbered backup files preserved by the transfer bridge as extra inputs: 12 valid and 6 broken outcomes instead of 6 and 3. The exact-count gate failed. The final run passed an explicit list of JSON inputs, excluding backups, and produced exactly six valid and three control outcomes. Earlier reports remain in the private execution receipts.
4. Independent review reproduced the comparison and hashes, then found a new urgency/deadline tie regression and
   the inherited loss of subsecond precision. Both were corrected with additional boundary, fault-injection and
   fractional-time tests. The invariant now uses event order and still detects lower-target post-activation alerts
   at the same instant. A supported `Fraction` input is normalised before export. This review-driven extension is
   recorded separately in the protocol.

## Reproduction and limits

```bash
python -m pytest -q tests
python bench/robustness_checks.py --out /tmp/loopshield-robustness.json --require-all
python bench/fhir_robustness_samples.py
```

To compare the baseline, create a detached checkout of `19cb775`, then set `LOOPSHIELD_CHECK_SOURCE_ROOT` to that checkout when running the same diagnostic script. Never import baseline and candidate engine modules in one Python process.

Finite timestamp validation does not limit the amount of work caused by a very large finite time jump. The engine remains an in-memory prototype without authentication, durable delivery or live patient integration. A hash is not a privacy guarantee. Arabic templates still require native-speaker and clinical review. The previous simulation and privacy study have not been reinterpreted as clinical results.
