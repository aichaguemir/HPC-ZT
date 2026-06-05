
from datetime import datetime, timezone, timedelta
from typing import Optional

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
    mpi_ptile:        Optional[int] = None,   # required when job_type == "mpi"
) -> dict:
    """
    Given what a user wants, return what the cluster can offer NOW.

    Serial / multicore:
      option 1 — wait: submit with full requested cores, may queue
      option 2 — throttled: reduce to what's free on one node, runs now

    MPI multi-node:
      option 1 — wait: submit full rank count, may queue
      option 2 — throttled: reduce to fewer nodes using available ptile slots
      (No single-node fallback for MPI — that changes the job semantics.)
    """
    state    = await get_cluster_state()
    util     = state["utilization"]
    util_pct = util * 100

    usable_nodes = sorted(
        [n for n in state["nodes"] if n["available"] and n["free_cores"] > 0],
        key=lambda n: n["free_cores"],
        reverse=True,
    )

    options = []

    # ── MPI: multi-node path ───────────────────────────────────────────────
    if job_type == "mpi" and mpi_ptile:
        nodes_needed  = requested_cores // mpi_ptile

        # Count nodes that can host a full ptile slice
        capable_nodes = [
            n for n in usable_nodes if n["free_cores"] >= mpi_ptile
        ]
        can_run_now   = len(capable_nodes) >= nodes_needed

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
            "label":          f"Submit with full {requested_cores} ranks ({nodes_needed} nodes)",
            "cores":          requested_cores,
            "memory":         requested_memory,
            "mpi_processes":  requested_cores,
            "mpi_ptile":      mpi_ptile,
            "nodes_needed":   nodes_needed,
            "available_now":  can_run_now,
            "estimated_wait": wait_estimate,
            "note": (
                "Resources available now" if can_run_now
                else f"Need {nodes_needed} nodes with {mpi_ptile} free cores each; "
                     f"only {len(capable_nodes)} currently available"
            ),
        })

        # Throttled MPI: use as many capable nodes as are ready right now
        if not can_run_now and len(capable_nodes) >= 2:
            throttled_nodes    = len(capable_nodes)
            throttled_procs    = throttled_nodes * mpi_ptile
            throttled_memory   = max(
                256,
                int(requested_memory * (throttled_procs / requested_cores))
            )
            options.append({
                "id":             "throttled",
                "label":          f"Run now with {throttled_procs} ranks ({throttled_nodes} nodes)",
                "cores":          throttled_procs,
                "memory":         throttled_memory,
                "mpi_processes":  throttled_procs,
                "mpi_ptile":      mpi_ptile,
                "nodes_needed":   throttled_nodes,
                "available_now":  True,
                "estimated_wait": "immediate",
                "note": (
                    f"Reduced from {requested_cores} to {throttled_procs} ranks "
                    f"({nodes_needed} → {throttled_nodes} nodes) "
                    f"due to {util_pct:.0f}% cluster load."
                ),
            })

        return {
            "cluster_utilization":  f"{util_pct:.0f}%",
            "cluster_free_cores":   state["free_cores"],
            "cluster_total_cores":  state["total_cores"],
            "capable_nodes_for_mpi": len(capable_nodes),
            "requested_cores":      requested_cores,
            "mpi_ptile":            mpi_ptile,
            "job_type":             "mpi",
            "options":              options,
        }

    # ── Serial / multicore: single-node path ──────────────────────────────
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
        "note": (
            "Resources available now" if can_run_now
            else "Job will run when resources are available"
        ),
    })

    if not can_run_now and usable_nodes:
        best_node        = usable_nodes[0]
        throttled_cores  = min(requested_cores, best_node["free_cores"])
        throttled_memory = max(
            256,
            int(requested_memory * (throttled_cores / requested_cores))
        )
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

    Serial / multicore (single node):
        -n {cores}
        -R "rusage[mem={memory}] span[hosts=1]"

    MPI (multi-node):
        -n {processes}
        -R "select[...exclusions && status==ok] span[ptile={ptile}]"
        mpirun -TCP -np $LSB_DJOB_NUMPROC -hostfile $MPI_HOSTS python3 sandbox.py

    Keys returned map directly to generate_lsf() parameters.
    """
    if job_type == "mpi":
        if not processes or not ptile:
            raise ValueError("MPI jobs require processes and ptile")

        nodes_needed = processes // ptile
        return {
            "job_type":      "mpi",
            "mpi_processes": processes,       # → generate_lsf(mpi_processes=)
            "mpi_ptile":     ptile,           # → generate_lsf(mpi_ptile=)
            "cores":         processes,       # total cores for policy check
            "nodes_needed":  nodes_needed,
            "note": (
                f"MPI: {processes} ranks across {nodes_needed} nodes "
                f"({ptile} ranks/node)"
            ),
        }
    else:
        return {
            "job_type":      "serial",
            "cores":         cores,
            "mpi_processes": None,
            "mpi_ptile":     None,
            "target_node":   target_node,
            "nodes_needed":  1,
            "note":          f"Serial: {cores} cores on single node",
        }


# ══════════════════════════════════════════════════════════════════════════
# STEP 4 — MPI VALIDATION
# ══════════════════════════════════════════════════════════════════════════
async def validate_mpi_params(
    processes: int,
    ptile: int,
    role: str,
    max_cores: int,   # policy max cores (still needed for total processes check)
) -> None:
    """
    Validates MPI job parameters against cluster node capacity.
    Raises HTTPException with clear message if invalid.
    """
    from fastapi import HTTPException

    # processes must be > 1
    if processes < 2:
        raise HTTPException(400, "MPI requires at least 2 processes")

    # ptile must divide processes evenly
    if processes % ptile != 0:
        raise HTTPException(400,
            f"Total processes ({processes}) must be divisible "
            f"by processes per node ({ptile}). "
            f"Try: {ptile * (processes // ptile)} or {ptile * (processes // ptile + 1)}")

    # Get actual node capacity from cluster
    state = await get_cluster_state()
    # Find the minimum max_cores among available (usable) nodes
    usable_nodes = [n for n in state["nodes"] if n["available"] and n["max_cores"] > 0]
    if not usable_nodes:
        # Fallback: use policy max_cores_per_job as conservative estimate
        max_cores_per_node = max_cores
    else:
        max_cores_per_node = min(n["max_cores"] for n in usable_nodes)

    # Check ptile against actual node capacity
    if ptile > max_cores_per_node:
        raise HTTPException(400,
            f"Processes per node ({ptile}) cannot exceed node capacity ({max_cores_per_node} cores). "
            f"Available nodes have at most {max_cores_per_node} cores.")

    # total processes cannot exceed policy limit (role-based)
    if processes > max_cores:
        raise HTTPException(400,
            f"Total processes ({processes}) exceeds policy limit ({max_cores} cores) for {role} role")

    # minimum ptile = 1
    if ptile < 1:
        raise HTTPException(400, "Processes per node must be at least 1")
