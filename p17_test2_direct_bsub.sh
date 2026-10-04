#!/bin/bash
# P1.7 – Test 2: 50 DIRECT bsub submissions (no gateway) – baseline for Table 7 / R2.6
# Run ON THE LSF MASTER as the SERVICE ACCOUNT (or from the management host over SSH – say which in your reply).
# One job at a time, no other load. Bash-only (RHEL 6 / LSF 9.1 compatible).
#
# !!! Every value in the CONFIG block must be copied from benchmark_e2e_20260503_200730.json and from the
# !!! gateway's own submit/poll code, so the comparison is fair. Nothing below is guessed for you.

##################################### CONFIG – FILL IN #####################################
JOB_SCRIPT="/path/to/the_same_job_script.sh"   # exact script used in the benchmark campaign
QUEUE="FILL_ME"                                # same queue as the campaign
BSUB_EXTRA_ARGS=( )                            # same resources, e.g. ( -n 1 -R "rusage[mem=...]" -W ... ) -> copy from gateway
POLL_INTERVAL_S="FILL_ME"                      # SAME polling period as the gateway (seconds, may be fractional e.g. 1 or 0.5)
N_TRIALS=50
TIMEOUT_S=600                                  # give up on one job after this long (status = TIMEOUT)
MEASURE_SCP=0                                  # set to 1 if the gateway copies the script by SFTP; then also times scp
SCP_TARGET=""                                  # e.g. "svc_account@lsf-master:/tmp/"  (only used when MEASURE_SCP=1)
SUBMIT_MODE="local-on-master"                  # free text for the log: "local-on-master" or "ssh-from-management-host"
###########################################################################################

set -u
[ "$POLL_INTERVAL_S" = "FILL_ME" ] || [ "$QUEUE" = "FILL_ME" ] && { echo "Fill the CONFIG block first."; exit 2; }
[ -f "$JOB_SCRIPT" ] || { echo "JOB_SCRIPT not found: $JOB_SCRIPT"; exit 2; }
command -v bsub >/dev/null && command -v bjobs >/dev/null || { echo "bsub/bjobs not in PATH"; exit 2; }

now_ms() { echo $(( $(date +%s%N) / 1000000 )); }
STAMP="$(date +%Y%m%d_%H%M%S)"
CSV="direct_bsub_${STAMP}.csv"
META="direct_bsub_${STAMP}.meta.txt"
{
  echo "date_utc=$(date -u '+%Y-%m-%dT%H:%M:%SZ')"; echo "host=$(hostname)"; echo "user=$(id -un)"
  echo "mode=$SUBMIT_MODE"; echo "queue=$QUEUE"; echo "job_script=$JOB_SCRIPT"; echo "job_script_sha256=$(sha256sum "$JOB_SCRIPT" | awk '{print $1}')"
  echo "bsub_extra_args=${BSUB_EXTRA_ARGS[*]}"; echo "poll_interval_s=$POLL_INTERVAL_S"; echo "n_trials=$N_TRIALS"
  echo "lsf_version=$(lsid 2>/dev/null | head -1)"
  echo "definitions: t0=just before bsub; t1=bsub returned job id; t2=bjobs shows DONE (or EXIT)"
  echo "t_submit_ms=t1-t0 ; t_complete_ms=t2-t1 ; t_total_ms=t2-t0   <-- CHECK these match the benchmark JSON definitions"
} > "$META"

echo "trial,t0_ms,t1_ms,t2_ms,t_submit_ms,t_complete_ms,t_total_ms,status,job_id,scp_ms" > "$CSV"

for i in $(seq 1 "$N_TRIALS"); do
  scp_ms=""
  if [ "$MEASURE_SCP" = "1" ]; then
    s=$(now_ms); scp -q -o BatchMode=yes "$JOB_SCRIPT" "$SCP_TARGET" >/dev/null 2>&1; e=$(now_ms); scp_ms=$(( e - s ))
  fi

  t0=$(now_ms)
  out=$(bsub -q "$QUEUE" "${BSUB_EXTRA_ARGS[@]}" < "$JOB_SCRIPT" 2>&1)    # same invocation style as the gateway? adjust if it passes the script path instead
  t1=$(now_ms)
  jid=$(echo "$out" | sed -n 's/.*Job <\([0-9]\+\)>.*/\1/p' | head -1)
  if [ -z "$jid" ]; then
    echo "$i,$t0,$t1,,$((t1-t0)),,,SUBMIT_FAILED,,$scp_ms" >> "$CSV"; echo "trial $i: submit failed: $out"; continue
  fi

  status="TIMEOUT"; t2=""
  deadline=$(( t1 + TIMEOUT_S * 1000 ))
  while [ "$(now_ms)" -lt "$deadline" ]; do
    st=$(bjobs -noheader "$jid" 2>/dev/null | awk '{print $3}' | head -1)
    case "$st" in
      DONE) t2=$(now_ms); status="DONE"; break ;;
      EXIT) t2=$(now_ms); status="EXIT"; break ;;
    esac
    sleep "$POLL_INTERVAL_S"
  done

  if [ -n "$t2" ]; then
    echo "$i,$t0,$t1,$t2,$((t1-t0)),$((t2-t1)),$((t2-t0)),$status,$jid,$scp_ms" >> "$CSV"
  else
    echo "$i,$t0,$t1,,$((t1-t0)),,,$status,$jid,$scp_ms" >> "$CSV"
  fi
  echo "trial $i/$N_TRIALS job=$jid status=$status total=$([ -n "$t2" ] && echo $((t2-t0)) || echo -)ms"
done

echo; echo "Raw data : $CSV"; echo "Metadata : $META"
awk -F, 'NR>1 && $8=="DONE"{n++; s+=$7; v[n]=$7} END{ if(n){ m=s/n; for(i=1;i<=n;i++) q+=(v[i]-m)^2; printf "DONE trials: %d  mean total: %.0f ms  sd: %.0f ms\n", n, m, (n>1?sqrt(q/(n-1)):0)} }' "$CSV"
