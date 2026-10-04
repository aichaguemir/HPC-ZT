#!/bin/bash
# P1.7 – Test 1: SSH with accounts that must NOT be able to log in (proof of non-bypass, §5.2 / R2.3)
# Run from a machine on the MANAGEMENT VLAN.  Needs: ssh.  Optional: sshpass (for non-interactive password attempts).
#
# Usage:
#   ./p17_test1_ssh_nonprovisioned.sh <LSF_MASTER_HOST> <COMPUTE_NODE_HOST>
# Then it asks for the portal account name + password (typed, never stored in the script or the logs).
#
# For EACH attempt it saves, under ./p17_test1_<timestamp>/ :
#   - the exact command, local date/time (+UTC), exit code, and the FULL `ssh -v` output
# It does NOT collect /var/log/secure (that file is on the master): see the helper printed at the end.

set -u
MASTER="${1:?usage: $0 <LSF_MASTER_HOST> <COMPUTE_NODE_HOST>}"
NODE="${2:?usage: $0 <LSF_MASTER_HOST> <COMPUTE_NODE_HOST>}"
FAKE_USER="hpczt_test_nouser"
OUT="p17_test1_$(date +%Y%m%d_%H%M%S)"; mkdir -p "$OUT"
SUMMARY="$OUT/summary.txt"

# Pre-flight: refuse to run if the targets are not reachable from THIS machine (a failed connection is not proof of anything)
echo "Running from: $(hostname) ($(hostname -I 2>/dev/null | awk '{print $1}'))  -- this must be a machine on the management VLAN"
for h in "$MASTER" "$NODE"; do
  if ! getent hosts "$h" >/dev/null 2>&1 && ! [[ "$h" =~ ^[0-9.]+$ ]]; then echo "ABORT: '$h' does not resolve from this machine. Run this from a cluster/management machine."; exit 3; fi
  if ! timeout 5 bash -c "echo > /dev/tcp/$h/22" 2>/dev/null; then echo "ABORT: cannot open TCP port 22 on '$h' from this machine. Wrong network or firewall: results would be meaningless."; exit 3; fi
done
read -r -p "Portal account name (created by the gateway): " PORTAL_USER
read -r -s -p "Its portal password (typed here only, not saved): " PORTAL_PASS; echo

SSH_OPTS=(-v -o PreferredAuthentications=password,keyboard-interactive -o PubkeyAuthentication=no
          -o NumberOfPasswordPrompts=1 -o ConnectTimeout=15 -o StrictHostKeyChecking=ask)

attempt() {   # attempt <label> <user> <host> <password>
  local label="$1" user="$2" host="$3" pass="$4" f="$OUT/${1}.txt"
  local cmd="ssh ${SSH_OPTS[*]} ${user}@${host} true"
  {
    echo "ATTEMPT   : $label"
    echo "COMMAND   : $cmd"
    echo "LOCAL TIME: $(date '+%Y-%m-%d %H:%M:%S %Z')   UTC: $(date -u '+%Y-%m-%d %H:%M:%S')"
    echo "FROM HOST : $(hostname) ($(hostname -I 2>/dev/null | awk '{print $1}'))"
    echo "------------------------------------------------------------ output"
  } > "$f"
  if command -v sshpass >/dev/null 2>&1; then
    SSHPASS="$pass" sshpass -e ssh "${SSH_OPTS[@]}" "${user}@${host}" true >> "$f" 2>&1; rc=$?
  else
    echo "(sshpass not installed: type the password when prompted)" >> "$f"
    ssh "${SSH_OPTS[@]}" "${user}@${host}" true 2>&1 | tee -a "$f"; rc=${PIPESTATUS[0]}
  fi
  echo "------------------------------------------------------------" >> "$f"
  echo "EXIT CODE : $rc   (255 = connection/auth failure)" >> "$f"
  local verdict
  if   grep -qi 'permission denied' "$f";                         then verdict="OK: Permission denied (authentication refused)"
  elif grep -qiE 'timed out|no route to host' "$f";               then verdict="INVALID TEST: could not reach the host (timeout / no route) - not an auth result"
  elif grep -qi 'could not resolve hostname' "$f";                then verdict="INVALID TEST: hostname does not resolve from this machine"
  elif grep -qi 'connection refused' "$f";                        then verdict="INVALID TEST: connection refused (sshd not listening there)"
  elif [ "$rc" = "0" ];                                           then verdict="!!! LOGIN SUCCEEDED - STOP AND REPORT !!!"
  else verdict="UNCLASSIFIED - READ THE FILE"; fi
  echo "$(date -u '+%H:%M:%S')Z  $label  user=$user host=$host  exit=$rc  -> $verdict" | tee -a "$SUMMARY"
}

attempt "1_fake_user_master"    "$FAKE_USER"   "$MASTER" "wrong-password-on-purpose"
attempt "2_portal_user_master"  "$PORTAL_USER" "$MASTER" "$PORTAL_PASS"
attempt "3_portal_user_node"    "$PORTAL_USER" "$NODE"   "$PORTAL_PASS"
attempt "4_fake_user_node"      "$FAKE_USER"   "$NODE"   "wrong-password-on-purpose"   # bonus, same test on a compute node

unset PORTAL_PASS
cat <<EOF

Done. Evidence in: $OUT/   (summary.txt + one file per attempt)

NOW get the matching sshd lines, ON THE LSF MASTER (and on the compute node for attempts 3-4), as root:
  sudo grep -E "${FAKE_USER}|${PORTAL_USER}" /var/log/secure | tail -n 20
Copy the lines whose timestamps match the "LOCAL TIME" of each attempt. Typical RHEL 6 text:
  "Failed password for invalid user ${FAKE_USER} from <your IP> port NNNNN ssh2"
Keep the output EXACTLY as printed (do not edit). Check the master's clock vs yours (date) so times line up.
EOF
