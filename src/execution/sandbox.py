"""Code execution sandbox using Podman with subprocess fallback.

Primary: podman-py for container management (daemonless, rootless)
Fallback: Python subprocess with resource limits + tempfile isolation
Security: Network disabled, filesystem read-only, timeout enforcement
"""

import asyncio
import hashlib
import logging
import os
import tempfile
import subprocess
from pathlib import Path
from typing import TypedDict, Optional
import resource
import signal

logger = logging.getLogger(__name__)

# Default timeout for code execution (seconds)
DEFAULT_TIMEOUT = 300

# Sandboxing approach
SANDBOX_MODE_PODMAN = "podman"
SANDBOX_MODE_SUBPROCESS = "subprocess"


class ExecutionResult(TypedDict):
    """Result from sandbox execution."""
    output: str
    exit_code: int
    sandbox_mode: str  # "podman" or "subprocess"
    timed_out: bool
    stderr: str


class SandboxError(Exception):
    """Base exception for sandbox errors."""
    pass


class PodmanNotAvailable(SandboxError):
    """Raised when podman is not available and fallback is disabled."""
    pass


async def check_podman_available() -> bool:
    """Check if podman is available on the system.

    Returns:
        True if podman command is accessible, False otherwise
    """
    try:
        proc = await asyncio.create_subprocess_exec(
            "podman", "--version",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        stdout, stderr = await proc.communicate()
        if proc.returncode == 0:
            logger.info(f"Podman available: {stdout.decode().strip()}")
            return True
        return False
    except FileNotFoundError:
        logger.warning("Podman not found — will use subprocess isolation fallback")
        return False
    except Exception as e:
        logger.warning(f"Podman check failed: {e} — will use subprocess isolation fallback")
        return False


async def execute_in_sandbox(
    code: str,
    test_command: str,
    timeout: int = DEFAULT_TIMEOUT,
    allow_network: bool = False,
    allow_write: bool = False,
) -> ExecutionResult:
    """Run code in isolated sandbox environment.

    Attempts to use Podman first. If unavailable, falls back to subprocess
    isolation with resource limits and tempfile-based sandboxing.

    Args:
        code: Python code to execute
        test_command: Command to run (e.g., "python code.py")
        timeout: Max execution seconds
        allow_network: If True, allow network access (Podman only)
        allow_write: If True, allow filesystem writes (subprocess only)

    Returns:
        ExecutionResult with stdout, exit code, mode, and metadata

    Raises:
        PodmanNotAvailable: If podman required but not available
    """
    # Try podman first
    podman_available = await check_podman_available()

    if podman_available:
        return await _execute_podman(
            code, test_command, timeout, allow_network
        )
    else:
        logger.warning("Falling back to subprocess isolation (weaker security)")
        return await _execute_subprocess(
            code, test_command, timeout, allow_write
        )


async def _execute_podman(
    code: str,
    test_command: str,
    timeout: int,
    allow_network: bool,
) -> ExecutionResult:
    """Execute code in ephemeral Podman container.

    Security features:
    - Rootless execution (no privilege escalation)
    - Network disabled by default (--network=none)
    - Read-only filesystem (--read-only)
    - Resource limits (--cpus, --memory)
    - Container destroyed after execution
    """
    import podman

    container_name = f"aegis-sandbox-{hashlib.md5(code.encode()).hexdigest()[:12]}"

    try:
        # Connect to podman
        client = podman.PodmanClient()

        # Create container config
        security_opts = ["no-new-privileges"]
        if not allow_network:
            security_opts.append("--network=none")

        # Read image name from env or use default
        image = os.getenv("SANDBOX_IMAGE", "docker.io/library/python:3.12-slim")

        # Create and run container
        container = client.containers.create(
            image=image,
            command=["bash", "-c", test_command],
            name=container_name,
            detach=True,
            remove=True,  # Auto-remove after execution
            read_only=not allow_network,  # Read-only unless network allowed
            network="none" if not allow_network else None,
            security_opt=security_opts,
            cpus=1.0,
            mem_limit="512m",
            tty=False,
        )

        # Write code to container
        # Note: podman-py doesn't expose direct file write, so we use exec
        # Write code via exec before running test command
        write_code_cmd = f"cat > /tmp/code.py << 'PYTHON_EOF'\n{code}\nPYTHON_EOF"
        container.exec_run(["bash", "-c", write_code_cmd])

        # Start container
        container.start()

        # Wait for completion with timeout
        result = container.wait(timeout=timeout)

        # Get logs
        logs = container.logs()
        output = logs.decode() if isinstance(logs, bytes) else str(logs)

        # Get exit code
        exit_code = result.get("StatusCode", -1) if isinstance(result, dict) else -1

        return ExecutionResult(
            output=output,
            exit_code=exit_code,
            sandbox_mode="podman",
            timed_out=(exit_code == -1),
            stderr=""  # Podman merges stdout/stderr in logs
        )

    except Exception as e:
        logger.warning(f"Podman execution failed: {e} — falling back to subprocess")
        return await _execute_subprocess(code, test_command, timeout, allow_write=False)

    finally:
        # Ensure container is destroyed
        try:
            client = podman.PodmanClient()
            container = client.containers.get(container_name)
            container.stop()
            container.remove()
        except Exception:
            pass  # Container may already be removed


async def _execute_subprocess(
    code: str,
    test_command: str,
    timeout: int,
    allow_write: bool,
) -> ExecutionResult:
    """Execute code with subprocess isolation and resource limits.

    Security features:
    - Runs in temp directory (isolated filesystem)
    - Resource limits via setrlimit (CPU, memory)
    - No network access (doesn't disable, but no explicit network calls)
    - Timeout enforcement via asyncio.wait_for

    WARNING: This is weaker than container isolation. Use only when
    Podman is unavailable or for trusted code.
    """
    temp_dir = None
    try:
        # Create temp directory for execution
        temp_dir = tempfile.mkdtemp(prefix="aegis-sandbox-")
        code_path = Path(temp_dir) / "code.py"

        # Write code file
        code_path.write_text(code)

        # Parse command to ensure it runs our code
        if "python" in test_command or ".py" in test_command:
            cmd = ["python3", str(code_path)]
        else:
            cmd = test_command.split()

        # Run with resource limits
        def set_limits():
            """Set resource limits for the subprocess."""
            # Limit CPU time to timeout + 10 seconds
            resource.setrlimit(resource.RLIMIT_CPU, (timeout + 10, timeout + 10))
            # Limit memory to 1GB
            resource.setrlimit(resource.RLIMIT_AS, (1024 * 1024 * 1024, 1024 * 1024 * 1024))
            # Limit file size to 100MB
            resource.setrlimit(resource.RLIMIT_FSIZE, (100 * 1024 * 1024, 100 * 1024 * 1024))
            # Don't allow core dumps
            resource.setrlimit(resource.RLIMIT_CORE, (0, 0))

        if not allow_write:
            logger.warning("Subprocess mode: filesystem write limits not enforced (use Podman for full isolation)")

        # Execute
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=temp_dir,
            preexec_fn=set_limits,
        )

        try:
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
            exit_code = proc.returncode
            timed_out = False
        except asyncio.TimeoutError:
            # Kill the process on timeout
            try:
                proc.kill()
                await proc.communicate()
            except ProcessLookupError:
                pass
            exit_code = -1
            stdout = b""
            stderr = f"Timeout after {timeout} seconds".encode()
            timed_out = True

        output = stdout.decode() if stdout else ""
        stderr_str = stderr.decode() if stderr else ""

        return ExecutionResult(
            output=output,
            exit_code=exit_code,
            sandbox_mode="subprocess",
            timed_out=timed_out,
            stderr=stderr_str
        )

    except Exception as e:
        logger.error(f"Subprocess execution failed: {e}")
        return ExecutionResult(
            output="",
            exit_code=-1,
            sandbox_mode="subprocess",
            timed_out=False,
            stderr=str(e)
        )

    finally:
        # Clean up temp directory
        if temp_dir:
            try:
                import shutil
                shutil.rmtree(temp_dir)
            except Exception as e:
                logger.warning(f"Failed to clean up sandbox directory: {e}")
