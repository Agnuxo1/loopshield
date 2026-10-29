"""Care pathways: the ordered steps an actionable screening result must go through.

Each step names the role that owns it and its service level (days allowed after the previous
step). The default values are assumptions for the prototype, to be set by each programme; they
are configuration, not clinical guidance.
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Step:
    state: str          # state reached when the step is done
    owner: str          # accountable role while the case waits for this step
    sla_days: float     # days allowed after the previous step


@dataclass(frozen=True)
class Pathway:
    code: str
    title: str
    steps: tuple[Step, ...]
    completion_sla_days: float              # end-to-end target from issue to diagnostic test done
    closure_evidence: tuple[str, ...] = ("report_ref", "next_step")
    escalation_ladder: tuple[str, ...] = ("owner", "navigator", "clinical_lead")
    escalation_gap_days: float = 7.0
    closure_sla_days: float = 14.0          # result recorded -> closure documented
    repeat_after_ladder_days: float | None = 30.0   # keep reminding the clinical lead while the step is stuck
    meta: dict = field(default_factory=dict)

    def step_after(self, state: str) -> Step | None:
        names = [s.state for s in self.steps]
        if state == "ISSUED":
            return self.steps[0]
        i = names.index(state)
        if i + 1 < len(self.steps):
            return self.steps[i + 1]
        # last clinical step done: the owner must still document closure (evidence + next step)
        return Step("CLOSED", self.steps[-1].owner, self.closure_sla_days)


FIT_POSITIVE = Pathway(
    code="crc-fit-positive",
    title="Positive faecal immunochemical test -> diagnostic colonoscopy",
    steps=(
        Step("NOTIFIED", "screening_programme", 7),
        Step("ACKNOWLEDGED", "primary_care", 7),
        Step("REFERRED", "primary_care", 7),
        Step("REFERRAL_ACCEPTED", "gastroenterology", 7),
        Step("BOOKED", "gastroenterology", 7),
        Step("ATTENDED", "gastroenterology", 25),
        Step("RESULTED", "gastroenterology", 14),
    ),
    completion_sla_days=60,
)

ABNORMAL_MAMMOGRAM = Pathway(
    code="breast-birads0",
    title="Abnormal screening mammogram (recall) -> diagnostic imaging",
    steps=(
        Step("NOTIFIED", "screening_programme", 3),
        Step("ACKNOWLEDGED", "screening_programme", 4),
        Step("REFERRED", "screening_programme", 3),
        Step("REFERRAL_ACCEPTED", "breast_imaging", 3),
        Step("BOOKED", "breast_imaging", 3),
        Step("ATTENDED", "breast_imaging", 14),
        Step("RESULTED", "breast_imaging", 7),
    ),
    completion_sla_days=30,
)

PATHWAYS = {p.code: p for p in (FIT_POSITIVE, ABNORMAL_MAMMOGRAM)}
