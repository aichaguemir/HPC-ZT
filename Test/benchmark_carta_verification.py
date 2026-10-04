#!/usr/bin/env python3

import json
import math
import statistics
from datetime import datetime

# ── CARTA Constants ────────────────────────────────────────────────────────

SIGNAL_WEIGHTS = {
    "R1_baseline": 0.13,
    "R2_device":   0.10,
    "R3_geo":      0.18,
    "R4_temporal": 0.04,
    "R5_rate":     0.13,
    "R6_cred":     0.35,
    "S2_velocity": 0.07,
}
TOTAL_WEIGHT = sum(SIGNAL_WEIGHTS.values())

COMBO_MULTIPLIERS = {
    ("R3_geo",     "R6_cred"):     1.50,
    ("R2_device",  "R6_cred"):     1.45,
    ("R3_geo",     "R2_device"):   1.35,
    ("R5_rate",    "S2_velocity"): 1.30,
    ("R4_temporal","R5_rate"):     1.25,
    ("R2_device",  "R5_rate"):     1.20,
    ("R1_baseline","R2_device"):   1.15,
    ("R3_geo",     "R5_rate"):     1.30,
    ("R1_baseline","R6_cred"):     1.45,
}

THRESHOLD_FLAG  = 0.12
THRESHOLD_MFA   = 0.40
THRESHOLD_BLOCK = 0.80

# ── CARTA Functions ────────────────────────────────────────────────────────

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
    r7_firing = signals.get("R6_cred", 0.0) == 1.0
    action = get_action(final_score, r7_firing)
    return {
        "rho":     final_score,
        "action":  action,
        "active":  active,
        "combos":  combos,
        "flagged": action != "allow",
    }


def make_signals(**kwargs):
    s = {k: 0.0 for k in SIGNAL_WEIGHTS}
    s.update(kwargs)
    return s


# ── 100+ Test Cases ────────────────────────────────────────────────────────

