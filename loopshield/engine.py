"""Closed-loop case engine for actionable screening results.

A case moves through the steps of its pathway. At every moment it has exactly one accountable
owner and one due time; when the due time passes, the engine escalates up a ladder
(owner -> navigator -> clinical lead) until the step is done. A case can be closed only with
closure evidence (report reference and next step) or with a documented decision by a named
clinician. Every change is written to a hash-chained audit log.

Time is a float in days since an arbitrary origin; the caller supplies it, so the engine runs
the same in a live service and in a simulation.
"""
from __future__ import annotations

import hashlib
import heapq
import json
from dataclasses import dataclass, field

from .pathways import Pathway

TERMINAL = {"CLOSED", "CLOSED_BY_DECISION"}
FORWARD = {"notify": "NOTIFIED", "acknowledge": "ACKNOWLEDGED", "refer": "REFERRED",
           "accept_referral": "REFERRAL_ACCEPTED", "book": "BOOKED", "attend": "ATTENDED",
           "result": "RESULTED"}
BACKWARD = {"reject_referral": ("REFERRED", "ACKNOWLEDGED"),
            "no_show": ("BOOKED", "REFERRAL_ACCEPTED"),
            "cancel_booking": ("BOOKED", "REFERRAL_ACCEPTED")}
DECISION_REASONS = {"declined_informed", "unreachable_after_attempts", "care_elsewhere_confirmed",
                    "deceased", "result_amended_normal"}
MIN_ATTEMPTS_UNREACHABLE = 3


class TransitionError(ValueError):
    """An event that is not allowed in the case's current state; the case is not changed."""


@dataclass
class Case:
    case_id: str
    pathway: Pathway
    issued_at: float
    state: str = "ISSUED"
    entered_at: float = 0.0
    owner_role: str = ""
    owner_ref: str | None = None           # person or team, if assigned
    urgent: bool = False
    attempts: int = 0
    escalation_level: int = 0              # for the current step
    escalations: list = field(default_factory=list)
    timeline: dict = field(default_factory=dict)
    closure: dict | None = None
    language: str = "en"
    urgent_at: float | None = None
    callback_requested: bool = False
    replies: list = field(default_factory=list)

    @property
    def open(self) -> bool:
        return self.state not in TERMINAL

    @property
    def pending_step(self):
        return self.pathway.step_after(self.state) if self.open else None

    @property
    def due_at(self) -> float | None:
        step = self.pending_step
        return None if step is None else self.entered_at + step.sla_days


class AuditLog:
    """Append-only, hash-chained log. `verify()` detects any edited, removed or reordered entry."""

    def __init__(self, enabled: bool = True):
        self.enabled = enabled
        self.entries: list[dict] = []
        self.head = "0" * 64

    def write(self, t: float, case_id: str, kind: str, data: dict):
        if not self.enabled:
            return
        body = {"seq": len(self.entries), "t": round(t, 6), "case": case_id, "kind": kind,
                "data": data, "prev": self.head}
        digest = hashlib.sha256(json.dumps(body, sort_keys=True, default=str).encode()).hexdigest()
        body["hash"] = digest
        self.entries.append(body)
        self.head = digest

    def verify(self, anchor: str | None = None) -> bool:
        """Check every link and that the chain ends at the recorded head (detects a removed last entry).
        Pass `anchor`, a head hash stored outside the log, to also detect a fully rewritten log."""
        prev = "0" * 64
        for i, e in enumerate(self.entries):
            body = {k: v for k, v in e.items() if k != "hash"}
            if body["seq"] != i or body["prev"] != prev:
                return False
            if hashlib.sha256(json.dumps(body, sort_keys=True, default=str).encode()).hexdigest() != e["hash"]:
                return False
            prev = e["hash"]
        if prev != self.head:
            return False
        return anchor is None or anchor == self.head


