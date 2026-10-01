#!/usr/bin/env python3
"""
Pass/fail policy for the OWASP ZAP baseline reports.

    zap_gate.py ACCEPTED_TSV REPORT.json [REPORT.json ...]

- High risk: always fails. It cannot be accepted.
- Medium risk: fails unless its plugin id is listed in ACCEPTED_TSV with a written reason.
- Low and Informational: listed in the summary, never fail the build.
- Alerts ZAP itself marks as false positives (confidence 0) are ignored.

An accepted entry that no longer appears is reported as stale, so the list does not rot.
Writes a Markdown summary to $GITHUB_STEP_SUMMARY when it is set.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

RISK = {3: "High", 2: "Medium", 1: "Low", 0: "Informational"}


def load_accepted(path: Path) -> dict[str, str]:
    accepted = {}
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        plugin, _, reason = line.partition("\t")
        if not reason.strip():
            sys.exit(f"zap_gate: {path}: plugin {plugin} is accepted without a reason")
        accepted[plugin.strip()] = reason.strip()
    return accepted


def alerts(report: Path):
    data = json.loads(report.read_text(encoding="utf-8"))
    for site in data.get("site", []):
        for alert in site.get("alerts", []):
            if int(alert.get("confidence", 1)) == 0:
                continue
            yield {
                "pass": report.stem.removeprefix("zap-"),
                "id": str(alert["pluginid"]),
                "name": alert.get("name") or alert.get("alert", "?"),
                "risk": int(alert["riskcode"]),
                "count": int(alert.get("count") or len(alert.get("instances", []))),
                "example": (alert.get("instances") or [{}])[0].get("uri", ""),
            }


def main(argv: list[str]) -> int:
    if len(argv) < 3:
        print(__doc__)
        return 2
    accepted = load_accepted(Path(argv[1]))
    found = [a for report in argv[2:] for a in alerts(Path(report))]
    failing = [a for a in found if a["risk"] == 3 or (a["risk"] == 2 and a["id"] not in accepted)]
    seen_ids = {a["id"] for a in found}
    stale = sorted(set(accepted) - seen_ids)

    lines = ["## OWASP ZAP baseline", ""]
    if found:
        lines += ["| Pass | Risk | Plugin | Alert | Instances | Status |", "|---|---|---|---|---|---|"]
        for a in sorted(found, key=lambda a: (-a["risk"], a["pass"], a["id"])):
            if a in failing:
                status = "**FAIL**"
            elif a["risk"] == 2:
                status = f"accepted: {accepted[a['id']]}"
            else:
                status = "reported"
            lines.append(f"| {a['pass']} | {RISK[a['risk']]} | {a['id']} | {a['name']} | {a['count']} | {status} |")
    else:
        lines.append("No alerts.")
    if stale:
        lines += ["", f"Accepted entries no longer raised (remove from .zap/accepted.tsv): {', '.join(stale)}"]
    verdict = "FAIL" if failing else "PASS"
    lines += [
        "",
        f"**Result: {verdict}** ({len(failing)} blocking alert(s); High never passes, Medium only if accepted)",
    ]
    summary = "\n".join(lines)
    print(summary)
    if os.environ.get("GITHUB_STEP_SUMMARY"):
        with open(os.environ["GITHUB_STEP_SUMMARY"], "a", encoding="utf-8") as fh:
            fh.write(summary + "\n")
    return 1 if failing else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