TEST_CASES = [

    # ════════════════════════════════════════════════════════════════
    # BENIGN CASES (ground truth = False) — 40 cases
    # ════════════════════════════════════════════════════════════════

    # Perfect clean cases
    {"name": "B01 Clean baseline",             "signals": make_signals(),                                          "is_threat": False, "category": "benign_clean"},
    {"name": "B02 All zeros explicit",         "signals": make_signals(R1_baseline=0, R2_device=0, R6_cred=0),    "is_threat": False, "category": "benign_clean"},
    {"name": "B03 Known device known IP",      "signals": make_signals(),                                          "is_threat": False, "category": "benign_clean"},
    {"name": "B04 Daytime clean",              "signals": make_signals(R4_temporal=0.0),                           "is_threat": False, "category": "benign_clean"},
    {"name": "B05 Researcher clean session",   "signals": make_signals(),                                          "is_threat": False, "category": "benign_clean"},

    # Mild R4 temporal (night work — partial signal, still below flag)
    {"name": "B06 Night access R4=0.1",        "signals": make_signals(R4_temporal=0.1),                           "is_threat": False, "category": "benign_temporal"},
    {"name": "B07 Night access R4=0.2",        "signals": make_signals(R4_temporal=0.2),                           "is_threat": False, "category": "benign_temporal"},
    {"name": "B08 Night access R4=0.3",        "signals": make_signals(R4_temporal=0.3),                           "is_threat": False, "category": "benign_temporal"},
    {"name": "B09 Night access R4=0.4",        "signals": make_signals(R4_temporal=0.4),                           "is_threat": False, "category": "benign_temporal"},
    {"name": "B10 Night access R4=0.5",        "signals": make_signals(R4_temporal=0.5),                           "is_threat": False, "category": "benign_temporal"},

    # Mild rate signals (slightly elevated but not anomalous)
    {"name": "B11 Mild rate R5=0.1",           "signals": make_signals(R5_rate=0.1),                               "is_threat": False, "category": "benign_rate"},
    {"name": "B12 Mild rate R5=0.2",           "signals": make_signals(R5_rate=0.2),                               "is_threat": False, "category": "benign_rate"},
    {"name": "B13 Mild rate R5=0.3",           "signals": make_signals(R5_rate=0.3),                               "is_threat": False, "category": "benign_rate"},

    # Mild resource signals
    {"name": "B14 Resource R1=0.1",            "signals": make_signals(R1_baseline=0.1),                           "is_threat": False, "category": "benign_resource"},
    {"name": "B15 Resource R1=0.2",            "signals": make_signals(R1_baseline=0.2),                           "is_threat": False, "category": "benign_resource"},
    {"name": "B16 Resource R1=0.3",            "signals": make_signals(R1_baseline=0.3),                           "is_threat": False, "category": "benign_resource"},

    # Single failed login (below R6 threshold)
    {"name": "B17 1 failed login R6=0",        "signals": make_signals(),                                          "is_threat": False, "category": "benign_credential"},
    {"name": "B18 2 failed logins R6=0",       "signals": make_signals(),                                          "is_threat": False, "category": "benign_credential"},

    # Mild velocity
    {"name": "B19 Mild velocity S2=0.1",       "signals": make_signals(S2_velocity=0.1),                           "is_threat": False, "category": "benign_velocity"},
    {"name": "B20 Mild velocity S2=0.2",       "signals": make_signals(S2_velocity=0.2),                           "is_threat": False, "category": "benign_velocity"},

    # Combinations that stay below flag threshold
    {"name": "B21 Low R4+R5",                  "signals": make_signals(R4_temporal=0.2, R5_rate=0.1),              "is_threat": False, "category": "benign_combo"},
    {"name": "B22 Low R1+S2",                  "signals": make_signals(R1_baseline=0.1, S2_velocity=0.1),          "is_threat": False, "category": "benign_combo"},
    {"name": "B23 Low R4+S2",                  "signals": make_signals(R4_temporal=0.3, S2_velocity=0.1),          "is_threat": False, "category": "benign_combo"},
    {"name": "B24 Very low all signals",       "signals": make_signals(R1_baseline=0.05, R4_temporal=0.05, R5_rate=0.05), "is_threat": False, "category": "benign_combo"},
    {"name": "B25 Low R2 partial",             "signals": make_signals(R2_device=0.1),                             "is_threat": False, "category": "benign_combo"},
    {"name": "B26 Low R2+R4",                  "signals": make_signals(R2_device=0.1, R4_temporal=0.2),            "is_threat": False, "category": "benign_combo"},
    {"name": "B27 Low R1+R4",                  "signals": make_signals(R1_baseline=0.1, R4_temporal=0.3),          "is_threat": False, "category": "benign_combo"},
    {"name": "B28 Low R5+S2 no combo",         "signals": make_signals(R5_rate=0.1, S2_velocity=0.1),              "is_threat": False, "category": "benign_combo"},
    {"name": "B29 Low R3 partial",             "signals": make_signals(R3_geo=0.1),                                "is_threat": False, "category": "benign_geo"},
    {"name": "B30 Low R3+R4",                  "signals": make_signals(R3_geo=0.1, R4_temporal=0.2),               "is_threat": False, "category": "benign_geo"},

    # Edge cases just below thresholds
    {"name": "B31 Just below flag R5",         "signals": make_signals(R5_rate=0.3),                               "is_threat": False, "category": "benign_edge"},
    {"name": "B32 Just below flag R1",         "signals": make_signals(R1_baseline=0.3),                           "is_threat": False, "category": "benign_edge"},
    {"name": "B33 Just below flag R3",         "signals": make_signals(R3_geo=0.2),                                "is_threat": False, "category": "benign_edge"},
    {"name": "B34 Just below flag multi",      "signals": make_signals(R4_temporal=0.5, S2_velocity=0.2),          "is_threat": False, "category": "benign_edge"},
    {"name": "B35 Very mild R6=0.3",           "signals": make_signals(R6_cred=0.3),                               "is_threat": False, "category": "benign_edge"},

    # Researcher/admin normal patterns
    {"name": "B36 Normal submission pattern",  "signals": make_signals(R5_rate=0.1, R1_baseline=0.1),              "is_threat": False, "category": "benign_normal"},
    {"name": "B37 Daytime high resource",      "signals": make_signals(R1_baseline=0.2, R5_rate=0.1),              "is_threat": False, "category": "benign_normal"},
    {"name": "B38 Known device night",         "signals": make_signals(R4_temporal=0.4),                           "is_threat": False, "category": "benign_normal"},
    {"name": "B39 Mild all signals",           "signals": make_signals(R1_baseline=0.05, R2_device=0.0, R4_temporal=0.1, R5_rate=0.05, S2_velocity=0.05), "is_threat": False, "category": "benign_normal"},
    {"name": "B40 Clean after previous flag",  "signals": make_signals(),                                          "is_threat": False, "category": "benign_normal"},

    # ════════════════════════════════════════════════════════════════
    # THREAT CASES (ground truth = True) — 65 cases
    # ════════════════════════════════════════════════════════════════

    # R6 credential attacks (single signal)
    {"name": "T01 Brute force R6=0.7",         "signals": make_signals(R6_cred=0.7),                               "is_threat": True, "category": "credential"},
    {"name": "T02 Brute force R6=1.0",         "signals": make_signals(R6_cred=1.0),                               "is_threat": True, "category": "credential"},
    {"name": "T03 Credential R6=0.7 night",    "signals": make_signals(R6_cred=0.7, R4_temporal=0.5),              "is_threat": True, "category": "credential"},
    {"name": "T04 Credential R6=1.0 night",    "signals": make_signals(R6_cred=1.0, R4_temporal=1.0),              "is_threat": True, "category": "credential"},
    {"name": "T05 Credential + rate",          "signals": make_signals(R6_cred=0.7, R5_rate=0.5),                  "is_threat": True, "category": "credential"},

    # R5 rate attacks (single signal)
    {"name": "T06 Rate flood R5=0.7",          "signals": make_signals(R5_rate=0.7),                               "is_threat": True, "category": "rate"},
    {"name": "T07 Rate flood R5=1.0",          "signals": make_signals(R5_rate=1.0),                               "is_threat": True, "category": "rate"},
    {"name": "T08 Rate + temporal",            "signals": make_signals(R5_rate=0.7, R4_temporal=0.5),              "is_threat": True, "category": "rate"},
    {"name": "T09 Rate + resource",            "signals": make_signals(R5_rate=1.0, R1_baseline=0.5),              "is_threat": True, "category": "rate"},
    {"name": "T10 Rate + velocity partial",    "signals": make_signals(R5_rate=0.7, S2_velocity=0.3),              "is_threat": True, "category": "rate"},

    # R2 device attacks (single signal)
    {"name": "T11 New device R2=1.0",          "signals": make_signals(R2_device=1.0),                             "is_threat": True, "category": "device"},
    {"name": "T12 New device + night",         "signals": make_signals(R2_device=1.0, R4_temporal=0.5),            "is_threat": True, "category": "device"},
    {"name": "T13 New device + rate mild",     "signals": make_signals(R2_device=1.0, R5_rate=0.3),                "is_threat": True, "category": "device"},

    # R3 geo attacks (single signal)
    {"name": "T14 Foreign access R3=0.7",      "signals": make_signals(R3_geo=0.7),                                "is_threat": True, "category": "geo"},
    {"name": "T15 Foreign access R3=1.0",      "signals": make_signals(R3_geo=1.0),                                "is_threat": True, "category": "geo"},
    {"name": "T16 Foreign + night",            "signals": make_signals(R3_geo=1.0, R4_temporal=0.5),               "is_threat": True, "category": "geo"},
    {"name": "T17 Foreign + rate mild",        "signals": make_signals(R3_geo=0.7, R5_rate=0.3),                   "is_threat": True, "category": "geo"},

    # R1 resource attacks
    {"name": "T18 Resource spike R1=1.0",      "signals": make_signals(R1_baseline=1.0),                           "is_threat": True, "category": "resource"},
    {"name": "T19 Resource + device",          "signals": make_signals(R1_baseline=1.0, R2_device=0.5),            "is_threat": True, "category": "resource"},
    {"name": "T20 Resource + night",           "signals": make_signals(R1_baseline=1.0, R4_temporal=1.0),          "is_threat": True, "category": "resource"},

    # S2 velocity attacks
    {"name": "T21 Velocity S2=1.0",            "signals": make_signals(S2_velocity=1.0),                           "is_threat": True, "category": "velocity"},
    {"name": "T22 Velocity + rate",            "signals": make_signals(S2_velocity=1.0, R5_rate=0.5),              "is_threat": True, "category": "velocity"},
    {"name": "T23 Velocity + night",           "signals": make_signals(S2_velocity=1.0, R4_temporal=0.5),          "is_threat": True, "category": "velocity"},

    # ── COMBO ATTACKS ──────────────────────────────────────────────
    # R2 + R6 — Account takeover (×1.45)
    {"name": "T24 Account takeover R2+R6 full","signals": make_signals(R2_device=1.0, R6_cred=1.0),                "is_threat": True, "category": "combo_R2_R6"},
    {"name": "T25 Account takeover partial",   "signals": make_signals(R2_device=0.7, R6_cred=0.7),                "is_threat": True, "category": "combo_R2_R6"},
    {"name": "T26 Account takeover + night",   "signals": make_signals(R2_device=1.0, R6_cred=1.0, R4_temporal=1.0), "is_threat": True, "category": "combo_R2_R6"},
    {"name": "T27 Account takeover + rate",    "signals": make_signals(R2_device=1.0, R6_cred=1.0, R5_rate=0.5),   "is_threat": True, "category": "combo_R2_R6"},

    # R3 + R6 — Foreign + credential (×1.50)
    {"name": "T28 Foreign credential full",    "signals": make_signals(R3_geo=1.0, R6_cred=1.0),                   "is_threat": True, "category": "combo_R3_R6"},
    {"name": "T29 Foreign credential partial", "signals": make_signals(R3_geo=0.7, R6_cred=0.7),                   "is_threat": True, "category": "combo_R3_R6"},
    {"name": "T30 Foreign credential + rate",  "signals": make_signals(R3_geo=1.0, R6_cred=1.0, R5_rate=0.5),      "is_threat": True, "category": "combo_R3_R6"},

    # R3 + R2 — Remote attacker (×1.35)
    {"name": "T31 Remote attacker full",       "signals": make_signals(R3_geo=1.0, R2_device=1.0),                 "is_threat": True, "category": "combo_R3_R2"},
    {"name": "T32 Remote attacker partial",    "signals": make_signals(R3_geo=0.7, R2_device=0.7),                 "is_threat": True, "category": "combo_R3_R2"},
    {"name": "T33 Remote attacker + cred",     "signals": make_signals(R3_geo=1.0, R2_device=1.0, R6_cred=0.7),   "is_threat": True, "category": "combo_R3_R2"},

    # R5 + S2 — Bot confirmed (×1.30)
    {"name": "T34 Bot confirmed full",         "signals": make_signals(R5_rate=1.0, S2_velocity=1.0),              "is_threat": True, "category": "combo_R5_S2"},
    {"name": "T35 Bot confirmed partial",      "signals": make_signals(R5_rate=0.7, S2_velocity=0.7),              "is_threat": True, "category": "combo_R5_S2"},
    {"name": "T36 Bot confirmed + night",      "signals": make_signals(R5_rate=1.0, S2_velocity=1.0, R4_temporal=1.0), "is_threat": True, "category": "combo_R5_S2"},
    {"name": "T37 Bot confirmed + device",     "signals": make_signals(R5_rate=1.0, S2_velocity=1.0, R2_device=1.0), "is_threat": True, "category": "combo_R5_S2"},

    # R4 + R5 — Off-hours bot (×1.25)
    {"name": "T38 Off-hours bot full",         "signals": make_signals(R4_temporal=1.0, R5_rate=1.0),              "is_threat": True, "category": "combo_R4_R5"},
    {"name": "T39 Off-hours bot partial",      "signals": make_signals(R4_temporal=0.7, R5_rate=0.7),              "is_threat": True, "category": "combo_R4_R5"},
    {"name": "T40 Off-hours bot + cred",       "signals": make_signals(R4_temporal=1.0, R5_rate=1.0, R6_cred=0.7), "is_threat": True, "category": "combo_R4_R5"},

    # R2 + R5 — Scripted attack (×1.20)
    {"name": "T41 Scripted attack full",       "signals": make_signals(R2_device=1.0, R5_rate=1.0),                "is_threat": True, "category": "combo_R2_R5"},
    {"name": "T42 Scripted attack partial",    "signals": make_signals(R2_device=0.7, R5_rate=0.7),                "is_threat": True, "category": "combo_R2_R5"},
    {"name": "T43 Scripted attack + cred",     "signals": make_signals(R2_device=1.0, R5_rate=1.0, R6_cred=0.7),  "is_threat": True, "category": "combo_R2_R5"},

    # R1 + R2 — Resource abuse (×1.15)
    {"name": "T44 Resource abuse full",        "signals": make_signals(R1_baseline=1.0, R2_device=1.0),            "is_threat": True, "category": "combo_R1_R2"},
    {"name": "T45 Resource abuse partial",     "signals": make_signals(R1_baseline=0.7, R2_device=0.7),            "is_threat": True, "category": "combo_R1_R2"},

    # R3 + R5 — Foreign scripted (×1.30)
    {"name": "T46 Foreign scripted full",      "signals": make_signals(R3_geo=1.0, R5_rate=1.0),                   "is_threat": True, "category": "combo_R3_R5"},
    {"name": "T47 Foreign scripted partial",   "signals": make_signals(R3_geo=0.7, R5_rate=0.7),                   "is_threat": True, "category": "combo_R3_R5"},

    # R1 + R6 — Resource takeover (×1.45)
    {"name": "T48 Resource takeover full",     "signals": make_signals(R1_baseline=1.0, R6_cred=1.0),              "is_threat": True, "category": "combo_R1_R6"},
    {"name": "T49 Resource takeover partial",  "signals": make_signals(R1_baseline=0.7, R6_cred=0.7),              "is_threat": True, "category": "combo_R1_R6"},

    # ── MULTI-SIGNAL ATTACKS ───────────────────────────────────────
    {"name": "T50 Full attack R2+R5+R6",       "signals": make_signals(R2_device=1.0, R5_rate=1.0, R6_cred=1.0),  "is_threat": True, "category": "multi_signal"},
    {"name": "T51 Critical R3+R6+R5",          "signals": make_signals(R3_geo=1.0, R6_cred=1.0, R5_rate=1.0),     "is_threat": True, "category": "multi_signal"},
    {"name": "T52 Full foreign attack",        "signals": make_signals(R3_geo=1.0, R2_device=1.0, R6_cred=1.0),   "is_threat": True, "category": "multi_signal"},
    {"name": "T53 Night bot attack",           "signals": make_signals(R4_temporal=1.0, R5_rate=1.0, S2_velocity=1.0), "is_threat": True, "category": "multi_signal"},
    {"name": "T54 Full resource attack",       "signals": make_signals(R1_baseline=1.0, R2_device=1.0, R5_rate=1.0), "is_threat": True, "category": "multi_signal"},
    {"name": "T55 All signals moderate",       "signals": make_signals(R1_baseline=0.5, R2_device=0.5, R3_geo=0.5, R4_temporal=0.5, R5_rate=0.5, R6_cred=0.5, S2_velocity=0.5), "is_threat": True, "category": "multi_signal"},
    {"name": "T56 All signals full",           "signals": make_signals(R1_baseline=1.0, R2_device=1.0, R3_geo=1.0, R4_temporal=1.0, R5_rate=1.0, R6_cred=1.0, S2_velocity=1.0), "is_threat": True, "category": "multi_signal"},
    {"name": "T57 Foreign bot attack",         "signals": make_signals(R3_geo=1.0, R5_rate=1.0, S2_velocity=1.0),  "is_threat": True, "category": "multi_signal"},
    {"name": "T58 Credential + bot",           "signals": make_signals(R6_cred=1.0, R5_rate=1.0, S2_velocity=1.0), "is_threat": True, "category": "multi_signal"},
    {"name": "T59 Night credential bot",       "signals": make_signals(R4_temporal=1.0, R6_cred=1.0, R5_rate=1.0), "is_threat": True, "category": "multi_signal"},
    {"name": "T60 Device + foreign + rate",    "signals": make_signals(R2_device=1.0, R3_geo=1.0, R5_rate=1.0),   "is_threat": True, "category": "multi_signal"},

    # ── BLOCK-LEVEL ATTACKS (ρ ≥ 0.80) ────────────────────────────
    {"name": "T61 Block: R3+R6+R2+R5",        "signals": make_signals(R3_geo=1.0, R6_cred=1.0, R2_device=1.0, R5_rate=1.0), "is_threat": True, "category": "block_level"},
    {"name": "T62 Block: all critical",       "signals": make_signals(R3_geo=1.0, R6_cred=1.0, R2_device=1.0, R5_rate=1.0, S2_velocity=1.0), "is_threat": True, "category": "block_level"},
    {"name": "T63 Block: R3+R6 full + extras","signals": make_signals(R3_geo=1.0, R6_cred=1.0, R5_rate=1.0, R4_temporal=1.0), "is_threat": True, "category": "block_level"},

    # ── PARTIAL SIGNAL THREATS ─────────────────────────────────────
    {"name": "T64 Partial R6=0.7 alone",      "signals": make_signals(R6_cred=0.7),                                "is_threat": True, "category": "partial"},
    {"name": "T65 Partial R3=0.7 alone",      "signals": make_signals(R3_geo=0.7),                                 "is_threat": True, "category": "partial"},
]


