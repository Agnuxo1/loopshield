"""E-PHI: how much PHI in a clinician note would reach an external model (pre-registered).

Data: Gretel gretel-pii-masking-en-v1 (Apache-2.0), test split, health domains. Systems: raw,
Presidio (default English, spaCy en_core_web_lg), NAVAJO v1, NAVAJO v2 (own technology, frozen),
hybrid v2 + Presidio. Scoring follows the edge-privacy-gateway benchmark (MIT) at character level.

    python bench/phi_payload.py --parquet test.parquet --out results/phi [--no-presidio]
"""
from __future__ import annotations

import argparse
import ast
import hashlib
import json
import os
import platform
import re
import sys
import time

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, ".."))
sys.path.insert(0, os.path.join(HERE, "..", "vendor"))

from loopshield import FIT_POSITIVE, CaseEngine  # noqa: E402
from loopshield.navajo_v2 import NavajoV2  # noqa: E402
from loopshield.privacy import PrivacyGateway, PrivacyRefusal  # noqa: E402

# HIPAA Safe Harbor identifiers as named in Gretel/Nemotron (from edge-privacy-gateway bench/common.py, MIT)
PHI = {"first_name", "last_name", "medical_record_number", "date_of_birth", "date", "date_time",
       "health_plan_beneficiary_number", "email", "phone_number", "fax_number", "biometric_identifier",
       "street_address", "city", "county", "postcode", "coordinate", "certificate_license_number", "url",
       "ipv4", "ipv6", "credit_debit_card", "account_number", "bank_routing_number", "employee_id",
       "national_id", "ssn", "tax_id", "unique_id", "customer_id", "mac_address", "user_name",
       "license_plate", "vehicle_identifier", "device_identifier", "name", "address", "credit_card_number",
       "unique_identifier"}
CLINICAL = re.compile(
    r"\b\d{1,3}(?:[.,]\d+)?(?:/\d{1,3})?\s?(?:mmHg|mg/dL|mmol/L|bpm|mg|mcg|µg|g/dL|mL|kg|lbs?|"
    r"°[CF]|%|IU|units?|breaths/min|kcal|steps|hours?|hrs?)\b", re.IGNORECASE)
LEX = os.path.join(HERE, "..", "assets", "lexicon_train.json")


def load_docs(parquet):
    import pyarrow.parquet as pq
    tab = pq.read_table(parquet).to_pylist()
    docs = []
    for r in tab:
        if "health" not in (r["domain"] or "").lower():
            continue
        text = r["text"]
        spans = []
        for ent in ast.literal_eval(r["entities"]):
            val = ent["entity"]
            if not val:
                continue
            for lab in ent["types"]:
                for m in re.finditer(re.escape(val), text):
                    spans.append((m.start(), m.end(), lab))
        docs.append({"uid": r["uid"], "domain": r["domain"], "text": text, "gold": spans})
    return docs


def cover(spans, n):
    m = np.zeros(n, dtype=bool)
    for s, e in spans:
        m[max(0, s):min(n, e)] = True
    return m


def doc_metrics(doc, pred):
    t = doc["text"]
    n = len(t)
    pm = cover(pred, n)
    phi = [(s, e) for s, e, lab in doc["gold"] if lab in PHI]
    allg = cover([(s, e) for s, e, _ in doc["gold"]], n)
    phim = cover(phi, n)
    ents_full_visible = sum(1 for s, e in phi if not pm[s:e].any())
    clin = [(m.start(), m.end()) for m in CLINICAL.finditer(t) if not allg[m.start():m.end()].any()]
    return {"phi_chars": int(phim.sum()), "phi_visible": int((phim & ~pm).sum()),
            "pred_chars": int(pm.sum()), "pred_in_gold": int((pm & allg).sum()),
            "ents": len(phi), "ents_full_visible": ents_full_visible,
            "doc_any_full_visible": int(ents_full_visible > 0),
            "clin": len(clin), "clin_kept": sum(1 for s, e in clin if not pm[s:e].any())}


def aggregate(rows):
    s = {k: sum(r[k] for r in rows) for k in rows[0]}
    return {"E_exposure": s["phi_visible"] / max(1, s["phi_chars"]),
            "precision": s["pred_in_gold"] / max(1, s["pred_chars"]),
            "entities_fully_visible": s["ents_full_visible"] / max(1, s["ents"]),
            "docs_with_full_visible_entity": s["doc_any_full_visible"] / len(rows),
            "clinical_kept": s["clin_kept"] / max(1, s["clin"]), "clinical_n": s["clin"],
            "docs": len(rows), "phi_chars": s["phi_chars"]}


