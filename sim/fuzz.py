"""E-ENG: random event sequences against the case engine; counts invariant violations."""
from __future__ import annotations

import argparse
import json
import os
import random
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from loopshield import PATHWAYS, CaseEngine, TransitionError  # noqa: E402
from loopshield.engine import BACKWARD, DECISION_REASONS, FORWARD  # noqa: E402

EVENTS = list(FORWARD) + list(BACKWARD) + ["contact_attempt", "reassign", "close", "close_by_decision",
                                           "flag_urgent", "patient_reply", "bogus"]


def random_data(rng, ev):
    d = {}
    if rng.random() < 0.7:
        d["reason"] = rng.choice(sorted(DECISION_REASONS) + ["patient moved", ""])
    if rng.random() < 0.5:
        d["report_ref"] = rng.choice(["R-1", "", None])
    if rng.random() < 0.5:
        d["next_step"] = rng.choice(["surveillance", "", None])
    if rng.random() < 0.5:
        d["decided_by"] = rng.choice(["dr-1", "", None])
    if rng.random() < 0.5:
        d["decider_role"] = rng.choice(["clinician", "clerk"])
    if rng.random() < 0.3:
        d["owner_ref"] = rng.choice(["team-a", ""])
    if ev == "patient_reply":
        d["code"] = rng.choice(["1", "2", "3", "9"])
    return d


def fuzz(n: int = 100_000, seed: int = 0, per_engine: int = 20) -> dict:
    rng = random.Random(seed)
    pathways = list(PATHWAYS.values())
    stats = {"sequences": n, "events": 0, "accepted": 0, "rejected": 0, "violations": 0,
             "closed_evidence": 0, "closed_decision": 0, "urgent": 0, "callbacks": 0, "examples": []}
    eng = None
    for i in range(n):
        if i % per_engine == 0:
            if eng is not None:
                bad = eng.check_invariants()
                stats["violations"] += len(bad)
                stats["examples"] += bad[:3]
            eng = CaseEngine(audit=True)
        cid = f"f{i}"
        t = max(0.0, eng.now) + rng.uniform(0, 5)        # events are fed in time order
        eng.open_case(cid, rng.choice(pathways), t, urgent=rng.random() < 0.05)
        for _ in range(rng.randint(1, 30)):
            t += rng.expovariate(1 / 4)
            ev = rng.choice(EVENTS) if rng.random() < 0.6 else rng.choice(list(FORWARD))
            stats["events"] += 1
            try:
                eng.apply(cid, ev, t, **random_data(rng, ev))
                stats["accepted"] += 1
            except TransitionError:
                stats["rejected"] += 1
            bad = CaseEngine.check_case(eng.cases[cid])        # invariants after every event
            if bad:
                stats["violations"] += len(bad)
                stats["examples"] += bad[:1]
        c = eng.cases[cid]
        stats["closed_evidence"] += c.state == "CLOSED"
        stats["closed_decision"] += c.state == "CLOSED_BY_DECISION"
        stats["urgent"] += c.urgent
        stats["callbacks"] += c.callback_requested
    bad = eng.check_invariants()
    stats["violations"] += len(bad)
    stats["examples"] += bad[:3]
    return stats


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=100_000)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--out", default=None)
    a = ap.parse_args()
    s = fuzz(a.n, a.seed)
    print(json.dumps(s, indent=1))
    if a.out:
        with open(a.out, "w") as f:
            json.dump(s, f, indent=1)