# ── Confusion Matrix ────────────────────────────────────────────────────────

def evaluate_confusion_matrix(test_cases):
    TP = TN = FP = FN = 0
    details = []

    for tc in test_cases:
        result = run_carta(tc["signals"])
        predicted_threat = result["action"] != "allow"
        actual_threat    = tc["is_threat"]

        if actual_threat and predicted_threat:       label = "TP"; TP += 1
        elif not actual_threat and not predicted_threat: label = "TN"; TN += 1
        elif not actual_threat and predicted_threat: label = "FP"; FP += 1
        else:                                        label = "FN"; FN += 1

        details.append({
            "name":     tc["name"],
            "category": tc.get("category", ""),
            "is_threat":tc["is_threat"],
            "predicted":predicted_threat,
            "label":    label,
            "rho":      result["rho"],
            "action":   result["action"],
            "active":   result["active"],
            "combos":   result["combos"],
        })

    precision = TP / (TP + FP) if (TP + FP) > 0 else 0
    recall    = TP / (TP + FN) if (TP + FN) > 0 else 0
    f1        = 2*precision*recall/(precision+recall) if (precision+recall) > 0 else 0
    fpr       = FP / (FP + TN) if (FP + TN) > 0 else 0
    fnr       = FN / (FN + TP) if (FN + TP) > 0 else 0
    accuracy  = (TP + TN) / len(test_cases)
    specificity = TN / (TN + FP) if (TN + FP) > 0 else 0
    npv       = TN / (TN + FN) if (TN + FN) > 0 else 0

    return {
        "TP": TP, "TN": TN, "FP": FP, "FN": FN,
        "precision":   round(precision, 4),
        "recall":      round(recall, 4),
        "f1":          round(f1, 4),
        "fpr":         round(fpr, 4),
        "fnr":         round(fnr, 4),
        "accuracy":    round(accuracy, 4),
        "specificity": round(specificity, 4),
        "npv":         round(npv, 4),
        "details":     details,
    }


