#!/usr/bin/env python3
"""
CARTA Engine Mathematical Verification
Tests signal weights, combo multipliers, thresholds, and computes:
  - TP, TN, FP, FN, Precision, Recall, F1
  - False Positive Rate (FPR), False Negative Rate (FNR)
  - ROC curve and AUC vs random baseline
No Docker needed — pure math verification.
"""

import json
import math
import statistics
import itertools
from datetime import datetime

# ── CARTA Constants (copied from carta.py) ─────────────────────────────────

SIGNAL_WEIGHTS = {
    "R1_baseline": 0.13,
    "R2_device":   0.10,
    "R3_geo":      0.18,
    "R4_temporal": 0.04,
    "R5_rate":     0.13,
    "R7_cred":     0.35,
    "S2_velocity": 0.07,
}
TOTAL_WEIGHT = sum(SIGNAL_WEIGHTS.values())

COMBO_MULTIPLIERS = {
    ("R3_geo",     "R7_cred"):     1.50,
    ("R2_device",  "R7_cred"):     1.45,
    ("R3_geo",     "R2_device"):   1.35,
    ("R5_rate",    "S2_velocity"): 1.30,
    ("R4_temporal","R5_rate"):     1.25,
    ("R2_device",  "R5_rate"):     1.20,
    ("R1_baseline","R2_device"):   1.15,
    ("R3_geo",     "R5_rate"):     1.30,
    ("R1_baseline","R7_cred"):     1.45,
}

THRESHOLD_FLAG  = 0.20
THRESHOLD_MFA   = 0.40
THRESHOLD_BLOCK = 0.80

# ── CARTA Functions (reproduced exactly from carta.py) ─────────────────────

def compute_request_score(signals: dict) -> tuple:
    weighted_sum = sum(
        SIGNAL_WEIGHTS.get(k, 0.0) * v
        for k, v in signals.items()
    )
    score = weighted_sum / TOTAL_WEIGHT
    active = [k for k, v in signals.items() if v > 0]
    return round(min(max(score, 0.0), 1.0), 4), active


def apply_combo_multipliers(base_score: float, active_signals: list) -> tuple:
    M = 1.0
    combos = []
    for (sig_a, sig_b), factor in COMBO_MULTIPLIERS.items():
        if sig_a in active_signals and sig_b in active_signals:
            M *= factor
            combos.append(f"COMBO:{sig_a}+{sig_b}(×{factor})")
    if M == 1.0:
        return base_score, []
    final = 1.0 - (1.0 - base_score) ** M
    return round(min(final, 1.0), 4), combos


def get_action(rho: float, r7_firing: bool = False) -> str:
    policy_score = rho
    if r7_firing:
        policy_score = max(policy_score, THRESHOLD_MFA)
    if policy_score >= THRESHOLD_BLOCK:
        return "block"
    elif policy_score >= THRESHOLD_MFA:
        return "mfa"
    elif policy_score >= THRESHOLD_FLAG:
        return "flag"
    else:
        return "allow"


def run_carta(signals: dict) -> dict:
    base_score, active = compute_request_score(signals)
    final_score, combos = apply_combo_multipliers(base_score, active)
    r7_firing = signals.get("R7_cred", 0.0) == 1.0
    action = get_action(final_score, r7_firing)
    return {
        "rho":     final_score,
        "action":  action,
        "active":  active,
        "combos":  combos,
        "flagged": action != "allow",
    }


# ── Test Case Definitions ───────────────────────────────────────────────────

def make_signals(**kwargs):
    s = {k: 0.0 for k in SIGNAL_WEIGHTS}
    s.update(kwargs)
    return s


