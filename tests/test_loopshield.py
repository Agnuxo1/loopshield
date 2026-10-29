import json
import os
import random
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from loopshield import ABNORMAL_MAMMOGRAM, FIT_POSITIVE, CaseEngine, TransitionError  # noqa: E402
from loopshield.fhir import case_bundle  # noqa: E402
from loopshield.messages import patient_message  # noqa: E402
from loopshield.privacy import PrivacyGateway, PrivacyRefusal  # noqa: E402
from sim.fuzz import fuzz  # noqa: E402

HAPPY = ["notify", "acknowledge", "refer", "accept_referral", "book", "attend", "result"]


def walk(eng, cid, t0=0.0, step=2.0):
    for i, ev in enumerate(HAPPY):
        eng.apply(cid, ev, t0 + step * (i + 1))


def test_happy_path_closes_with_evidence_and_no_escalation():
    eng = CaseEngine()
    eng.open_case("c1", FIT_POSITIVE, 0.0)
    walk(eng, "c1")
    c = eng.apply("c1", "close", 20.0, report_ref="COL-REPORT-A", next_step="surveillance 3y")
    assert c.state == "CLOSED" and not c.escalations
    assert eng.check_invariants() == []


def test_out_of_order_event_is_rejected_and_case_unchanged():
    eng = CaseEngine()
    eng.open_case("c1", FIT_POSITIVE, 0.0)
    with pytest.raises(TransitionError):
        eng.apply("c1", "book", 1.0)
    assert eng.cases["c1"].state == "ISSUED"


def test_close_needs_evidence():
    eng = CaseEngine()
    eng.open_case("c1", FIT_POSITIVE, 0.0)
    walk(eng, "c1")
    with pytest.raises(TransitionError):
        eng.apply("c1", "close", 20.0, report_ref="R1")          # next_step missing
    assert eng.cases["c1"].open


def test_decision_closure_needs_named_clinician_and_attempts():
    eng = CaseEngine()
    eng.open_case("c1", FIT_POSITIVE, 0.0)
    with pytest.raises(TransitionError):
        eng.apply("c1", "close_by_decision", 1.0, reason="declined_informed", decided_by="dr-7",
                  decider_role="clerk")
    with pytest.raises(TransitionError):
        eng.apply("c1", "close_by_decision", 1.0, reason="unreachable_after_attempts", decided_by="dr-7",
                  decider_role="clinician")
    for t in (2, 3, 4):
        eng.apply("c1", "contact_attempt", t, channel="sms")
    c = eng.apply("c1", "close_by_decision", 5.0, reason="unreachable_after_attempts", decided_by="dr-7",
                  decider_role="clinician")
    assert c.state == "CLOSED_BY_DECISION"


def test_overdue_case_climbs_the_escalation_ladder_on_time():
    eng = CaseEngine()
    eng.open_case("c1", FIT_POSITIVE, 0.0)            # notify due at day 7
    eng.advance_to(30.0)
    esc = eng.cases["c1"].escalations
    assert [e["to"] for e in esc] == ["owner", "navigator", "clinical_lead"]
    assert [e["t"] for e in esc] == [7.0, 14.0, 21.0]
    assert eng.board()["screening_programme"]["overdue"] == 1


def test_progress_resets_the_ladder():
    eng = CaseEngine()
    eng.open_case("c1", FIT_POSITIVE, 0.0)
    eng.advance_to(8.0)
    eng.apply("c1", "notify", 9.0)
    assert eng.cases["c1"].escalation_level == 0
    eng.advance_to(16.5)                               # acknowledge due at day 16
    assert eng.cases["c1"].escalations[-1]["step"] == "ACKNOWLEDGED"


def test_urgent_goes_to_clinical_lead_immediately():
    eng = CaseEngine()
    c = eng.open_case("c1", FIT_POSITIVE, 0.0, urgent=True)
    assert c.escalations[0]["to"] == "clinical_lead" and c.escalations[0]["t"] == 0.0
    eng.advance_to(8.0)
    assert all(e["to"] == "clinical_lead" for e in c.escalations)


def test_audit_chain_detects_tampering():
    eng = CaseEngine()
    eng.open_case("c1", FIT_POSITIVE, 0.0)
    walk(eng, "c1")
    assert eng.audit.verify()
    eng.audit.entries[3]["data"]["to"] = "CLOSED"
    assert not eng.audit.verify()


def test_fuzz_small():
    assert fuzz(n=3000, seed=1)["violations"] == 0


def test_privacy_mask_and_restore_round_trip():
    gw = PrivacyGateway()
    eng = CaseEngine()
    c = eng.open_case("c1", FIT_POSITIVE, 0.0)
    note = ("Patient John Carter (MRN: 99812345, email john.carter@example.com) called on 2026-03-14; "
            "HbA1c 8.2 7.9, BP 130/85 mmHg. Prefers mornings.")
    prompt, mapping = gw.build_request(c, note)
    assert "John" not in prompt and "99812345" not in prompt and "example.com" not in prompt
    assert "8.2 7.9" in prompt and "130/85 mmHg" in prompt
    answer = "Dear " + next(k for k, v in mapping.items() if "John" in v) + ", please call us."
    restored = gw.restore(answer, mapping)
    assert "John" in restored and mapping == {}


