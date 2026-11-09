# SPDX-FileCopyrightText: 2026 Francisco Angulo de Lafuente
# SPDX-License-Identifier: MIT
# Research-Project: LoopShield
# Research-ORCID: https://orcid.org/0009-0001-1634-7063
"""E-ROBUST-01: bounded, synthetic black-box checks of engine/FHIR contracts."""
from __future__ import annotations

import argparse
import copy
import datetime as dt
import hashlib
import json
import os
import pathlib
import re
import sys

sys.path.insert(0, os.environ.get("LOOPSHIELD_CHECK_SOURCE_ROOT", str(pathlib.Path(__file__).resolve().parents[1])))
from loopshield import CaseEngine, FIT_POSITIVE, TransitionError
from loopshield.fhir import case_bundle
from sim.export_fhir_samples import scenarios


def run_checks():
    checks = []

    def record(name, check):
        try:
            detail = check()
            checks.append({"name": name, "pass": True, "detail": detail})
        except Exception as exc:
            checks.append({"name": name, "pass": False,
                           "detail": f"{type(exc).__name__}: {exc}"})

    def reject_unchanged(operation, value, populated=False):
        eng = CaseEngine()
        if populated:
            eng.open_case("synthetic", FIT_POSITIVE, 0.0)
        def snapshot():
            # AuditLog has identity equality: compare its fields, not a deep-copied object identity.
            return copy.deepcopy({**eng.__dict__, "audit": eng.audit.__dict__})
        before = snapshot()
        try:
            if operation == "open":
                eng.open_case("new", FIT_POSITIVE, value)
            elif operation == "advance":
                eng.advance_to(value)
            elif operation == "apply":
                eng.apply("synthetic", "notify", value)
            else:
                eng.flag_urgent("synthetic", value, by="synthetic reviewer")
        except TransitionError:
            assert snapshot() == before, "rejection changed engine state"
            return "TransitionError; state unchanged"
        raise AssertionError("invalid timestamp accepted")

    for label, value in (("nan", float("nan")), ("positive_infinity", float("inf")),
                         ("negative_infinity", float("-inf")), ("bool", True),
                         ("string", "1.0"), ("none", None)):
        for operation in ("open", "advance"):
            record(f"{operation}_rejects_{label}",
                   lambda op=operation, v=value: reject_unchanged(op, v))
    for operation in ("apply", "urgent"):
        record(f"{operation}_rejects_nan_without_mutation",
               lambda op=operation: reject_unchanged(op, float("nan"), True))
    record("direct_urgent_rejects_past_time",
           lambda: reject_unchanged("urgent", -1.0, True))

    def chronological_control():
        eng = CaseEngine()
        eng.open_case("control", FIT_POSITIVE, 0.0)
        eng.apply("control", "patient_reply", 2.0, code="1")
        assert eng.cases["control"].state == "ACKNOWLEDGED"
        assert not eng.check_invariants()
        return "finite chronological control succeeds"

    record("finite_chronological_control", chronological_control)

    ids = ["safe-1", "synthetic:alpha/1", "synthetic α", "x" * 200,
           "synthetic:<&>", "sha256-" + "a" * 40]
    observed = []

    def id_check(case_id):
        eng = CaseEngine()
        case = eng.open_case(case_id, FIT_POSITIVE, 0.0)
        eng.apply(case_id, "patient_reply", 1.0, code="2")
        bundle = case_bundle(case)
        resources = [entry["resource"] for entry in bundle["entry"]]
        for resource in resources:
            assert re.fullmatch(r"[A-Za-z0-9-.]{1,64}", resource["id"]), "invalid FHIR id"
        task_id = resources[0]["id"]
        assert resources[-1]["target"][0]["reference"] == "Task/" + task_id
        assert resources[1]["partOf"][0]["reference"] == "Task/" + task_id
        assert bundle == case_bundle(case), "export is not deterministic"
        assert len({entry["fullUrl"] for entry in bundle["entry"]}) == len(resources)
        observed.append(task_id)
        return "bounded IDs, stable references and deterministic export"

    for index, case_id in enumerate(ids):
        record(f"fhir_case_id_{index}", lambda cid=case_id: id_check(cid))
    record("distinct_test_case_ids", lambda: len(observed) == len(set(observed)) or
           (_ for _ in ()).throw(AssertionError("duplicate test identifiers")))

    def time_check(offset):
        zone = dt.timezone(dt.timedelta(minutes=offset))
        origin = dt.datetime(2026, 1, 1, 12, 0, tzinfo=zone)
        eng = CaseEngine()
        case = eng.open_case("time-control", FIT_POSITIVE, 0.0)
        value = case_bundle(case, origin=origin)["entry"][0]["resource"]["authoredOn"]
        assert re.fullmatch(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ", value), value
        parsed = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
        assert parsed == origin.astimezone(dt.timezone.utc), "instant changed"
        return "valid UTC dateTime, instant retained"

    for offset in (0, 330, -420):
        record(f"fhir_origin_offset_{offset}", lambda off=offset: time_check(off))
    default_scenarios = {name: hashlib.sha256(json.dumps(bundle, sort_keys=True).encode()).hexdigest()
                         for name, bundle in scenarios().items()}
    implementation_hashes = {name: hashlib.sha256(pathlib.Path(sys.modules[name].__file__).read_bytes()).hexdigest()
                             for name in ("loopshield.engine", "loopshield.fhir")}
    return {"protocol": "E-ROBUST-01", "synthetic_only": True,
            "implementation_file_sha256": implementation_hashes,
            "measurement_file_sha256": hashlib.sha256(pathlib.Path(__file__).read_bytes()).hexdigest(),
            "total": len(checks), "passed": sum(c["pass"] for c in checks),
            "checks": checks, "default_scenario_sha256": default_scenarios}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=pathlib.Path, required=True)
    parser.add_argument("--require-all", action="store_true")
    args = parser.parse_args()
    result = run_checks()
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    print(json.dumps({"total": result["total"], "passed": result["passed"],
                      "failed": [c["name"] for c in result["checks"] if not c["pass"]]}))
    if args.require_all and result["passed"] != result["total"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
