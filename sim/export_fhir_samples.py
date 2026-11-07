# SPDX-FileCopyrightText: 2026 Francisco Angulo de Lafuente
# SPDX-License-Identifier: MIT
# Research-Project: LoopShield
# Research-Author: Francisco Angulo de Lafuente
# Research-ORCID: https://orcid.org/0009-0001-1634-7063
# Research-Date: 2026-11-07
"""Write one FHIR R4 bundle per engine scenario, plus two broken bundles as negative controls (E-FHIR-01)."""
from __future__ import annotations

import argparse
import copy
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from loopshield import ABNORMAL_MAMMOGRAM, FIT_POSITIVE, CaseEngine  # noqa: E402
from loopshield.engine import DECISION_REASONS  # noqa: E402
from loopshield.fhir import case_bundle  # noqa: E402

HAPPY = ["notify", "acknowledge", "refer", "accept_referral", "book", "attend", "result"]


def scenarios() -> dict:
    out = {}
    for name, pathway in (("fit", FIT_POSITIVE), ("mammogram", ABNORMAL_MAMMOGRAM)):
        eng = CaseEngine()
        eng.open_case("open", pathway, 0.0)
        out[f"{name}_open"] = case_bundle(eng.cases["open"])

        eng = CaseEngine()
        eng.open_case("late", pathway, 0.0)
        eng.advance_to(40.0)
        out[f"{name}_overdue"] = case_bundle(eng.cases["late"])

        eng = CaseEngine()
        eng.open_case("urgent", pathway, 0.0)
        eng.flag_urgent("urgent", 1.0, by="Dr Example")
        out[f"{name}_urgent"] = case_bundle(eng.cases["urgent"])

        eng = CaseEngine()
        eng.open_case("done", pathway, 0.0)
        for i, ev in enumerate(HAPPY):
            eng.apply("done", ev, 2.0 * (i + 1))
        eng.apply("done", "close", 20.0, **{k: "synthetic-" + k for k in pathway.closure_evidence})
        out[f"{name}_closed_evidence"] = case_bundle(eng.cases["done"])

        eng = CaseEngine()
        eng.open_case("dec", pathway, 0.0)
        eng.apply("dec", "close_by_decision", 5.0, reason=sorted(DECISION_REASONS)[0], decided_by="Dr Example",
                  decider_role="clinician")
        out[f"{name}_closed_decision"] = case_bundle(eng.cases["dec"])
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    os.makedirs(os.path.join(a.out, "valid"), exist_ok=True)
    os.makedirs(os.path.join(a.out, "broken"), exist_ok=True)
    s = scenarios()
    for k, b in s.items():
        with open(os.path.join(a.out, "valid", k + ".json"), "w", encoding="utf-8") as f:
            json.dump(b, f, indent=1)
    bad = copy.deepcopy(s["fit_open"])
    bad["entry"][0]["resource"]["status"] = "not-a-status"
    bad2 = copy.deepcopy(s["fit_open"])
    del bad2["entry"][0]["resource"]["intent"]
    for k, b in (("bad_status", bad), ("missing_intent", bad2)):
        with open(os.path.join(a.out, "broken", k + ".json"), "w", encoding="utf-8") as f:
            json.dump(b, f, indent=1)
    print(len(s), "valid scenarios, 2 broken")


if __name__ == "__main__":
    main()