def test_privacy_refuses_when_hard_identifier_survives():
    gw = PrivacyGateway()
    gw.v2.detect = lambda text: []                       # simulate a detector miss
    eng = CaseEngine()
    c = eng.open_case("c1", FIT_POSITIVE, 0.0)
    with pytest.raises(PrivacyRefusal):
        gw.build_request(c, "Contact: 784-1987-1234567-1, mail a.b@example.org")


def test_guard_does_not_flag_lab_values():
    assert PrivacyGateway.guard("HbA1c 8.2 7.9 8.0, LDL 3.4 mmol/L, BP 130/85") == []


def test_messages_both_languages_and_urgent_line():
    eng = CaseEngine()
    c = eng.open_case("c1", FIT_POSITIVE, 0.0, language="ar", urgent=True)
    eng.apply("c1", "notify", 1.0)
    m = patient_message(c)
    assert "998" in m and "999" not in m and "{" not in m
    c2 = eng.open_case("c2", FIT_POSITIVE, 1.0)
    m2 = patient_message(c2, "overdue")
    assert "not a diagnosis" not in m2 and "navigator" in m2


def test_fhir_bundle_shape():
    eng = CaseEngine()
    eng.open_case("c1", FIT_POSITIVE, 0.0)
    eng.advance_to(10.0)
    b = case_bundle(eng.cases["c1"])
    kinds = [e["resource"]["resourceType"] for e in b["entry"]]
    assert kinds[0] == "Task" and "Communication" in kinds and kinds[-1] == "Provenance"
    comm = next(e["resource"] for e in b["entry"] if e["resource"]["resourceType"] == "Communication")
    assert comm["status"] == "preparation" and "sent" not in comm
    json.dumps(b)


def test_time_cannot_go_backwards():
    eng = CaseEngine()
    eng.open_case("c1", FIT_POSITIVE, 5.0)
    with pytest.raises(TransitionError):
        eng.apply("c1", "notify", 4.0)


def test_placeholder_like_text_is_refused():
    eng = CaseEngine()
    c = eng.open_case("c1", FIT_POSITIVE, 0.0)
    with pytest.raises(PrivacyRefusal):
        PrivacyGateway().build_request(c, "see [PHI_1] above")


def test_audit_detects_removed_last_entry_and_rewrite():
    eng = CaseEngine()
    eng.open_case("c1", FIT_POSITIVE, 0.0)
    walk(eng, "c1")
    anchor = eng.audit.head
    eng.audit.entries.pop()
    assert not eng.audit.verify()
    eng2 = CaseEngine()
    eng2.open_case("c1", FIT_POSITIVE, 0.0)
    assert eng2.audit.verify() and not eng2.audit.verify(anchor=anchor)


def test_mammogram_messages_do_not_mention_colonoscopy():
    eng = CaseEngine()
    for lang in ("en", "ar"):
        c = eng.open_case(f"m-{lang}", ABNORMAL_MAMMOGRAM, 0.0, language=lang)
        for kind in ("first", "overdue"):
            m = patient_message(c, kind)
            assert "colonoscopy" not in m and "FIT" not in m and "القولون" not in m and "{" not in m
    assert "mammogram" in patient_message(eng.cases["m-en"])


def test_patient_reply_acknowledges_and_requests_call():
    eng = CaseEngine()
    eng.open_case("c1", FIT_POSITIVE, 0.0)
    eng.apply("c1", "notify", 1.0)
    c = eng.apply("c1", "patient_reply", 2.0, code="1")
    assert c.state == "ACKNOWLEDGED"
    c = eng.apply("c1", "patient_reply", 3.0, code="2")
    assert c.callback_requested and c.escalations[-1]["to"] == "navigator"
    with pytest.raises(TransitionError):
        eng.apply("c1", "patient_reply", 4.0, code="7")
    assert eng.check_invariants() == []


def test_clinical_lead_keeps_being_reminded_after_the_ladder():
    eng = CaseEngine()
    eng.open_case("c1", FIT_POSITIVE, 0.0)
    eng.advance_to(90.0)
    esc = eng.cases["c1"].escalations
    assert [e["t"] for e in esc] == [7.0, 14.0, 21.0, 51.0, 81.0]
    assert all(e["to"] == "clinical_lead" for e in esc[2:]) and esc[-1]["reason"] == "overdue_reminder"


def test_reply_to_first_message_records_notification_and_acknowledgement():
    eng = CaseEngine()
    eng.open_case("c1", FIT_POSITIVE, 0.0)
    c = eng.apply("c1", "patient_reply", 1.0, code="1")
    assert c.state == "ACKNOWLEDGED" and c.timeline["NOTIFIED"] == 1.0
    eng.apply("c1", "refer", 2.0)
    c = eng.apply("c1", "patient_reply", 3.0, code="1")
    assert c.state == "REFERRED" and len(c.replies) == 2
