# SPDX-FileCopyrightText: 2026 Francisco Angulo de Lafuente
# SPDX-License-Identifier: MIT
# Research-Project: LoopShield
# Research-Author: Francisco Angulo de Lafuente
# Research-ORCID: https://orcid.org/0009-0001-1634-7063
# Research-Date: 2026-11-07
"""Export a case as FHIR R4 resources (Task + Communication + Provenance) for exchange between providers.

Plain dictionaries, no FHIR library. Scenario bundles pass the official HL7 FHIR Validator against base R4
(experiment E-FHIR-01, `results/fhir/`); no national or local implementation guide has been tested.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import html
import re

TASK_STATUS = {"ISSUED": "requested", "NOTIFIED": "received", "ACKNOWLEDGED": "accepted",
               "REFERRED": "in-progress", "REFERRAL_ACCEPTED": "in-progress", "BOOKED": "in-progress",
               "ATTENDED": "in-progress", "RESULTED": "in-progress", "CLOSED": "completed",
               "CLOSED_BY_DECISION": "completed"}


BASE_URL = "https://loopshield.example.org/fhir"  # placeholder; a deployment sets its own server base


def _narrative(text: str) -> dict:
    return {"status": "generated",
            "div": f'<div xmlns="http://www.w3.org/1999/xhtml">{html.escape(text)}</div>'}


def _iso(origin: dt.datetime, days: float) -> str:
    # Engine time is elapsed days from the origin. Naive origins retain the existing UTC convention.
    utc = origin.replace(tzinfo=dt.timezone.utc) if origin.utcoffset() is None else origin.astimezone(dt.timezone.utc)
    return (utc + dt.timedelta(days=days)).isoformat().replace("+00:00", "Z")


def _resource_stem(case_id: str) -> str:
    """Keep short safe case IDs; derive bounded opaque IDs for everything else.

    Reserve the sha256- namespace so a literal case ID cannot alias an encoded one. A deployment must
    still use pseudonymous case IDs: the hash is an identifier encoding, not an anonymisation claim.
    """
    if not isinstance(case_id, str):
        raise ValueError("FHIR export needs a string case_id")
    if re.fullmatch(r"[A-Za-z0-9-.]{1,40}", case_id) and not case_id.startswith("sha256-"):
        return "loop-" + case_id
    return "loop-sha256-" + hashlib.sha256(case_id.encode("utf-8")).hexdigest()[:32]


def case_bundle(case, origin: dt.datetime | None = None, patient_ref: str = "Patient/pseudonymous") -> dict:
    origin = origin or dt.datetime(2026, 1, 1)
    stem = _resource_stem(case.case_id)
    task = {
        "resourceType": "Task",
        "id": stem,
        "status": TASK_STATUS[case.state],
        "intent": "order",
        "priority": "urgent" if case.urgent else "routine",
        "code": {"text": case.pathway.title},
        "businessStatus": {"text": case.state},
        "for": {"reference": patient_ref},
        "authoredOn": _iso(origin, case.issued_at),
        "lastModified": _iso(origin, case.entered_at),
        "owner": {"display": case.owner_role if case.open else "closed"},
        "text": _narrative(f"{case.pathway.title}: {case.state}"),
    }
    if case.due_at is not None:
        task["restriction"] = {"period": {"end": _iso(origin, case.due_at)}}
    if case.closure:
        task["output"] = [{"type": {"text": k}, "valueString": str(v)} for k, v in case.closure.items()]
    # Escalations are alerts the engine has raised. This prototype has no delivery channel, so they are exported as
    # Communications in "preparation" (created, not sent); a delivery integration must set "completed" and `sent`
    # only after confirmed delivery.
    comms = [{
        "resourceType": "Communication", "id": f"{stem}-alert-{i}", "status": "preparation",
        "text": _narrative(f"Alert level {e['level']} to {e['to']}; delivery not confirmed"),
        "partOf": [{"reference": f"Task/{task['id']}"}],
        "recipient": [{"display": e["to"]}],
        "note": [{"text": f"alert raised by the engine at {_iso(origin, e['t'])}; delivery not confirmed"}],
        "payload": [{"contentString": f"escalation level {e['level']} ({e['reason']}) at step {e['step']}"}],
    } for i, e in enumerate(case.escalations)]
    prov = {"resourceType": "Provenance", "id": f"{stem}-provenance",
            "text": _narrative("Recorded by the LoopShield engine"), "target": [{"reference": f"Task/{task['id']}"}],
            "recorded": _iso(origin, case.entered_at),
            "agent": [{"who": {"display": "LoopShield engine"}}]}
    return {"resourceType": "Bundle", "type": "collection",
            "entry": [{"fullUrl": f"{BASE_URL}/{r['resourceType']}/{r['id']}", "resource": r}
                      for r in [task, *comms, prov]]}