class CaseEngine:
    def __init__(self, audit: bool = True):
        self.cases: dict[str, Case] = {}
        self.audit = AuditLog(audit)
        self.now = float("-inf")
        self._timers: list[tuple[float, int, str, int]] = []   # (time, seq, case_id, version)
        self._version: dict[str, int] = {}
        self._seq = 0

    # ---- time -----------------------------------------------------------------------------
    def advance_to(self, t: float):
        """Fire every escalation due at or before t, in time order. Time never goes backwards."""
        if t < self.now - 1e-9:
            raise TransitionError(f"time {t} is before the engine clock {self.now}; feed events in time order")
        while self._timers and self._timers[0][0] <= t:
            when, _, cid, ver = heapq.heappop(self._timers)
            if self._version.get(cid) != ver:
                continue                       # stale timer: the case moved on
            self._escalate(self.cases[cid], when)
        self.now = max(self.now, t)

    def _arm(self, case: Case):
        ver = self._version.get(case.case_id, 0) + 1
        self._version[case.case_id] = ver
        if not case.open:
            return
        due = case.due_at
        ladder = case.pathway.escalation_ladder
        gap = case.pathway.escalation_gap_days
        if case.escalation_level >= len(ladder):
            repeat = case.pathway.repeat_after_ladder_days
            if repeat is None:
                return
            # ladder exhausted: remind the clinical lead every `repeat` days until the step is done
            extra = case.escalation_level - len(ladder) + 1
            when = due + (len(ladder) - 1) * gap + extra * repeat
        else:
            when = due + case.escalation_level * gap
        self._seq += 1
        heapq.heappush(self._timers, (when, self._seq, case.case_id, ver))

    def _escalate(self, case: Case, t: float, reason: str = "overdue"):
        ladder = case.pathway.escalation_ladder
        level = case.escalation_level
        target = ladder[-1] if case.urgent else ladder[min(level, len(ladder) - 1)]
        if reason == "overdue" and level >= len(ladder):
            reason = "overdue_reminder"
        rec = {"t": t, "level": level + 1, "to": target, "step": case.pending_step.state, "reason": reason}
        case.escalations.append(rec)
        case.escalation_level = level + 1
        self.audit.write(t, case.case_id, "escalation", rec)
        self._arm(case)

    # ---- lifecycle ------------------------------------------------------------------------
    def open_case(self, case_id: str, pathway: Pathway, t: float, language: str = "en",
                  urgent: bool = False) -> Case:
        if case_id in self.cases:
            raise TransitionError(f"case {case_id} already exists")
        self.advance_to(t)
        c = Case(case_id, pathway, issued_at=t, entered_at=t, language=language)
        c.owner_role = pathway.steps[0].owner
        c.timeline["ISSUED"] = t
        self.cases[case_id] = c
        self.audit.write(t, case_id, "opened", {"pathway": pathway.code, "owner": c.owner_role,
                                                 "language": language})
        self._arm(c)
        if urgent:
            self.flag_urgent(case_id, t, by="intake")
        return c

    def apply(self, case_id: str, event: str, t: float, **data) -> Case:
        """Apply one event. Raises TransitionError (case unchanged) if the event is not allowed."""
        self.advance_to(t)
        c = self.cases.get(case_id)
        if c is None:
            raise TransitionError(f"unknown case {case_id}")
        if not c.open:
            raise TransitionError(f"case {case_id} is closed")
        if event in FORWARD:
            target = FORWARD[event]
            step = c.pending_step
            if step is None or step.state != target:
                raise TransitionError(f"{event} not allowed in state {c.state}")
            self._move(c, target, t, event, data)
        elif event in BACKWARD:
            frm, to = BACKWARD[event]
            if c.state != frm:
                raise TransitionError(f"{event} not allowed in state {c.state}")
            if not data.get("reason"):
                raise TransitionError(f"{event} needs a reason")
            self._move(c, to, t, event, data)
        elif event == "contact_attempt":
            c.attempts += 1
            self.audit.write(t, case_id, event, {"attempt": c.attempts, **data})
        elif event == "reassign":
            if not data.get("owner_ref"):
                raise TransitionError("reassign needs owner_ref")
            c.owner_ref = data["owner_ref"]
            self.audit.write(t, case_id, event, data)
        elif event == "close":
            missing = [k for k in c.pathway.closure_evidence if not data.get(k)]
            if c.state != "RESULTED":
                raise TransitionError(f"close not allowed in state {c.state}; use close_by_decision")
            if missing:
                raise TransitionError(f"closure evidence missing: {missing}")
            c.closure = {"kind": "evidence", **{k: data[k] for k in c.pathway.closure_evidence}}
            self._move(c, "CLOSED", t, event, data)
        elif event == "close_by_decision":
            if not data.get("decided_by") or data.get("decider_role") != "clinician":
                raise TransitionError("close_by_decision needs a named clinician (decided_by, decider_role)")
            if data.get("reason") not in DECISION_REASONS:
                raise TransitionError(f"reason must be one of {sorted(DECISION_REASONS)}")
            if data["reason"] == "unreachable_after_attempts" and c.attempts < MIN_ATTEMPTS_UNREACHABLE:
                raise TransitionError(f"unreachable needs >= {MIN_ATTEMPTS_UNREACHABLE} documented attempts")
            c.closure = {"kind": "decision", "decided_by": data["decided_by"], "reason": data["reason"]}
            self._move(c, "CLOSED_BY_DECISION", t, event, data)
        elif event == "patient_reply":
            code = str(data.get("code", "")).strip()
            if code not in {"1", "2", "3"}:
                raise TransitionError("patient_reply code must be 1, 2 or 3")
            c.replies.append({"t": t, "code": code})
            self.audit.write(t, case_id, event, {"code": code})
            # "1" acknowledges only while the case waits for notification or acknowledgement: a reply to the
            # first message proves it was received (ISSUED -> NOTIFIED) and understood (-> ACKNOWLEDGED).
            # In later states it is stored as a reply and changes nothing.
            if code == "1" and c.state == "ISSUED":
                self._move(c, "NOTIFIED", t, "notify", {"via": "patient_reply"})
            if code == "1" and c.state == "NOTIFIED":
                self._move(c, "ACKNOWLEDGED", t, "acknowledge", {"via": "patient_reply"})
            elif code in {"2", "3"}:
                # a person must call back (2) or arrange another language (3): navigator now
                c.callback_requested = True
                rec = {"t": t, "level": 0, "to": "navigator", "step": c.pending_step.state,
                       "reason": "callback_requested" if code == "2" else "language_request"}
                c.escalations.append(rec)
                self.audit.write(t, case_id, "escalation", rec)
        elif event == "flag_urgent":
            self.flag_urgent(case_id, t, by=data.get("by", "unknown"))
        else:
            raise TransitionError(f"unknown event {event}")
        return c

    def flag_urgent(self, case_id: str, t: float, by: str):
        c = self.cases[case_id]
        if c.urgent or not c.open:
            return
        c.urgent = True
        c.urgent_at = t
        self.audit.write(t, case_id, "flag_urgent", {"by": by})
        # Urgent cases go straight to the top of the ladder: a qualified clinician sees them now,
        # and every later overdue escalation of the case also goes to the clinical lead.
        level = c.escalation_level
        self._escalate(c, t, reason="urgent")
        c.escalation_level = level
        self._arm(c)

    def _move(self, c: Case, to: str, t: float, event: str, data: dict):
        c.state = to
        c.entered_at = t
        c.timeline.setdefault(to, t)
        c.escalation_level = 0
        step = c.pending_step
        if step is not None:
            c.owner_role = step.owner
            c.owner_ref = None if event in FORWARD else c.owner_ref
        self.audit.write(t, c.case_id, event, {"to": to, "owner": c.owner_role,
                                               **{k: v for k, v in data.items() if k != "note"}})
        self._arm(c)

    # ---- views ----------------------------------------------------------------------------
    def board(self, t: float | None = None) -> dict:
        """Work-list counts per owner role: open, overdue, unassigned, urgent."""
        t = self.now if t is None else t
        out: dict[str, dict[str, int]] = {}
        for c in self.cases.values():
            if not c.open:
                continue
            row = out.setdefault(c.owner_role, {"open": 0, "overdue": 0, "unassigned": 0, "urgent": 0})
            row["open"] += 1
            row["overdue"] += c.due_at is not None and t > c.due_at
            row["unassigned"] += c.owner_ref is None
            row["urgent"] += c.urgent
        return out

    def check_invariants(self) -> list[str]:
        bad = []
        for c in self.cases.values():
            bad += self.check_case(c)
        if not self.audit.verify():
            bad.append("audit chain broken")
        return bad

    @staticmethod
    def check_case(c: Case) -> list[str]:
        """Safety invariants of one case; cheap enough to run after every event."""
        bad = []
        if c.state == "CLOSED" and not (c.closure and all(c.closure.get(k) for k in c.pathway.closure_evidence)):
            bad.append(f"{c.case_id}: closed without evidence")
        if c.state == "CLOSED_BY_DECISION" and not (c.closure and c.closure.get("decided_by")):
            bad.append(f"{c.case_id}: closed by decision without a named clinician")
        if c.open and not c.owner_role:
            bad.append(f"{c.case_id}: open without an accountable owner")
        if c.urgent and not any(e["reason"] == "urgent" and e["to"] == c.pathway.escalation_ladder[-1]
                                and e["t"] == c.urgent_at for e in c.escalations):
            bad.append(f"{c.case_id}: urgent but not escalated to the clinical lead at once")
        if c.urgent and any(e["reason"] == "overdue" and e["to"] != c.pathway.escalation_ladder[-1]
                            and e["t"] >= c.urgent_at for e in c.escalations):
            bad.append(f"{c.case_id}: urgent case escalated below the clinical lead")
        if c.callback_requested and not any(e["reason"] in {"callback_requested", "language_request"}
                                            for e in c.escalations):
            bad.append(f"{c.case_id}: call-back requested but nobody alerted")
        return bad
