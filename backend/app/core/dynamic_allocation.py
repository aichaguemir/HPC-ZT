"""
Dynamic Resource Allocation Engine
====================================
Provides real-time cluster state and allocation options.

Two features:
  1. get_cluster_state()      → parse bhosts, return node data
  2. get_allocation_options() → offer user: wait OR throttled
  3. compute_lsf_params()     → decide serial vs MPI LSF params
"""
from datetime import datetime, timezone, timedelta
from typing import Optional
from dataclasses import dataclass

from app.core.logging import logger
from app.services.ssh import run_ssh_async
from app.core.config import LSF_PATH


# ── Cache ──────────────────────────────────────────────────────────────────
_cluster_cache: dict = {"state": None, "updated": None}
CACHE_TTL = timedelta(minutes=2)


# ══════════════════════════════════════════════════════════════════════════
# STEP 1 — CLUSTER STATE
# ══════════════════════════════════════════════════════════════════════════

async def get_cluster_state() -> dict:
    """
    Fetches real-time cluster state from bhosts.
    Cached for 2 minutes.

    Returns:
    {
        "total_cores":   int,
        "free_cores":    int,
        "utilization":   float,   # 0.0 to 1.0
        "active_nodes":  int,
        "total_nodes":   int,
        "nodes": [
            {
                "host":       str,
                "max_cores":  int,
                "run_cores":  int,
                "free_cores": int,
                "available":  bool,
                "utilization": float
            }
        ]
    }
    """
    global _cluster_cache
    now = datetime.now(timezone.utc)

    # Return cached state if fresh
    if (_cluster_cache["state"] is not None and
            _cluster_cache["updated"] is not None and
            now - _cluster_cache["updated"] < CACHE_TTL):
        return _cluster_cache["state"]

    try:
        result = await run_ssh_async(f"{LSF_PATH}/bhosts")
        lines  = result.strip().splitlines()

        nodes     = []
        total_max = 0
        total_run = 0

        for line in lines[1:]:    # skip header line
            parts = line.split()
            if len(parts) < 6:
                continue

            host      = parts[0]   # e.g. compute001
            status    = parts[1]   # ok / unavail / closed
            max_cores = int(parts[3])   # MAX column
            run_cores = int(parts[5])   # RUN column

            # YOUR LOGIC — node is usable if:
            # 1. status is "ok"
            # 2. max_cores > 1 (unavail nodes show MAX=1)
            # 3. not an admin node (don't submit jobs there)
            is_usable = (
                status    == "ok" and
                max_cores  > 1   and
                "admin" not in host
            )

            # Free cores = max - currently running
            free_cores  = max_cores - run_cores
            node_util   = run_cores / max_cores if max_cores > 0 else 0.0

            # Accumulate cluster totals (usable nodes only)
            if is_usable:
                total_max += max_cores
                total_run += run_cores

            nodes.append({
                "host":        host,
                "max_cores":   max_cores,
                "run_cores":   run_cores,
                "free_cores":  free_cores,
                "available":   is_usable,
                "utilization": round(node_util, 2),
            })

        utilization = total_run / total_max if total_max > 0 else 0.0

        state = {
            "total_cores":  total_max,
            "free_cores":   total_max - total_run,
            "utilization":  round(utilization, 3),
            "active_nodes": len([n for n in nodes if n["available"]]),
            "total_nodes":  len(nodes),
            "nodes":        nodes,
        }

        # Update cache
        _cluster_cache["state"]   = state
        _cluster_cache["updated"] = now

        logger.info(
            f"Cluster state: {state['active_nodes']} active nodes, "
            f"{state['free_cores']}/{state['total_cores']} cores free, "
            f"utilization={utilization*100:.1f}%"
        )
        return state

    except Exception as e:
        logger.error(f"Could not fetch cluster state: {e}")
        # Return last cached state if available
        if _cluster_cache["state"]:
            logger.warning("Returning stale cluster state from cache")
            return _cluster_cache["state"]
        # Return safe default if no cache
        return {
            "total_cores":  0,
            "free_cores":   0,
            "utilization":  0.0,
            "active_nodes": 0,
            "total_nodes":  0,
            "nodes":        [],
        }


# ══════════════════════════════════════════════════════════════════════════
# STEP 2 — ALLOCATION OPTIONS
# ══════════════════════════════════════════════════════════════════════════