# ── ROC Curve ──────────────────────────────────────────────────────────────

def compute_roc_curve(test_cases):
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
            if is_threat and predicted:           TP += 1
            elif not is_threat and not predicted: TN += 1
            elif not is_threat and predicted:     FP += 1
            else:                                 FN += 1
        tpr = TP / (TP + FN) if (TP + FN) > 0 else 0
        fpr = FP / (FP + TN) if (FP + TN) > 0 else 0
        roc_points.append({"threshold": round(thresh,4), "tpr": round(tpr,4), "fpr": round(fpr,4)})

    roc_points.sort(key=lambda x: x["fpr"])

    # AUC via trapezoidal rule
    auc = 0.0
    for i in range(1, len(roc_points)):
        dx = roc_points[i]["fpr"] - roc_points[i-1]["fpr"]
        dy = (roc_points[i]["tpr"] + roc_points[i-1]["tpr"]) / 2
        auc += dx * dy

    return {
        "roc_points":      roc_points,
        "auc":             round(auc, 4),
        "auc_baseline":    0.5,
        "auc_improvement": round(auc - 0.5, 4),
    }


# ── Combo Verification ─────────────────────────────────────────────────────

def verify_all_combos():
    results = []
    for (sig_a, sig_b), factor in COMBO_MULTIPLIERS.items():
        signals = make_signals(**{sig_a: 1.0, sig_b: 1.0})
        base, active = compute_request_score(signals)
        final, combos = apply_combo_multipliers(base, active)
        expected_base  = (SIGNAL_WEIGHTS[sig_a] + SIGNAL_WEIGHTS[sig_b]) / TOTAL_WEIGHT
        expected_final = 1.0 - (1.0 - expected_base) ** factor
        match = abs(final - round(min(expected_final, 1.0), 4)) < 0.001
        results.append({
            "combo":          f"{sig_a} + {sig_b}",
            "factor":         factor,
            "base_score":     round(base, 4),
            "final_score":    final,
            "expected_final": round(min(expected_final, 1.0), 4),
            "verified":       match,
            "combo_fired":    len(combos) > 0,
        })
    return results


