#!/usr/bin/env python3
"""
CMU CERT r4.2 evaluation of HPC-ZT's R4 (temporal) and R6 (credential) signals.

Only R4 and R6 are observable from logon.csv alone (R1/R2/R3/S2 require other
log sources). R6 is proxied as "unknown device during the labelled attack
window" — the observable signal of an attacker using stolen credentials from
a machine the legitimate user never used.

Output: cert_eval_results.json + cert_eval_results.csv
"""

import csv
import json
import os
from collections import defaultdict
from datetime import datetime

WEIGHTS = {
    "R4_temporal": 0.04,
    "R6_cred":     0.35,
}
# Full engine weight mass; matches backend/app/core/carta.py where sum(weights)=1.00
TOTAL_WEIGHT = 1.00

THRESHOLD_FLAG  = 0.12
THRESHOLD_MFA   = 0.40
THRESHOLD_BLOCK = 0.80

DATA_DIR   = os.path.dirname(os.path.abspath(__file__))
LOGON_CSV  = os.path.join(DATA_DIR, "r4.2", "logon.csv")
LABELS_CSV = os.path.join(DATA_DIR, "answers", "insiders.csv")


def parse_time(s):
    for fmt in ("%m/%d/%Y %H:%M:%S", "%m/%d/%Y %H:%M"):
        try:
            return datetime.strptime(s.strip(), fmt)
        except ValueError:
            continue
    return None


def load_labels():
    labels = {}
    with open(LABELS_CSV, newline="", encoding="utf-8", errors="replace") as f:
        for row in csv.DictReader(f):
            if row["dataset"].strip() != "4.2":
                continue
            labels[row["user"].strip()] = {
                "scenario": int(row["scenario"]),
                "start": parse_time(row["start"]),
                "end":   parse_time(row["end"]),
            }
    return labels


def load_logons():
    events = defaultdict(list)
    with open(LOGON_CSV, newline="", encoding="utf-8", errors="replace") as f:
        for row in csv.DictReader(f):
            dt = parse_time(row["date"])
            if dt is None:
                continue
            events[row["user"].strip()].append({
                "dt": dt,
                "pc": row["pc"].strip(),
                "activity": row["activity"].strip().lower(),
            })
    return events


def compute_r4_in_window(events, start, end):
    """Off-hours fraction of logons inside [start, end]."""
    logons = [e for e in events
              if e["activity"] == "logon" and start <= e["dt"] <= end]
    if not logons:
        return 0.0
    off = sum(1 for e in logons if e["dt"].hour >= 22 or e["dt"].hour < 6)
    frac = off / len(logons)
    return round(min(frac / 0.30, 1.0), 4)


def compute_r6_unknown_device(events, start, end):
    """
    R6 = 1.0 if any PC used during the attack window never appeared in the
    user's pre-attack baseline; 0.7 if distinct-PC count during the attack
    window is at least 2x the baseline diversity; else 0.0.
    """
    baseline_pcs = set(e["pc"] for e in events
                       if e["activity"] == "logon" and e["dt"] < start)
    attack_pcs   = set(e["pc"] for e in events
                       if e["activity"] == "logon" and start <= e["dt"] <= end)

    if not attack_pcs:
        return 0.0

    novel = attack_pcs - baseline_pcs
    if novel:
        return 1.0

    if baseline_pcs and len(attack_pcs) >= 2 * len(baseline_pcs):
        return 0.7

    return 0.0


def score_user(events, start, end):
    r4 = compute_r4_in_window(events, start, end)
    r6 = compute_r6_unknown_device(events, start, end)
    rho_req = (WEIGHTS["R4_temporal"] * r4 + WEIGHTS["R6_cred"] * r6) / TOTAL_WEIGHT
    rho_pol = rho_req
    if r6 == 1.0:
        rho_pol = max(rho_pol, THRESHOLD_MFA)
    if rho_pol >= THRESHOLD_BLOCK:
        action = "block"
    elif rho_pol >= THRESHOLD_MFA:
        action = "mfa"
    elif rho_pol >= THRESHOLD_FLAG:
        action = "flag"
    else:
        action = "allow"
    return {"R4": r4, "R6": r6,
            "rho_req": round(rho_req, 4),
            "rho_pol": round(rho_pol, 4),
            "action": action,
            "flagged": action != "allow"}


def main():
    print(f"Loading labels from {LABELS_CSV}")
    labels = load_labels()
    print(f"  {len(labels)} r4.2 malicious users found")

    print(f"Loading logon events from {LOGON_CSV}")
    events = load_logons()
    print(f"  {len(events)} unique users in logon.csv\n")

    results = []
    by_scenario = defaultdict(lambda: {"total": 0, "detected": 0})

    for user, meta in sorted(labels.items()):
        ev = events.get(user, [])
        s = score_user(ev, meta["start"], meta["end"])
        sc = meta["scenario"]

        by_scenario[sc]["total"] += 1
        if s["flagged"]:
            by_scenario[sc]["detected"] += 1

        results.append({
            "user": user, "scenario": sc,
            "n_logon_events": len(ev),
            **s,
            "detected": s["flagged"],
        })

    total = len(labels)
    detected = sum(1 for r in results if r["detected"])
    recall = detected / total if total else 0.0

    summary = {
        "dataset": "CMU CERT r4.2",
        "users_evaluated": total,
        "detected": detected,
        "missed": total - detected,
        "recall": round(recall, 4),
        "by_scenario": {str(k): v for k, v in sorted(by_scenario.items())},
        "note": ("Only R4 and R6 are observable from logon.csv. R6 is proxied "
                 "as novel-device-during-labelled-window, matching the "
                 "stolen-credential attack model of CERT r4.2 Scenario 3. "
                 "Benign-user FP/TN are not computable from this labelled subset."),
    }

    out_json = os.path.join(DATA_DIR, "cert_eval_results.json")
    out_csv  = os.path.join(DATA_DIR, "cert_eval_results.csv")

    with open(out_json, "w") as f:
        json.dump({"summary": summary, "per_user": results}, f, indent=2)

    with open(out_csv, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=results[0].keys())
        w.writeheader()
        w.writerows(results)

    print("=== CMU CERT r4.2 evaluation ===")
    print(f"Users evaluated   : {total}")
    print(f"Detected (flagged): {detected}")
    print(f"Missed            : {total - detected}")
    print(f"Recall            : {recall:.4f}\n")
    print("By scenario:")
    for sc, s in sorted(by_scenario.items()):
        print(f"  Scenario {sc}: {s['detected']}/{s['total']} detected")
    print(f"\nWrote {out_json}\nWrote {out_csv}")


if __name__ == "__main__":
    main()