# Ground truth: True = threat, False = benign
TEST_CASES = [
    # ── BENIGN (ground truth = False) ──────────────────────────────────────
    {
        "name": "Clean baseline",
        "signals": make_signals(),
        "is_threat": False,
        "description": "All signals zero — legitimate user"
    },
    {
        "name": "Night access only (R4=0.5)",
        "signals": make_signals(R4_temporal=0.5),
        "is_threat": False,
        "description": "Working late — R4 partial, below flag threshold"
    },
    {
        "name": "Mild rate (R5=0.3)",
        "signals": make_signals(R5_rate=0.3),
        "is_threat": False,
        "description": "Slightly elevated submission rate — not anomalous"
    },
    {
        "name": "Small resource spike (R1=0.3)",
        "signals": make_signals(R1_baseline=0.3),
        "is_threat": False,
        "description": "Moderate resource usage — within normal range"
    },
    {
        "name": "Known device, night (R4=0.5, R2=0)",
        "signals": make_signals(R4_temporal=0.5),
        "is_threat": False,
        "description": "Night work from known device — acceptable"
    },
    {
        "name": "1 failed login (R7=0)",
        "signals": make_signals(),
        "is_threat": False,
        "description": "Single failed login — below R7 threshold"
    },

    # ── THREATS (ground truth = True) ──────────────────────────────────────
    {
        "name": "Credential attack (R7=1.0)",
        "signals": make_signals(R7_cred=1.0),
        "is_threat": True,
        "description": "5+ failed logins — brute force detected"
    },
    {
        "name": "Rate flood (R5=1.0)",
        "signals": make_signals(R5_rate=1.0),
        "is_threat": True,
        "description": "Excessive submission rate — automated attack"
    },
    {
        "name": "New device (R2=1.0)",
        "signals": make_signals(R2_device=1.0),
        "is_threat": True,
        "description": "Unrecognized device fingerprint"
    },
    {
        "name": "Resource abuse (R1=1.0)",
        "signals": make_signals(R1_baseline=1.0),
        "is_threat": True,
        "description": "Massive resource spike vs personal baseline"
    },
    {
        "name": "Account takeover (R2+R7 combo)",
        "signals": make_signals(R2_device=1.0, R7_cred=1.0),
        "is_threat": True,
        "description": "New device + failed logins → account takeover"
    },
    {
        "name": "Bot confirmed (R5+S2 combo)",
        "signals": make_signals(R5_rate=1.0, S2_velocity=1.0),
        "is_threat": True,
        "description": "High rate + regular timing → automated bot"
    },
    {
        "name": "Remote attacker (R3+R2 combo)",
        "signals": make_signals(R3_geo=1.0, R2_device=1.0),
        "is_threat": True,
        "description": "Foreign location + new device → remote attacker"
    },
    {
        "name": "Foreign + credential (R3+R7 combo)",
        "signals": make_signals(R3_geo=1.0, R7_cred=1.0),
        "is_threat": True,
        "description": "Foreign location + failed logins → highest severity"
    },
    {
        "name": "Off-hours bot (R4+R5 combo)",
        "signals": make_signals(R4_temporal=1.0, R5_rate=1.0),
        "is_threat": True,
        "description": "Night hours + high rate → automated off-hours attack"
    },
    {
        "name": "Scripted attack (R2+R5 combo)",
        "signals": make_signals(R2_device=1.0, R5_rate=1.0),
        "is_threat": True,
        "description": "New device + high rate → scripted attack"
    },
    {
        "name": "Full attack (R2+R5+R7)",
        "signals": make_signals(R2_device=1.0, R5_rate=1.0, R7_cred=1.0),
        "is_threat": True,
        "description": "Multiple signals + combos → severe threat"
    },
    {
        "name": "Critical (R3+R7+R5)",
        "signals": make_signals(R3_geo=1.0, R7_cred=1.0, R5_rate=1.0),
        "is_threat": True,
        "description": "Foreign + credential + rate → critical attack"
    },
]


# ── Confusion Matrix ────────────────────────────────────────────────────────