def paired_bootstrap(a_rows, b_rows, seed, reps=1000):
    rng = np.random.default_rng(seed)
    av = np.array([[r["phi_visible"], r["phi_chars"]] for r in a_rows], dtype=float)
    bv = np.array([[r["phi_visible"], r["phi_chars"]] for r in b_rows], dtype=float)
    n = len(av)
    diffs = []
    for _ in range(reps):
        idx = rng.integers(0, n, n)
        a, b = av[idx].sum(0), bv[idx].sum(0)
        diffs.append(a[0] / max(1, a[1]) - b[0] / max(1, b[1]))
    return [float(np.percentile(diffs, 2.5)), float(np.percentile(diffs, 97.5))]


def systems(use_presidio):
    from navajo_egp.detector import PIIDetector
    v1d = PIIDetector(use_spacy=False)

    def v1(t):
        try:
            return [(e.start, e.end) for e in v1d.detect(t)]
        except Exception:      # v1 is known to crash on some inputs; counts as nothing masked
            return []
    v2d = NavajoV2(LEX)
    out = {"raw": lambda t: [], "navajo_v1": v1, "navajo_v2": v2d.detect}
    if use_presidio:
        from presidio_analyzer import AnalyzerEngine
        an = AnalyzerEngine()
        pres = lambda t: [(r.start, r.end) for r in an.analyze(text=t, language="en")]  # noqa: E731
        out["presidio"] = pres
        out["hybrid_v2+presidio"] = lambda t: v2d.detect(t) + pres(t)
    return out


def main(parquet, out, use_presidio=True):
    os.makedirs(out, exist_ok=True)
    docs = load_docs(parquet)
    sysd = systems(use_presidio)
    per = {}
    timing = {}
    for name, f in sysd.items():
        t0 = time.perf_counter()
        per[name] = [doc_metrics(d, f(d["text"])) for d in docs]
        timing[name] = 1000 * (time.perf_counter() - t0) / len(docs)
    part = [int(hashlib.sha256(d["uid"].encode()).hexdigest(), 16) % 3 for d in docs]
    res = {}
    for name, rows in per.items():
        agg = aggregate(rows)
        parts = [aggregate([r for r, p in zip(rows, part) if p == k])["E_exposure"] for k in range(3)]
        agg["E_partitions_mean"], agg["E_partitions_sd"] = float(np.mean(parts)), float(np.std(parts, ddof=1))
        agg["ms_per_doc"] = timing[name]
        res[name] = agg
    tests = {}
    if use_presidio:
        for a in ("navajo_v2", "hybrid_v2+presidio"):
            d = res[a]["E_exposure"] - res["presidio"]["E_exposure"]
            tests[f"{a} - presidio"] = {"diff": d, "ci95_seeds_0_1_2": [paired_bootstrap(per[a], per["presidio"], s)
                                                                       for s in (0, 1, 2)]}
    # Payload level: how often the gateway would refuse to send (hard identifier survived masking)
    gw = PrivacyGateway()
    eng = CaseEngine(audit=False)
    case = eng.open_case("bench", FIT_POSITIVE, 0.0)
    refused = 0
    for d in docs:
        try:
            gw.build_request(case, d["text"])
        except PrivacyRefusal:
            refused += 1
    meta = {"docs": len(docs), "domains": sorted({d["domain"] for d in docs}),
            "python": platform.python_version(), "platform": platform.platform(),
            "gateway_refusal_rate_v2": refused / len(docs)}
    from importlib.metadata import PackageNotFoundError, version
    for pkg in ("presidio-analyzer", "spacy", "en_core_web_lg", "numpy", "pyarrow"):
        try:
            meta[pkg] = version(pkg)
        except PackageNotFoundError:
            meta[pkg] = None
    with open(os.path.join(out, "phi_results.json"), "w") as f:
        json.dump({"meta": meta, "systems": res, "tests": tests}, f, indent=1)
    with open(os.path.join(out, "phi_rows.json"), "w") as f:
        json.dump({"uids": [d["uid"] for d in docs], "per": per}, f)
    return meta, res, tests


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--parquet", required=True)
    ap.add_argument("--out", default="results/phi")
    ap.add_argument("--no-presidio", action="store_true")
    a = ap.parse_args()
    meta, res, tests = main(a.parquet, a.out, not a.no_presidio)
    print(json.dumps(meta))
    for k, v in res.items():
        print(k, {m: round(x, 4) if isinstance(x, float) else x for m, x in v.items()})
    print(json.dumps(tests, indent=1))
