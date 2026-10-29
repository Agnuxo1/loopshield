"""Offline demo: 300 synthetic positive-FIT cases run through the engine, rendered as one HTML board.

    python demo/run_demo.py            # writes demo/out/dashboard.html and demo/out/case_bundle.json

All people, notes and numbers are synthetic. No network, no model, no real data.
"""
from __future__ import annotations

import html
import json
import os
import random
import statistics
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, ".."))

from loopshield import FIT_POSITIVE, CaseEngine, TransitionError  # noqa: E402
from loopshield.fhir import case_bundle  # noqa: E402
from loopshield.messages import patient_message  # noqa: E402
from loopshield.privacy import PrivacyGateway  # noqa: E402

TODAY = 120.0
FORWARD = ["notify", "acknowledge", "refer", "accept_referral", "book", "attend", "result"]
NOTE = ("Called Mr Omar Haddad on 2026-03-02 at +971 50 123 4567 about his FIT result; MRN 55120934. "
        "He works night shifts and asked for a weekend slot. BP 128/82 mmHg, on metformin 500 mg.")


def build(seed: int = 7, n: int = 300):
    rng = random.Random(seed)
    eng = CaseEngine(audit=True)
    plan = []
    for i in range(n):
        t0 = rng.uniform(0, 100)
        cid = f"FIT-{1000 + i}"
        lang = "ar" if rng.random() < 0.45 else "en"
        speed = rng.lognormvariate(0, 0.7)                     # slower or faster than SLA
        stop = len(FORWARD) if rng.random() < 0.7 else rng.randint(0, len(FORWARD) - 1)
        plan.append((t0, cid, lang, speed, stop))
    events = []
    for t0, cid, lang, speed, stop in plan:
        events.append((t0, 0, cid, "open", {"language": lang}))
        t = t0
        for k, step in enumerate(FIT_POSITIVE.steps[:stop]):
            t += step.sla_days * speed * rng.uniform(0.3, 1.1)
            events.append((t, k + 1, cid, FORWARD[k], {}))
            if FORWARD[k] == "book" and rng.random() < 0.12:
                t += 3
                events.append((t, k + 1.5, cid, "no_show", {"reason": "patient did not attend"}))
                t += 5
                events.append((t, k + 1.6, cid, "book", {}))
        if stop == len(FORWARD):
            events.append((t + rng.uniform(1, 10), 9, cid, "close",
                           {"report_ref": f"COL-{cid}", "next_step": rng.choice(["surveillance 3 y", "routine screening 2 y", "treatment referral"])}))
        elif rng.random() < 0.3:
            for j in range(3):
                events.append((t + 10 + 5 * j, 8, cid, "contact_attempt", {"channel": "sms"}))
    events.sort(key=lambda e: (e[0], e[1]))
    for t, _, cid, ev, data in events:
        if t > TODAY:
            continue
        if ev == "open":
            eng.open_case(cid, FIT_POSITIVE, t, language=data["language"])
        else:
            try:
                eng.apply(cid, ev, t, **data)
            except TransitionError:
                pass
    eng.open_case("FIT-URG", FIT_POSITIVE, TODAY, language="ar", urgent=True)
    eng.advance_to(TODAY)
    return eng


def tile(label, value, note=""):
    return (f'<div class="tile"><div class="v">{html.escape(str(value))}</div>'
            f'<div class="l">{html.escape(label)}</div><div class="n">{html.escape(note)}</div></div>')


