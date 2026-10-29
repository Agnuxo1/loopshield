"""E-SIM: positive-FIT cohort, usual care vs reminders-only tracker vs LoopShield (pre-registered).

Usual-care timing comes from Chubak et al. 2016; intervention effects from the mFOCUS trial
(Atlas et al. 2023). The tracker arms are run through the real LoopShield engine, so silent-loss
and escalation figures are measured on the software. See experiments/PREREGISTRO.md.
"""
from __future__ import annotations

import argparse
import json
import math
import os
import platform
import sys
import time

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

import dataclasses  # noqa: E402

from loopshield import FIT_POSITIVE, CaseEngine  # noqa: E402

PATHWAY = FIT_POSITIVE                 # --ladder-only replaces it with the v0.1 behaviour (no reminders)

SCENARIOS = {  # Chubak 2016: extremes across four US health systems
    "S-low": {"p12": 0.581, "median": 174.0},
    "S-high": {"p12": 0.838, "median": 41.0},
}
SIGMA = 0.8
SLA = 60.0
WINDOW = 120.0
TRIAL_BASE = 0.229            # mFOCUS usual-care completion within 120 days among overdue results
EFFECT_SD = (12.0 - 4.8) / 3.92
ARMS = {"A1-reminders": -0.2, "A2-loopshield": 8.5}
SENSITIVITY = [0.0, 4.8, 8.5, 12.0]
CORLEY = [(30, 30), (60, 28), (90, 31), (180, 31), (270, 43), (365, 49), (math.inf, 76)]
FORWARD = ["notify", "acknowledge", "refer", "accept_referral", "book", "attend", "result"]
WEIGHTS = np.cumsum([s.sla_days for s in FIT_POSITIVE.steps]) / sum(s.sla_days for s in FIT_POSITIVE.steps)


def norm_cdf(x):
    return 0.5 * (1 + math.erf(x / math.sqrt(2)))


def baseline(rng, n, sc):
    """Usual-care completion day (inf = never) and drop-off step for non-completers."""
    f365 = norm_cdf(math.log(365 / sc["median"]) / SIGMA)
    p_ever = sc["p12"] / f365
    t = np.exp(math.log(sc["median"]) + SIGMA * rng.standard_normal(n))
    t[rng.random(n) >= p_ever] = np.inf
    drop = rng.integers(1, len(FORWARD), n)          # steps done before dropping out (non-completers)
    return t, drop


def intervene(rng, t, delta_pts):
    t = t.copy()
    overdue = t > SLA
    if delta_pts >= 0:
        c = (delta_pts / 100) / (1 - TRIAL_BASE)
        pool = overdue & (t > SLA + WINDOW)
        hit = pool & (rng.random(t.size) < c)
        t[hit] = SLA + rng.uniform(0, WINDOW, t.size)[hit]
    else:
        c = (-delta_pts / 100) / TRIAL_BASE
        pool = overdue & (t <= SLA + WINDOW)
        hit = pool & (rng.random(t.size) < c)
        t[hit] = np.inf
    return t


def outcomes(t):
    done365 = float(np.mean(t <= 365))
    late300 = float(np.mean(t > 300))
    cancers = 0.0
    for d in t:
        for lim, rate in CORLEY:
            if d <= lim:
                cancers += rate
                break
    return {"O1_completed_365": done365, "O2_not_done_300": late300,
            "O3_crc_per_1000_assoc": cancers / t.size}


def run_engine(t, drop, median):
    """Feed every patient's events into the engine in global time order; measure visibility."""
    eng = CaseEngine(audit=False)
    events = []
    for i, (ti, di) in enumerate(zip(t, drop)):
        cid = f"p{i}"
        events.append((0.0, 0, cid, "open"))
        if math.isfinite(ti) and ti <= 365:
            for k, ev in enumerate(FORWARD):
                events.append((float(ti * WEIGHTS[k]), k + 1, cid, ev))
            events.append((float(ti) + 2.0, 9, cid, "close"))
        else:
            scale = median if not math.isfinite(ti) else min(ti, median)
            for k in range(di):
                events.append((float(scale * WEIGHTS[k]), k + 1, cid, FORWARD[k]))
    events.sort()
    for when, _, cid, ev in events:
        if when > 365.0:                # measure at day 365: later events have not happened yet
            continue
        if ev == "open":
            eng.open_case(cid, PATHWAY, when)
        elif ev == "close":
            eng.apply(cid, "close", when, report_ref="report", next_step="per findings")
        else:
            eng.apply(cid, ev, when)
    eng.advance_to(365.0)
    unresolved = [c for c in eng.cases.values() if c.open]
    silent = sum(1 for c in unresolved if not c.escalations)
    late = [c for c in eng.cases.values() if c.timeline.get("RESULTED", math.inf) > SLA]
    lag_pre = []                     # pre-registered definition (any escalation, truncated at 0)
    lag_after = []                   # corrected: first escalation recorded on or after the 60-day SLA
    no_esc_after = 0
    late_open = 0
    for c in late:
        first = min((e["t"] for e in c.escalations), default=math.inf)
        if math.isfinite(first):
            lag_pre.append(max(0.0, first - SLA))
        after = min((e["t"] for e in c.escalations if e["t"] >= SLA), default=math.inf)
        if math.isfinite(after):
            lag_after.append(after - SLA)
        if c.open:
            late_open += 1
            if not math.isfinite(after):
                no_esc_after += 1
    return {"O4_silent_share_of_unresolved": silent / max(1, len(unresolved)),
            "O5_median_days_sla_to_escalation": float(np.median(lag_pre)) if lag_pre else float("nan"),
            "O5b_median_days_sla_to_next_escalation": float(np.median(lag_after)) if lag_after else float("nan"),
            "O5b_p90_days_sla_to_next_escalation": float(np.percentile(lag_after, 90)) if lag_after else float("nan"),
            "O5b_open_late_without_escalation_after_sla": no_esc_after / max(1, late_open),
            "unresolved_365": len(unresolved) / len(t),
            "escalations_per_case": sum(len(c.escalations) for c in eng.cases.values()) / len(t),
            "invariant_violations": len(eng.check_invariants())}


