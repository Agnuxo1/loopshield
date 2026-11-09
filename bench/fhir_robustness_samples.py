# SPDX-FileCopyrightText: 2026 Francisco Angulo de Lafuente
# SPDX-License-Identifier: MIT
# Research-Project: LoopShield
# Research-ORCID: https://orcid.org/0009-0001-1634-7063
"""Rebuild and compare the nine synthetic bundles in the official E-ROBUST-01 receipt."""
import copy
import datetime as dt
import hashlib
import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from loopshield import ABNORMAL_MAMMOGRAM, FIT_POSITIVE, CaseEngine
from loopshield.fhir import case_bundle


def samples():
    valid = {}
    for pathway in (FIT_POSITIVE, ABNORMAL_MAMMOGRAM):
        for kind, case_id, offset in (("reply", "synthetic:<&α/1", 330),
                                      ("reassigned", "synthetic-" + "x" * 100, 0),
                                      ("time", "time-control", -420)):
            engine = CaseEngine()
            case = engine.open_case(case_id, pathway, 0.0, urgent=(kind == "reassigned"))
            if kind == "reassigned":
                engine.apply(case_id, "reassign", 1.0, owner_ref="synthetic-team")
            else:
                engine.apply(case_id, "patient_reply", 1.0, code="2" if kind == "reply" else "1")
            origin = dt.datetime(2026, 1, 1, 12,
                                 tzinfo=dt.timezone(dt.timedelta(minutes=offset)))
            valid[pathway.code + "-" + kind] = case_bundle(case, origin)
    first = next(iter(valid.values()))
    broken = {name: copy.deepcopy(first) for name in ("bad_id", "bad_time", "missing_intent")}
    broken["bad_id"]["entry"][0]["resource"]["id"] = "invalid/id"
    broken["bad_time"]["entry"][0]["resource"]["authoredOn"] = "2026-01-01T12:00:00+05:30Z"
    del broken["missing_intent"]["entry"][0]["resource"]["intent"]
    return {"valid": valid, "broken": broken}


if __name__ == "__main__":
    root = pathlib.Path(__file__).resolve().parents[1] / "results/robustness/fhir"
    receipt = json.loads((root / "summary.json").read_text())
    checked = 0
    for group, bundles in samples().items():
        for name, bundle in bundles.items():
            # The captured Windows inputs used CRLF; keep those exact bytes across platforms.
            payload = json.dumps(bundle, ensure_ascii=(group == "broken"), indent=2).replace("\n", "\r\n").encode()
            digest = hashlib.sha256(payload).hexdigest()
            assert digest == receipt["groups"][group]["inputs"][name + ".json"], (group, name)
            assert payload == (root / "input" / group / (name + ".json")).read_bytes()
            checked += 1
    print(f"{checked} regenerated input bytes and SHA-256 match the official validation receipt")
