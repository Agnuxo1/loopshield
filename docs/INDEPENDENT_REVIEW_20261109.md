# Independent review of the reliability changes

Fresh conversation context; read-only reviewer, EGM critical and drift lenses. No account access, GPU work or
publication by the reviewer. Reports were returned to the author, who applied and tested corrections.

The first review reproduced the original 4/26 versus 26/26 comparison and ten compatible FHIR scenario hashes.
New checks found an introduced urgent/deadline tie regression and inherited subsecond timestamp truncation.
It also observed that a supported `Fraction` day input needed normalisation before FHIR export. These findings
led to additional tests and the corrections described in [the audit](RELIABILITY_AUDIT_20261109.md).

The second review reported no remaining findings in the reviewed scope. It executed:

- 11 new regression cases, with automatic third-party pytest plugins disabled;
- regeneration of all nine FHIR inputs, matching exact bytes and receipt SHA-256 values;
- 12 additional urgency cases covering both entry paths, both pathways, deadline boundaries and 100 subsequent days;
- fault injection of a lower-target `overdue_reminder` after urgent activation, detected even with the same timestamp;
- 30 exact datetime comparisons, including negative/fractional day values, microsecond carry, naive/aware origins
  and offsets up to plus/minus23:59;
- 32 populated-engine rejection checks, four operations and eight invalid inputs, without state mutation;
- separate-process baseline/candidate comparison and ten existing scenario hashes;
- the six valid FHIR report outcomes and three control outcomes, including all nine input hashes.

The reviewer did not rerun the official Java validator or the 21 pre-existing tests. The author ran all 32 tests
and executed the official validator on the server CPU. An initial reviewer pytest attempt failed because of an
unrelated global `nengo` plugin; it was not counted as a successful test run. This review is scoped engineering
evidence, not a guarantee of production safety, clinical effectiveness or anonymity.