def evaluate_confusion_matrix(test_cases: list, threshold_action="flag") -> dict:
    """
    TP: threat correctly detected (action != allow)
    TN: benign correctly allowed (action == allow)
    FP: benign incorrectly flagged (action != allow)
    FN: threat incorrectly allowed (action == allow)
    """
    TP = TN = FP = FN = 0
    details = []

    for tc in test_cases:
        result = run_carta(tc["signals"])
        predicted_threat = result["action"] != "allow"
        actual_threat    = tc["is_threat"]

        if actual_threat and predicted_threat:
            label = "TP"
            TP += 1
        elif not actual_threat and not predicted_threat:
            label = "TN"
            TN += 1
        elif not actual_threat and predicted_threat:
            label = "FP"
            FP += 1
        else:
            label = "FN"
            FN += 1

        details.append({
            "name":           tc["name"],
            "is_threat":      actual_threat,
            "predicted":      predicted_threat,
            "label":          label,
            "rho":            result["rho"],
            "action":         result["action"],
            "active_signals": result["active"],
        })

    precision = TP / (TP + FP) if (TP + FP) > 0 else 0
    recall    = TP / (TP + FN) if (TP + FN) > 0 else 0
    f1        = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0
    fpr       = FP / (FP + TN) if (FP + TN) > 0 else 0
    fnr       = FN / (FN + TP) if (FN + TP) > 0 else 0
    accuracy  = (TP + TN) / len(test_cases)

    return {
        "TP": TP, "TN": TN, "FP": FP, "FN": FN,
        "precision": precision,
        "recall":    recall,
        "f1":        f1,
        "fpr":       fpr,
        "fnr":       fnr,
        "accuracy":  accuracy,
        "details":   details,
    }


# ── ROC Curve ──────────────────────────────────────────────────────────────

def compute_roc_curve(test_cases: list) -> dict:
    """
    Sweep threshold from 0 to 1 and compute TPR/FPR at each point.
    Also compute AUC using trapezoidal rule.
    """
    # Get rho scores for all test cases
    scores = []
    for tc in test_cases:
        result = run_carta(tc["signals"])
        scores.append((result["rho"], tc["is_threat"]))

    thresholds = sorted(set([s[0] for s in scores] + [0.0, 1.0]))
    roc_points = []

    for thresh in thresholds:
        TP = TN = FP = FN = 0
        for rho, is_threat in scores:
            predicted = rho >= thresh
            if is_threat and predicted:     TP += 1
            elif not is_threat and not predicted: TN += 1
            elif not is_threat and predicted: FP += 1
            else:                            FN += 1

        tpr = TP / (TP + FN) if (TP + FN) > 0 else 0
        fpr = FP / (FP + TN) if (FP + TN) > 0 else 0
        roc_points.append({"threshold": thresh, "tpr": tpr, "fpr": fpr})

    # Sort by FPR for AUC calculation
    roc_points.sort(key=lambda x: x["fpr"])

    # AUC via trapezoidal rule
    auc = 0.0
    for i in range(1, len(roc_points)):
        dx = roc_points[i]["fpr"] - roc_points[i-1]["fpr"]
        dy = (roc_points[i]["tpr"] + roc_points[i-1]["tpr"]) / 2
        auc += dx * dy

    # Random baseline AUC = 0.5
    return {
        "roc_points": roc_points,
        "auc":        round(auc, 4),
        "auc_baseline": 0.5,
        "auc_improvement": round(auc - 0.5, 4),
    }


# ── Combo Verification ─────────────────────────────────────────────────────

def verify_all_combos() -> list:
    results = []
    for (sig_a, sig_b), factor in COMBO_MULTIPLIERS.items():
        # Test with both signals at 1.0
        signals = make_signals(**{sig_a: 1.0, sig_b: 1.0})
        base, active = compute_request_score(signals)
        final, combos = apply_combo_multipliers(base, active)

        # Manual verification
        expected_base  = (SIGNAL_WEIGHTS[sig_a] + SIGNAL_WEIGHTS[sig_b]) / TOTAL_WEIGHT
        expected_final = 1.0 - (1.0 - expected_base) ** factor
        match = abs(final - round(min(expected_final, 1.0), 4)) < 0.001

        results.append({
            "combo":          f"{sig_a} + {sig_b}",
            "factor":         factor,
            "base_score":     round(base, 4),
            "expected_base":  round(expected_base, 4),
            "final_score":    final,
            "expected_final": round(min(expected_final, 1.0), 4),
            "verified":       match,
            "combo_fired":    len(combos) > 0,
        })
    return results


# ── Signal Weight Verification ─────────────────────────────────────────────