def summarise(vals):
    a = np.array(vals, dtype=float)
    return {"mean": float(a.mean()), "sd": float(a.std(ddof=1)) if a.size > 1 else 0.0,
            "p2.5": float(np.percentile(a, 2.5)), "p97.5": float(np.percentile(a, 97.5))}


def main(n=10_000, seeds=range(10), out="results/sim"):
    os.makedirs(out, exist_ok=True)
    t0 = time.time()
    rows = []
    for sname, sc in SCENARIOS.items():
        for seed in seeds:
            base_rng = np.random.default_rng([seed, list(SCENARIOS).index(sname)])
            t_base, drop = baseline(base_rng, n, sc)
            arms = {"A0-usual": (t_base, None)}
            for k, (arm, mu) in enumerate(ARMS.items()):
                r = np.random.default_rng([seed, list(SCENARIOS).index(sname), 1 + k])
                d = r.normal(mu, EFFECT_SD)
                arms[arm] = (intervene(r, t_base, d), d)
            for k, d in enumerate(SENSITIVITY):
                r = np.random.default_rng([seed, list(SCENARIOS).index(sname), 10 + k])
                arms[f"A2-sens-{d}"] = (intervene(r, t_base, d), d)
            for arm, (t, d) in arms.items():
                row = {"scenario": sname, "seed": seed, "arm": arm, "delta_pts": d, **outcomes(t)}
                if arm == "A0-usual":
                    row["O4_silent_share_of_unresolved"] = 1.0       # assumption: no tracking system
                elif not arm.startswith("A2-sens"):
                    row.update(run_engine(t, drop, sc["median"]))
                rows.append(row)
    with open(os.path.join(out, "rows.json"), "w") as f:
        json.dump(rows, f, indent=1)
    summary = {}
    for sname in SCENARIOS:
        for arm in sorted({r["arm"] for r in rows}):
            rs = [r for r in rows if r["scenario"] == sname and r["arm"] == arm]
            keys = [k for k in rs[0] if k.startswith(("O", "unresolved", "escalations", "invariant"))]
            summary[f"{sname}/{arm}"] = {k: summarise([r[k] for r in rs]) for k in keys}
            if arm != "A0-usual":
                base = {r["seed"]: r for r in rows if r["scenario"] == sname and r["arm"] == "A0-usual"}
                summary[f"{sname}/{arm}"]["diff_O1_vs_usual"] = summarise(
                    [r["O1_completed_365"] - base[r["seed"]]["O1_completed_365"] for r in rs])
                summary[f"{sname}/{arm}"]["diff_O3_vs_usual"] = summarise(
                    [r["O3_crc_per_1000_assoc"] - base[r["seed"]]["O3_crc_per_1000_assoc"] for r in rs])
    meta = {"n_per_arm": n, "seeds": list(seeds), "seconds": round(time.time() - t0, 1),
            "python": platform.python_version(), "numpy": np.__version__, "platform": platform.platform()}
    with open(os.path.join(out, "summary.json"), "w") as f:
        json.dump({"meta": meta, "summary": summary}, f, indent=1)
    return meta, summary


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=10_000)
    ap.add_argument("--seeds", type=int, default=10)
    ap.add_argument("--out", default="results/sim")
    ap.add_argument("--ladder-only", action="store_true", help="v0.1 engine behaviour: no reminders after the ladder")
    a = ap.parse_args()
    if a.ladder_only:
        PATHWAY = dataclasses.replace(FIT_POSITIVE, repeat_after_ladder_days=None)
    meta, summary = main(a.n, range(a.seeds), a.out)
    print(json.dumps(meta))
    for k, v in summary.items():
        print(k, {m: round(s["mean"], 4) for m, s in v.items()})
