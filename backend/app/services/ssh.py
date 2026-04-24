import asyncio
import threading
import paramiko
from fastapi import HTTPException

from app.core.config import SSH_HOST, SSH_USER, SSH_PASSWORD, REMOTE_JOB_DIR
from app.core.logging import logger

_ssh_client = None
_ssh_lock   = threading.Lock()


# ══════════════════════════════════════════════════════════════════════════
# CONNECTION POOL
# ══════════════════════════════════════════════════════════════════════════

def create_ssh_client() -> paramiko.SSHClient:
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    ssh.connect(
        SSH_HOST,
        username     = SSH_USER,
        password     = SSH_PASSWORD,
        timeout      = 30,
        allow_agent  = False,
        look_for_keys= False,
    )
    ssh.get_transport().set_keepalive(30)
    return ssh


def get_ssh_client() -> paramiko.SSHClient:
    global _ssh_client
    with _ssh_lock:
        if _ssh_client:
            transport = _ssh_client.get_transport()
            if transport and transport.is_active():
                return _ssh_client
        _ssh_client = create_ssh_client()
        return _ssh_client


# ══════════════════════════════════════════════════════════════════════════
# COMMAND EXECUTION
# ══════════════════════════════════════════════════════════════════════════

def run_ssh_command(command: str) -> str:
    try:
        ssh = get_ssh_client()
        stdin, stdout, stderr = ssh.exec_command(command, timeout=60)
        stdout.channel.settimeout(60)
        exit_status = stdout.channel.recv_exit_status()
        output      = stdout.read().decode()
        error       = stderr.read().decode()

        if exit_status != 0:
            logger.error(
                f"HPC command failed | exit={exit_status} | "
                f"cmd={command[:80]} | stderr={error.strip()}"
            )
            # exit=255 from bjobs means job not found — not a server error
            if exit_status == 255 and "not found" in error.lower():
                return ""
            raise RuntimeError("HPC command failed.")

        return output.strip()

    except RuntimeError:
        raise
    except Exception as e:
        logger.error(f"SSH error: {type(e).__name__}: {e}", exc_info=True)
        raise RuntimeError("HPC connection failed.")


async def run_ssh_async(command: str) -> str:
    """Non-blocking SSH — use this in all async route handlers."""
    try:
        return await asyncio.get_running_loop().run_in_executor(
            None, run_ssh_command, command
        )
    except RuntimeError as e:
        detail = str(e)
        if "connection" in detail.lower():
            raise HTTPException(503, detail=f"HPC connection failed: {detail}")
        raise HTTPException(500, detail=f"HPC command failed: {detail}")


# ══════════════════════════════════════════════════════════════════════════
# FILE TRANSFER
# ══════════════════════════════════════════════════════════════════════════

def _transfer_files_sync(
    local_script:  str,
    local_lsf:     str,
    local_sandbox: str,
    unique_id:     str,
    username:      str,
) -> None:
    """
    Transfers job files to HPC cluster via SFTP.

    Directory structure:
      REMOTE_JOB_DIR/
        script_{uuid}.py       ← temporary, deleted after job
        sandbox_{uuid}.py      ← temporary, deleted after job
        job_{uuid}.lsf         ← temporary, deleted after job
        {username}/            ← per-user permanent directory
          job_{uuid}/          ← per-job directory (created by jobs.py)
            output_{uuid}.log  ← created by LSF
            error_{uuid}.log   ← created by LSF
    """
    try:
        ssh  = get_ssh_client()
        sftp = ssh.open_sftp()

        # ── Ensure REMOTE_JOB_DIR exists ──────────────────────────────────
        remote_base = REMOTE_JOB_DIR.rstrip('/')
        if not remote_base.startswith('/'):
            remote_base = f"/{remote_base}"

        try:
            sftp.stat(remote_base)
        except (FileNotFoundError, IOError):
            parts   = remote_base.strip('/').split('/')
            current = ''
            for part in parts:
                current += f'/{part}'
                try:
                    sftp.stat(current)
                except (FileNotFoundError, IOError):
                    try:
                        sftp.mkdir(current)
                    except OSError as e:
                        if e.errno == 13:   # permission denied — already exists
                            continue
                        raise

        # ── Ensure per-user directory exists ──────────────────────────────
        user_dir = f"{remote_base}/{username}"
        try:
            sftp.stat(user_dir)
        except (FileNotFoundError, IOError):
            sftp.mkdir(user_dir)
            sftp.chmod(user_dir, 0o700)
            logger.info(f"Created user directory: {user_dir}")

        # ── Transfer execution files to REMOTE_JOB_DIR root ───────────────
        # These are temporary — the LSF script deletes them after execution
        sftp.put(local_script,  f"{remote_base}/script_{unique_id}.py")
        sftp.put(local_lsf,     f"{remote_base}/job_{unique_id}.lsf")
        sftp.put(local_sandbox, f"{remote_base}/sandbox_{unique_id}.py")

        sftp.close()
        logger.info(
            f"Files transferred: script/sandbox/lsf → {remote_base}/ "
            f"user_dir → {user_dir}/"
        )

    except Exception as e:
        logger.error(f"File transfer failed: {e}", exc_info=True)
        raise RuntimeError(f"File transfer failed: {str(e)}")


async def transfer_files(
    local_script:  str,
    local_lsf:     str,
    local_sandbox: str,
    unique_id:     str,
    username:      str,     # ← NEW parameter
) -> None:
    """Non-blocking file transfer — use in all async route handlers."""
    try:
        await asyncio.get_running_loop().run_in_executor(
            None, _transfer_files_sync,
            local_script, local_lsf, local_sandbox, unique_id, username
        )
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail=str(e))