# ── Signal Weight Verification ─────────────────────────────────────────────

def verify_signal_weights():
    results = []
    for sig_name, weight in SIGNAL_WEIGHTS.items():
        signals = make_signals(**{sig_name: 1.0})
        computed, _ = compute_request_score(signals)
        expected = weight / TOTAL_WEIGHT
        match = abs(computed - round(expected, 4)) < 0.001
        results.append({
            "signal":       sig_name,
            "weight":       weight,
            "expected_rho": round(expected, 4),
            "computed_rho": computed,
            "verified":     match,
        })
    return results


# ── Threshold Boundary Tests ───────────────────────────────────────────────

def verify_thresholds():
    results = []
    boundaries = [
        (THRESHOLD_FLAG - 0.001,  "allow",  "just below flag τ₁"),
        (THRESHOLD_FLAG,          "flag",   "exactly at flag τ₁"),
        (THRESHOLD_FLAG + 0.001,  "flag",   "just above flag τ₁"),
        (THRESHOLD_MFA - 0.001,   "flag",   "just below mfa τ₂"),
        (THRESHOLD_MFA,           "mfa",    "exactly at mfa τ₂"),
        (THRESHOLD_MFA + 0.001,   "mfa",    "just above mfa τ₂"),
        (THRESHOLD_BLOCK - 0.001, "mfa",    "just below block τ₃"),
        (THRESHOLD_BLOCK,         "block",  "exactly at block τ₃"),
        (THRESHOLD_BLOCK + 0.001, "block",  "just above block τ₃"),
    ]
    for rho, expected_action, label in boundaries:
        actual_action = get_action(rho)
        results.append({
            "label":           label,
            "rho":             round(rho, 4),
            "expected_action": expected_action,
            "actual_action":   actual_action,
            "verified":        actual_action == expected_action,
        })
    return results