def verify_signal_weights() -> list:
    results = []
    for sig_name, weight in SIGNAL_WEIGHTS.items():
        signals = make_signals(**{sig_name: 1.0})
        computed, _ = compute_request_score(signals)
        expected = weight / TOTAL_WEIGHT
        match = abs(computed - round(expected, 4)) < 0.001
        results.append({
            "signal":   sig_name,
            "weight":   weight,
            "expected_rho": round(expected, 4),
            "computed_rho": computed,
            "verified": match,
        })
    return results


# ── Threshold Boundary Tests ───────────────────────────────────────────────

def verify_thresholds() -> list:
    results = []
    boundaries = [
        (THRESHOLD_FLAG - 0.001,  "allow",  "just below flag"),
        (THRESHOLD_FLAG,          "flag",   "exactly at flag"),
        (THRESHOLD_FLAG + 0.001,  "flag",   "just above flag"),
        (THRESHOLD_MFA - 0.001,   "flag",   "just below mfa"),
        (THRESHOLD_MFA,           "mfa",    "exactly at mfa"),
        (THRESHOLD_MFA + 0.001,   "mfa",    "just above mfa"),
        (THRESHOLD_BLOCK - 0.001, "mfa",    "just below block"),
        (THRESHOLD_BLOCK,         "block",  "exactly at block"),
        (THRESHOLD_BLOCK + 0.001, "block",  "just above block"),
    ]
    for rho, expected_action, label in boundaries:
        actual_action = get_action(rho)
        results.append({
            "label":           label,
            "rho":             rho,
            "expected_action": expected_action,
            "actual_action":   actual_action,
            "verified":        actual_action == expected_action,
        })
    return results


# ── Main ───────────────────────────────────────────────────────────────────

