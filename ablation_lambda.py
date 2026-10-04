"""
Ablation study: Pi(rho, lambda) load-aware policy.
Compares WITH-tightening (real deployed policy) vs WITHOUT-tightening
(load_tier forced to 'low' regardless of actual cluster load) across
a fine grid of risk score rho in [0,1] and cluster load lambda in [0,1].

Run inside the fastapi container:
  docker compose exec fastapi python3 /app/ablation_lambda.py
"""
import json
import sys
sys.path.insert(0, "/app")

from app.core.carta import compute_2d_policy, THRESHOLD_FLAG, THRESHOLD_MFA, THRESHOLD_BLOCK

STEP = 0.01

def classify_risk_tier(rho: float) -> str:
    if rho < THRESHOLD_FLAG:
        return "low"
    elif rho < THRESHOLD_MFA:
        return "medium"
    elif rho < THRESHOLD_BLOCK:
        return "high"
    else:
        return "critical"

# Reimplementation of the matrix lookup, forcing load_tier='low'
# (i.e. simulating a policy with load tightening disabled entirely).
MATRIX = {
    "low": {
        "low":      ("allow",    1.0,  False, False),
        "medium":   ("allow",    1.0,  False, False),
        "high":     ("allow",    1.0,  False, False),
        "critical": ("flag",     1.0,  False, False),
    },
    "medium": {
        "low":      ("flag",     1.0,  False, False),
        "medium":   ("flag",     1.0,  False, False),
        "high":     ("mfa",      1.0,  True,  False),
        "critical": ("throttle", 0.75, True,  False),
    },
    "high": {
        "low":      ("mfa",      1.0,  True,  False),
        "medium":   ("restrict", 0.5,  True,  False),
        "high":     ("restrict", 0.5,  True,  False),
        "critical": ("block",    0.0,  False, True),
    },
    "critical": {
        "low":      ("block",    0.0,  False, True),
        "medium":   ("block",    0.0,  False, True),
        "high":     ("block",    0.0,  False, True),
        "critical": ("isolate",  0.0,  False, True),
    },
}

def compute_policy_no_tightening(risk_score: float):
    risk_tier = classify_risk_tier(risk_score)
    action, resource_cap, mfa_required, admin_alert = MATRIX[risk_tier]["low"]
    return action, risk_tier

def main():
    results = []
    n_points = 0
    n_diff = 0
    diffs_by_load_bucket = {}

    rho = 0.0
    while rho <= 1.0001:
        lam = 0.0
        while lam <= 1.0001:
            with_t = compute_2d_policy(round(rho, 4), round(lam, 4))
            without_action, without_tier = compute_policy_no_tightening(round(rho, 4))

            n_points += 1
            differs = with_t.action != without_action
            if differs:
                n_diff += 1
                bucket = round(lam, 1)
                diffs_by_load_bucket[bucket] = diffs_by_load_bucket.get(bucket, 0) + 1

            results.append({
                "rho": round(rho, 4),
                "lambda": round(lam, 4),
                "risk_tier": with_t.risk_tier,
                "load_tier": with_t.load_tier,
                "action_with_tightening": with_t.action,
                "action_without_tightening": without_action,
                "differs": differs,
            })
            lam += STEP
        rho += STEP

    summary = {
        "total_grid_points": n_points,
        "points_where_tightening_changes_action": n_diff,
        "pct_changed": round(100 * n_diff / n_points, 3),
        "diffs_by_load_bucket_0.1_steps": diffs_by_load_bucket,
    }

    with open("/app/ablation_results.json", "w") as f:
        json.dump({"summary": summary, "grid": results}, f)

    print(json.dumps(summary, indent=2))

    # Sanity check: P2 says load tightening should only ever make actions
    # MORE restrictive, never less. Verify no point where without>with severity.
    SEVERITY = {"allow":0,"flag":1,"mfa":2,"throttle":3,"restrict":4,"block":5,"isolate":6}
    violations = [
        r for r in results
        if SEVERITY[r["action_with_tightening"]] < SEVERITY[r["action_without_tightening"]]
    ]
    print(f"\nP2 monotonicity violations (tightened action LESS severe than baseline): {len(violations)}")
    if violations[:5]:
        print("First few violations:", violations[:5])

if __name__ == "__main__":
    main()
