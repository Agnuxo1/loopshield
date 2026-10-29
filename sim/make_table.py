"""Markdown table of E-SIM results from results/sim/summary.json."""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
src = sys.argv[1] if len(sys.argv) > 1 else os.path.join(HERE, "..", "results", "sim", "summary.json")
d = json.load(open(src))["summary"]


def f(x, s=100):
    return f"{x['mean'] * s:.1f} ± {x['sd'] * s:.1f}"


lines = ["| Scenario | Arm | O1 completed by day 365 (%) | Δ O1 vs usual care (points) [2.5–97.5 pct] "
         "| O2 not done by day 300 (%) | O3 CRC per 1,000 (associational) | O4 silent loss (% of unresolved) "
         "| Escalations per case |", "|---|---|---|---|---|---|---|---|"]
for sc in ("S-low", "S-high"):
    for arm in ("A0-usual", "A1-reminders", "A2-loopshield", "A2-sens-0.0", "A2-sens-4.8", "A2-sens-8.5",
                "A2-sens-12.0"):
        v = d[f"{sc}/{arm}"]
        dd = v.get("diff_O1_vs_usual")
        dtxt = f"{dd['mean'] * 100:+.2f} [{dd['p2.5'] * 100:+.2f}, {dd['p97.5'] * 100:+.2f}]" if dd else "—"
        o4 = "—"
        if "O4_silent_share_of_unresolved" in v:
            o4 = f"{v['O4_silent_share_of_unresolved']['mean'] * 100:.0f}" + (
                " (assumed)" if arm == "A0-usual" else " (measured)")
        esc = f"{v['escalations_per_case']['mean']:.2f}" if "escalations_per_case" in v else "—"
        lines.append(f"| {sc} | {arm} | {f(v['O1_completed_365'])} | {dtxt} | {f(v['O2_not_done_300'])} "
                     f"| {v['O3_crc_per_1000_assoc']['mean']:.1f} | {o4} | {esc} |")
out = os.path.join(os.path.dirname(src), "table.md")
with open(out, "w", encoding="utf-8") as fh:
    fh.write("\n".join(lines) + "\n")
print(out)