def main():
    print(f"{'='*65}")
    print(f"  CARTA Engine Mathematical Verification")
    print(f"  Started : {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'='*65}\n")

    results = {}

    # ── 1. Signal Weight Verification ────────────────────────────────────
    print("[ 1 ] Signal Weight Verification")
    print(f"  TOTAL_WEIGHT = {TOTAL_WEIGHT:.2f}")
    weight_results = verify_signal_weights()
    all_pass = True
    for r in weight_results:
        status = "✓" if r["verified"] else "✗"
        print(f"  {status} {r['signal']:20s} w={r['weight']:.2f}  "
              f"expected_ρ={r['expected_rho']:.4f}  computed_ρ={r['computed_rho']:.4f}")
        if not r["verified"]:
            all_pass = False
    print(f"  Result: {'ALL VERIFIED ✓' if all_pass else 'FAILURES DETECTED ✗'}\n")
    results["weight_verification"] = weight_results

    # ── 2. Combo Multiplier Verification ─────────────────────────────────
    print("[ 2 ] Combo Multiplier Verification")
    print(f"  Formula: final = 1 - (1 - base)^M")
    combo_results = verify_all_combos()
    all_pass = True
    for r in combo_results:
        status = "✓" if r["verified"] else "✗"
        fired  = "FIRED" if r["combo_fired"] else "NOT FIRED"
        print(f"  {status} {r['combo']:35s} ×{r['factor']:.2f}  "
              f"base={r['base_score']:.4f}  "
              f"final={r['final_score']:.4f}  "
              f"expected={r['expected_final']:.4f}  [{fired}]")
        if not r["verified"]:
            all_pass = False
    print(f"  Result: {'ALL VERIFIED ✓' if all_pass else 'FAILURES DETECTED ✗'}\n")
    results["combo_verification"] = combo_results

    # ── 3. Threshold Boundary Verification ───────────────────────────────
    print("[ 3 ] Threshold Boundary Verification")
    threshold_results = verify_thresholds()
    all_pass = True
    for r in threshold_results:
        status = "✓" if r["verified"] else "✗"
        print(f"  {status} ρ={r['rho']:.3f}  {r['label']:25s}  "
              f"expected={r['expected_action']:5s}  actual={r['actual_action']}")
        if not r["verified"]:
            all_pass = False
    print(f"  Result: {'ALL VERIFIED ✓' if all_pass else 'FAILURES DETECTED ✗'}\n")
    results["threshold_verification"] = threshold_results

    # ── 4. Confusion Matrix ───────────────────────────────────────────────
    print("[ 4 ] Confusion Matrix (18 test cases)")
    cm = evaluate_confusion_matrix(TEST_CASES)

    print(f"\n  {'─'*50}")
    print(f"  Confusion Matrix:")
    print(f"  {'─'*50}")
    print(f"                    Predicted THREAT  Predicted BENIGN")
    print(f"  Actual THREAT   :      TP={cm['TP']:2d}               FN={cm['FN']:2d}")
    print(f"  Actual BENIGN   :      FP={cm['FP']:2d}               TN={cm['TN']:2d}")
    print(f"  {'─'*50}")
    print(f"  Accuracy  : {cm['accuracy']:.4f}  ({cm['accuracy']*100:.1f}%)")
    print(f"  Precision : {cm['precision']:.4f}  (of flagged, how many real threats)")
    print(f"  Recall    : {cm['recall']:.4f}  (of threats, how many caught)")
    print(f"  F1 Score  : {cm['f1']:.4f}")
    print(f"  FPR       : {cm['fpr']:.4f}  (false alarm rate)")
    print(f"  FNR       : {cm['fnr']:.4f}  (missed threat rate)")

    print(f"\n  Per-case breakdown:")
    for d in cm["details"]:
        icon = {"TP":"🟢","TN":"🟢","FP":"🔴","FN":"🔴"}[d["label"]]
        print(f"  {icon} [{d['label']}] {d['name']:40s} ρ={d['rho']:.3f} → {d['action']}")

    results["confusion_matrix"] = {k: v for k, v in cm.items() if k != "details"}
    results["confusion_matrix_details"] = cm["details"]

    # ── 5. ROC Curve + AUC ────────────────────────────────────────────────
    print(f"\n[ 5 ] ROC Curve & AUC")
    roc = compute_roc_curve(TEST_CASES)

    print(f"\n  AUC (CARTA)    : {roc['auc']:.4f}")
    print(f"  AUC (baseline) : {roc['auc_baseline']:.4f}  (random classifier)")
    print(f"  Improvement    : +{roc['auc_improvement']:.4f} over random")
    print(f"\n  ROC curve points (FPR → TPR):")
    for pt in roc["roc_points"]:
        bar = "█" * int(pt["tpr"] * 20)
        print(f"  τ={pt['threshold']:.3f}  FPR={pt['fpr']:.3f}  TPR={pt['tpr']:.3f}  {bar}")

    results["roc"] = roc

    # ── 6. Summary ────────────────────────────────────────────────────────
    print(f"\n{'='*65}")
    print(f"  VERIFICATION SUMMARY")
    print(f"{'='*65}")
    w_pass = all(r["verified"] for r in weight_results)
    c_pass = all(r["verified"] for r in combo_results)
    t_pass = all(r["verified"] for r in threshold_results)
    print(f"  Signal weights    : {'✓ ALL CORRECT' if w_pass else '✗ ERRORS'}")
    print(f"  Combo multipliers : {'✓ ALL CORRECT' if c_pass else '✗ ERRORS'}")
    print(f"  Thresholds        : {'✓ ALL CORRECT' if t_pass else '✗ ERRORS'}")
    print(f"  Accuracy          : {cm['accuracy']*100:.1f}%")
    print(f"  Precision         : {cm['precision']*100:.1f}%")
    print(f"  Recall            : {cm['recall']*100:.1f}%")
    print(f"  F1 Score          : {cm['f1']:.4f}")
    print(f"  FPR               : {cm['fpr']*100:.1f}%")
    print(f"  FNR               : {cm['fnr']*100:.1f}%")
    print(f"  AUC               : {roc['auc']:.4f} (vs 0.5 random baseline)")

    output = f"benchmark_carta_verification_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    with open(output, "w") as f:
        json.dump(results, f, indent=2, default=str)
    print(f"\n  Results saved to: {output}")
    print(f"{'='*65}\n")


if __name__ == "__main__":
    main()