# ── Category Analysis ──────────────────────────────────────────────────────

def analyze_by_category(details):
    categories = {}
    for d in details:
        cat = d["category"]
        if cat not in categories:
            categories[cat] = {"TP":0,"TN":0,"FP":0,"FN":0,"count":0}
        categories[cat][d["label"]] += 1
        categories[cat]["count"] += 1
    return categories


# ── Main ───────────────────────────────────────────────────────────────────

def main():
    print(f"{'='*70}")
    print(f"  CARTA Engine Mathematical Verification — {len(TEST_CASES)} Test Cases")
    print(f"  Started : {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'='*70}\n")

    results = {}
    benign_count = sum(1 for t in TEST_CASES if not t["is_threat"])
    threat_count = sum(1 for t in TEST_CASES if t["is_threat"])
    print(f"  Test cases: {len(TEST_CASES)} total  ({benign_count} benign, {threat_count} threats)\n")

    # ── 1. Signal Weight Verification ────────────────────────────────────
    print("[ 1 ] Signal Weight Verification")
    print(f"  TOTAL_WEIGHT = {TOTAL_WEIGHT:.2f}")
    weight_results = verify_signal_weights()
    w_pass = True
    for r in weight_results:
        status = "✓" if r["verified"] else "✗"
        print(f"  {status} {r['signal']:20s} w={r['weight']:.2f}  "
              f"ρ_expected={r['expected_rho']:.4f}  ρ_computed={r['computed_rho']:.4f}")
        if not r["verified"]:
            w_pass = False
    print(f"  → {'ALL VERIFIED ✓' if w_pass else 'FAILURES ✗'}\n")
    results["weight_verification"] = weight_results

    # ── 2. Combo Multiplier Verification ─────────────────────────────────
    print("[ 2 ] Combo Multiplier Verification  [formula: final = 1-(1-base)^M]")
    combo_results = verify_all_combos()
    c_pass = True
    for r in combo_results:
        status = "✓" if r["verified"] else "✗"
        fired  = "FIRED ✓" if r["combo_fired"] else "NOT FIRED ✗"
        print(f"  {status} {r['combo']:35s} ×{r['factor']:.2f}  "
              f"base={r['base_score']:.4f}  final={r['final_score']:.4f}  "
              f"expected={r['expected_final']:.4f}  [{fired}]")
        if not r["verified"] or not r["combo_fired"]:
            c_pass = False
    print(f"  → {'ALL VERIFIED ✓' if c_pass else 'FAILURES ✗'}\n")
    results["combo_verification"] = combo_results

    # ── 3. Threshold Boundary Verification ───────────────────────────────
    print("[ 3 ] Threshold Boundary Verification")
    print(f"  τ₁={THRESHOLD_FLAG} (flag)  τ₂={THRESHOLD_MFA} (mfa)  τ₃={THRESHOLD_BLOCK} (block)")
    threshold_results = verify_thresholds()
    t_pass = True
    for r in threshold_results:
        status = "✓" if r["verified"] else "✗"
        print(f"  {status} ρ={r['rho']:.4f}  {r['label']:28s}  "
              f"expected={r['expected_action']:5s}  actual={r['actual_action']}")
        if not r["verified"]:
            t_pass = False
    print(f"  → {'ALL VERIFIED ✓' if t_pass else 'FAILURES ✗'}\n")
    results["threshold_verification"] = threshold_results

    # ── 4. Confusion Matrix ───────────────────────────────────────────────
    print(f"[ 4 ] Confusion Matrix ({len(TEST_CASES)} test cases)")
    cm = evaluate_confusion_matrix(TEST_CASES)

    print(f"\n  ┌─────────────────────────────────────────────────┐")
    print(f"  │           CONFUSION MATRIX                      │")
    print(f"  ├──────────────────────┬──────────────┬──────────┤")
    print(f"  │                      │ Pred. THREAT │Pred. OK  │")
    print(f"  ├──────────────────────┼──────────────┼──────────┤")
    print(f"  │ Actual THREAT        │  TP = {cm['TP']:3d}     │ FN = {cm['FN']:3d}│")
    print(f"  │ Actual BENIGN        │  FP = {cm['FP']:3d}     │ TN = {cm['TN']:3d}│")
    print(f"  └──────────────────────┴──────────────┴──────────┘")

    print(f"\n  ┌─────────────────────────────────────┐")
    print(f"  │  PERFORMANCE METRICS                │")
    print(f"  ├─────────────────────────────────────┤")
    print(f"  │  Accuracy    : {cm['accuracy']:.4f}  ({cm['accuracy']*100:.1f}%)      │")
    print(f"  │  Precision   : {cm['precision']:.4f}  ({cm['precision']*100:.1f}%)      │")
    print(f"  │  Recall      : {cm['recall']:.4f}  ({cm['recall']*100:.1f}%)      │")
    print(f"  │  Specificity : {cm['specificity']:.4f}  ({cm['specificity']*100:.1f}%)      │")
    print(f"  │  F1 Score    : {cm['f1']:.4f}                 │")
    print(f"  │  FPR         : {cm['fpr']:.4f}  ({cm['fpr']*100:.1f}%)       │")
    print(f"  │  FNR         : {cm['fnr']:.4f}  ({cm['fnr']*100:.1f}%)       │")
    print(f"  │  NPV         : {cm['npv']:.4f}  ({cm['npv']*100:.1f}%)      │")
    print(f"  └─────────────────────────────────────┘")

    # Category breakdown
    cats = analyze_by_category(cm["details"])
    print(f"\n  Category breakdown:")
    for cat, counts in sorted(cats.items()):
        tp=counts["TP"]; tn=counts["TN"]; fp=counts["FP"]; fn=counts["FN"]
        print(f"  {cat:25s}: TP={tp} TN={tn} FP={fp} FN={fn} (n={counts['count']})")

    # FP/FN details
    fps = [d for d in cm["details"] if d["label"] == "FP"]
    fns = [d for d in cm["details"] if d["label"] == "FN"]
    if fps:
        print(f"\n  False Positives (benign flagged):")
        for d in fps:
            print(f"    ✗ {d['name']:45s} ρ={d['rho']:.3f} → {d['action']}")
    if fns:
        print(f"\n  False Negatives (threats missed):")
        for d in fns:
            print(f"    ✗ {d['name']:45s} ρ={d['rho']:.3f} → {d['action']}")

    results["confusion_matrix"] = {k: v for k, v in cm.items() if k != "details"}
    results["confusion_matrix_details"] = cm["details"]

    # ── 5. ROC Curve + AUC ────────────────────────────────────────────────
    print(f"\n[ 5 ] ROC Curve & AUC")
    roc = compute_roc_curve(TEST_CASES)

    print(f"\n  AUC (CARTA)          : {roc['auc']:.4f}")
    print(f"  AUC (random baseline): {roc['auc_baseline']:.4f}")
    print(f"  Improvement over random: +{roc['auc_improvement']:.4f}")
    print(f"\n  ROC Points:")
    print(f"  {'Threshold':>10}  {'FPR':>6}  {'TPR':>6}  {'Chart'}")
    print(f"  {'─'*55}")
    for pt in roc["roc_points"]:
        bar = "█" * int(pt["tpr"] * 30)
        print(f"  τ={pt['threshold']:.4f}     {pt['fpr']:.4f}   {pt['tpr']:.4f}   {bar}")

    results["roc"] = roc

    # ── Final Summary ─────────────────────────────────────────────────────
    print(f"\n{'='*70}")
    print(f"  FINAL VERIFICATION SUMMARY")
    print(f"{'='*70}")
    print(f"  Test cases        : {len(TEST_CASES)} ({benign_count} benign, {threat_count} threats)")
    print(f"  Signal weights    : {'✓ ALL CORRECT' if w_pass else '✗ ERRORS'}")
    print(f"  Combo multipliers : {'✓ ALL CORRECT' if c_pass else '✗ ERRORS'}")
    print(f"  Thresholds        : {'✓ ALL CORRECT' if t_pass else '✗ ERRORS'}")
    print(f"  TP={cm['TP']}  TN={cm['TN']}  FP={cm['FP']}  FN={cm['FN']}")
    print(f"  Accuracy          : {cm['accuracy']*100:.1f}%")
    print(f"  Precision         : {cm['precision']*100:.1f}%")
    print(f"  Recall            : {cm['recall']*100:.1f}%")
    print(f"  F1 Score          : {cm['f1']:.4f}")
    print(f"  FPR               : {cm['fpr']*100:.1f}%  (false alarm rate)")
    print(f"  FNR               : {cm['fnr']*100:.1f}%  (missed threat rate)")
    print(f"  AUC               : {roc['auc']:.4f}  (vs 0.5000 random baseline)")

    output = f"benchmark_carta_verification_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    with open(output, "w") as f:
        json.dump(results, f, indent=2, default=str)
    print(f"\n  Results saved to: {output}")
    print(f"{'='*70}\n")


if __name__ == "__main__":
    main()