async def get_allocation_options(
    requested_cores:  int,
    requested_memory: int,
    role:             str,
    job_type:         str = "serial",
) -> dict:
    """
    Given what a user wants, return what the cluster can offer NOW.

    Returns two options:
      1. wait      → submit with full requested resources, may queue
      2. throttled → reduce cores to what's available now, runs immediately

    For MPI jobs: also checks if ptile distribution is possible.
    """
    state = await get_cluster_state()
    util  = state["utilization"]
    util_pct = util * 100

    # Get usable nodes sorted by free_cores descending
    usable_nodes = sorted(
        [n for n in state["nodes"] if n["available"] and n["free_cores"] > 0],
        key=lambda n: n["free_cores"],
        reverse=True,
    )

    options = []

    # ── Option 1: Wait for full allocation ────────────────────────────────
    can_run_now = state["free_cores"] >= requested_cores
    if can_run_now:
        wait_estimate = "immediate"
    elif util_pct < 50:
        wait_estimate = "< 30 minutes"
    elif util_pct < 80:
        wait_estimate = "~1-2 hours"
    else:
        wait_estimate = "~2-4 hours"

    options.append({
        "id":             "wait",
        "label":          "Submit with full resources",
        "cores":          requested_cores,
        "memory":         requested_memory,
        "available_now":  can_run_now,
        "estimated_wait": wait_estimate,
        "note":           "Job will run when resources are available"
                          if not can_run_now else "Resources available now",
    })

    # ── Option 2: Throttled — run now with less ────────────────────────────
    if not can_run_now and usable_nodes:
        best_node       = usable_nodes[0]   # node with most free cores
        throttled_cores = min(requested_cores, best_node["free_cores"])

        # Scale memory proportionally
        throttled_memory = int(
            requested_memory * (throttled_cores / requested_cores)
        )
        throttled_memory = max(256, throttled_memory)   # minimum 256MB

        if throttled_cores > 0 and throttled_cores < requested_cores:
            options.append({
                "id":             "throttled",
                "label":          f"Run now with {throttled_cores} cores",
                "cores":          throttled_cores,
                "memory":         throttled_memory,
                "available_now":  True,
                "estimated_wait": "immediate",
                "target_node":    best_node["host"],
                "note": (
                    f"Reduced from {requested_cores} to {throttled_cores} cores "
                    f"due to {util_pct:.0f}% cluster load. "
                    f"Running on {best_node['host']}."
                ),
            })

    return {
        "cluster_utilization": f"{util_pct:.0f}%",
        "cluster_free_cores":  state["free_cores"],
        "cluster_total_cores": state["total_cores"],
        "requested_cores":     requested_cores,
        "job_type":            job_type,
        "options":             options,
    }


# ══════════════════════════════════════════════════════════════════════════
# STEP 3 — LSF PARAMETERS
# ══════════════════════════════════════════════════════════════════════════

def compute_lsf_params(
    job_type:    str,
    cores:       int,
    memory:      int,
    processes:   Optional[int] = None,
    ptile:       Optional[int] = None,
    target_node: Optional[str] = None,
) -> dict:
    """
    Returns LSF directive parameters based on job type.

    Serial:
        -n {cores}
        -R "rusage[mem={memory}] span[hosts=1]"

    MPI:
        -n {processes}
        -R "rusage[mem={memory}] span[ptile={ptile}]"
        mpirun -np {processes} python3 sandbox.py

    Returns dict used by generate_lsf().
    """
    if job_type == "mpi":
        if not processes or not ptile:
            raise ValueError("MPI jobs require processes and ptile")

        nodes_needed = processes // ptile
        return {
            "job_type":     "mpi",
            "bsub_n":       processes,
            "resource_req": f'rusage[mem={memory}] span[ptile={ptile}]',
            "node_flag":    f'-m "{target_node}"' if target_node else "",
            "exec_prefix":  f"mpirun -np {processes}",
            "nodes_needed": nodes_needed,
            "note":         f"MPI: {processes} processes, "
                            f"{ptile} per node, {nodes_needed} nodes",
        }
    else:
        return {
            "job_type":     "serial",
            "bsub_n":       cores,
            "resource_req": f'rusage[mem={memory}] span[hosts=1]',
            "node_flag":    f'-m "{target_node}"' if target_node else "",
            "exec_prefix":  "",
            "nodes_needed": 1,
            "note":         f"Serial: {cores} cores on single node",
        }


# ══════════════════════════════════════════════════════════════════════════
# STEP 4 — MPI VALIDATION
# ══════════════════════════════════════════════════════════════════════════

def validate_mpi_params(
    processes:   int,
    ptile:       int,
    role:        str,
    max_cores:   int,   # from policy
) -> None:
    """
    Validates MPI job parameters.
    Raises HTTPException with clear message if invalid.
    """
    from fastapi import HTTPException

    # processes must be > 1
    if processes < 2:
        raise HTTPException(400,
            "MPI requires at least 2 processes")

    # ptile must divide processes evenly
    if processes % ptile != 0:
        raise HTTPException(400,
            f"Total processes ({processes}) must be divisible "
            f"by processes per node ({ptile}). "
            f"Try: {ptile * (processes // ptile)} or {ptile * (processes // ptile + 1)}")

    # ptile cannot exceed physical node capacity
    if ptile > 16:
        raise HTTPException(400,
            f"Processes per node ({ptile}) cannot exceed "
            f"node capacity (16 cores)")

    # total processes cannot exceed policy
    if processes > max_cores:
        raise HTTPException(400,
            f"Total processes ({processes}) exceeds "
            f"policy limit ({max_cores} cores) for {role} role")

    # minimum ptile = 1
    if ptile < 1:
        raise HTTPException(400,
            "Processes per node must be at least 1")