def render(eng: CaseEngine) -> str:
    cases = list(eng.cases.values())
    open_c = [c for c in cases if c.open]
    closed = [c for c in cases if c.state == "CLOSED"]
    overdue = [c for c in open_c if c.due_at is not None and TODAY > c.due_at]
    silent = [c for c in overdue if not c.escalations]
    ttc = [c.timeline["CLOSED"] - c.issued_at for c in closed]
    board = eng.board(TODAY)
    rows = "".join(
        f"<tr><td>{html.escape(r)}</td><td>{v['open']}</td><td class='{'bad' if v['overdue'] else ''}'>{v['overdue']}</td>"
        f"<td>{v['urgent']}</td></tr>" for r, v in sorted(board.items()))
    worst = sorted(overdue, key=lambda c: (not c.urgent, -(TODAY - c.due_at)))[:12]
    wl = "".join(
        f"<tr><td>{c.case_id}{' <b class=urg>URGENT</b>' if c.urgent else ''}</td><td>{c.state}</td>"
        f"<td>{c.pending_step.state}</td><td>{html.escape(c.owner_role)}</td><td>{TODAY - c.due_at:.0f}</td>"
        f"<td>{c.escalations[-1]['to'] if c.escalations else '-'}</td><td>{c.language}</td></tr>" for c in worst)
    sample = next(c for c in closed if any(e for e in c.escalations)) if any(c.escalations for c in closed) else closed[0]
    tl = "".join(f"<li><b>{s}</b> day {t - sample.issued_at:.1f}</li>" for s, t in sample.timeline.items())
    tl += "".join(f"<li class='esc'>escalated to {e['to']} at step {e['step']}, day {e['t'] - sample.issued_at:.1f}</li>"
                  for e in sample.escalations)
    en_case = next(c for c in open_c if c.language == "en" and c.state == "NOTIFIED")
    ar_case = eng.cases["FIT-URG"]
    gw = PrivacyGateway()
    prompt, mapping = gw.build_request(en_case, NOTE)
    n_map = len(mapping)
    gw.restore("", mapping)
    bundle = case_bundle(sample)
    with open(os.path.join(HERE, "out", "case_bundle.json"), "w", encoding="utf-8") as f:
        json.dump(bundle, f, indent=1)
    css = """
    :root{--bg:#f6f7f9;--card:#fff;--ink:#16202a;--mut:#5b6b7a;--acc:#0b6e69;--bad:#b42318;--line:#e3e7ec}
    @media (prefers-color-scheme:dark){:root{--bg:#0f1418;--card:#171e24;--ink:#e8eef3;--mut:#9aabb8;--acc:#3cc4b9;--bad:#ff6b5e;--line:#26313a}}
    body{margin:0;background:var(--bg);color:var(--ink);font:15px/1.45 system-ui,Segoe UI,Roboto,sans-serif}
    header{padding:22px 24px;border-bottom:1px solid var(--line)} h1{margin:0;font-size:22px} header p{margin:4px 0 0;color:var(--mut)}
    main{max-width:1180px;margin:auto;padding:18px 16px 40px;display:grid;gap:16px}
    .tiles{display:grid;grid-template-columns:repeat(auto-fit,minmax(160px,1fr));gap:12px}
    .tile,.card{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:14px}
    .v{font-size:28px;font-weight:650;color:var(--acc)} .l{font-weight:600} .n{color:var(--mut);font-size:13px}
    .grid2{display:grid;grid-template-columns:repeat(auto-fit,minmax(340px,1fr));gap:16px}
    table{border-collapse:collapse;width:100%;font-size:14px} td,th{padding:6px 8px;border-bottom:1px solid var(--line);text-align:left}
    .bad{color:var(--bad);font-weight:650} .urg{color:var(--bad)} h2{font-size:16px;margin:0 0 10px}
    pre{white-space:pre-wrap;background:var(--bg);padding:10px;border-radius:8px;font-size:12.5px;overflow:auto}
    .ar{direction:rtl;text-align:right;font-size:16px} li.esc{color:var(--bad)} .scroll{overflow-x:auto}
    footer{color:var(--mut);font-size:13px;text-align:center;padding:0 16px 30px}
    """
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>LoopShield board</title><style>{css}</style></head><body>
<header><h1>LoopShield — screening-to-care loop board</h1>
<p>Positive FIT pathway · day {TODAY:.0f} · {len(cases)} synthetic cases · every number on this page is computed by the engine</p></header>
<main>
<section class="tiles">
{tile("Open actionable results", len(open_c))}
{tile("Overdue now", len(overdue), "past the SLA of their current step")}
{tile("Overdue with no alert raised", len(silent), "silent loss; must be 0")}
{tile("Closed with evidence", len(closed), "report + next step recorded")}
{tile("Median days to closure", f"{statistics.median(ttc):.0f}" if ttc else "-")}
{tile("Audit chain", "verified" if eng.audit.verify() else "BROKEN", f"{len(eng.audit.entries)} entries, SHA-256 linked")}
</section>
<section class="grid2">
<div class="card scroll"><h2>Work list by accountable owner</h2><table><tr><th>Owner</th><th>Open</th><th>Overdue</th><th>Urgent</th></tr>{rows}</table></div>
<div class="card"><h2>One case, end to end ({sample.case_id})</h2><ol>{tl}</ol></div>
</section>
<section class="card scroll"><h2>Most overdue (urgent first)</h2><table><tr><th>Case</th><th>State</th><th>Waiting for</th><th>Owner</th><th>Days overdue</th><th>Escalated to</th><th>Lang</th></tr>{wl}</table></section>
<section class="grid2">
<div class="card"><h2>Patient message (English, deterministic template)</h2><p>{html.escape(patient_message(en_case))}</p></div>
<div class="card"><h2>Patient message (Arabic, urgent case; pending native review)</h2><p class="ar" lang="ar">{html.escape(patient_message(ar_case))}</p></div>
</section>
<section class="grid2">
<div class="card"><h2>Clinician note (stays in the hospital)</h2><pre>{html.escape(NOTE)}</pre></div>
<div class="card"><h2>What an external AI model would receive (NAVAJO v2)</h2><pre>{html.escape(prompt)}</pre><p class="n">{n_map} values replaced by placeholders; mapping kept in memory and destroyed after the answer is restored.</p></div>
</section>
<section class="card scroll"><h2>FHIR R4 Task exported for the next provider</h2><pre>{html.escape(json.dumps(bundle['entry'][0]['resource'], indent=1))}</pre></section>
</main><footer>Prototype · synthetic data · not a medical device · LoopShield 0.1 (MIT) built on Project NAVAJO</footer></body></html>"""


if __name__ == "__main__":
    os.makedirs(os.path.join(HERE, "out"), exist_ok=True)
    e = build()
    bad = e.check_invariants()
    page = render(e)
    with open(os.path.join(HERE, "out", "dashboard.html"), "w", encoding="utf-8") as f:
        f.write(page)
    print(json.dumps({"cases": len(e.cases), "invariant_violations": bad, "audit_entries": len(e.audit.entries),
                      "board": e.board(TODAY)}, indent=1))
