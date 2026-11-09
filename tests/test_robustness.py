# SPDX-FileCopyrightText: 2026 Francisco Angulo de Lafuente
# SPDX-License-Identifier: MIT
# Research-Project: LoopShield
# Research-ORCID: https://orcid.org/0009-0001-1634-7063
"""Regression contracts found by the prospective synthetic reliability audit."""
import datetime as dt
import hashlib
from fractions import Fraction

import pytest

from bench.robustness_checks import run_checks
from loopshield import CaseEngine, FIT_POSITIVE, TransitionError
from loopshield.fhir import case_bundle


def test_robustness_acceptance_contracts():
    result = run_checks()
    failures = [case for case in result["checks"] if not case["pass"]]
    assert failures == [], failures
    assert result["total"] == 26


def test_reserved_id_namespace_cannot_alias_an_encoded_case():
    unsafe = "synthetic/a"
    literal = "sha256-" + hashlib.sha256(unsafe.encode()).hexdigest()[:32]
    eng = CaseEngine()
    one = case_bundle(eng.open_case(unsafe, FIT_POSITIVE, 0.0))["entry"][0]["resource"]["id"]
    two = case_bundle(eng.open_case(literal, FIT_POSITIVE, 0.0))["entry"][0]["resource"]["id"]
    assert one != two


def test_elapsed_days_preserve_instant_and_unknown_urgent_case_is_rejected():
    eng = CaseEngine()
    case = eng.open_case("independent-control", FIT_POSITIVE, 1.0)
    origin = dt.datetime(2026, 1, 1, 12, tzinfo=dt.timezone(dt.timedelta(hours=5, minutes=30)))
    task = case_bundle(case, origin)["entry"][0]["resource"]
    assert task["id"] == "loop-independent-control"
    assert task["authoredOn"] == "2026-01-02T06:30:00Z"
    before = (eng.now, eng.audit.head, len(eng._timers))
    with pytest.raises(TransitionError):
        eng.flag_urgent("missing", 5.0, by="synthetic reviewer")
    assert (eng.now, eng.audit.head, len(eng._timers)) == before


@pytest.mark.parametrize("via_event", [False, True])
@pytest.mark.parametrize("offset", [-1e-6, 0.0, 1e-6])
def test_urgency_deadline_order_and_post_activation_fault_detection(via_event, offset):
    eng = CaseEngine()
    case = eng.open_case("deadline-urgent", FIT_POSITIVE, 0.0)
    when = case.due_at + offset
    if via_event:
        eng.apply(case.case_id, "flag_urgent", when, by="synthetic review")
    else:
        eng.flag_urgent(case.case_id, when, by="synthetic review")
    assert eng.check_invariants() == []
    assert case.escalations[case.urgent_escalation_index]["reason"] == "urgent"
    # Equal-time lower-target alerts AFTER activation must remain detectable.
    fault = {**case.escalations[-1], "reason": "overdue", "to": "owner", "t": when}
    case.escalations.append(fault)
    assert any("below the clinical lead" in failure for failure in eng.check_invariants())


def test_fhir_preserves_subsecond_instant():
    origin = dt.datetime(2026, 1, 1, 0, 0, 0, 250000,
                         tzinfo=dt.timezone(dt.timedelta(hours=5, minutes=45)))
    eng = CaseEngine()
    case = eng.open_case("subsecond", FIT_POSITIVE, 0.5 / 86400)
    value = case_bundle(case, origin)["entry"][0]["resource"]["authoredOn"]
    assert value == "2025-12-31T18:15:00.750000Z"


def test_supported_real_days_are_normalised_for_export():
    eng = CaseEngine()
    case = eng.open_case("fractional-day", FIT_POSITIVE, Fraction(1, 2))
    assert isinstance(case.issued_at, float)
    assert case_bundle(case)["entry"][0]["resource"]["authoredOn"] == "2026-01-01T12:00:00Z"
