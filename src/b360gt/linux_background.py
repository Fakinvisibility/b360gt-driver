"""systemd user-service controls for the Linux web control panel."""

from __future__ import annotations

import subprocess

SERVICE_NAME = "b360gt-ui.service"
CONTROL_URL = "http://127.0.0.1:8765/"


def _systemctl(*arguments: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["systemctl", "--user", *arguments, SERVICE_NAME],
        check=False,
        capture_output=True,
        text=True,
    )


def _failure_message(result: subprocess.CompletedProcess[str]) -> str:
    detail = result.stderr.strip() or result.stdout.strip()
    return detail or f"systemctl 退出状态为 {result.returncode}"


def status() -> tuple[bool, int | None]:
    """Return whether the UI service is active and its main PID."""
    active = _systemctl("is-active", "--quiet")
    if active.returncode != 0:
        return False, None
    pid_result = _systemctl("show", "--property=MainPID", "--value")
    try:
        pid = int(pid_result.stdout.strip())
    except ValueError:
        pid = 0
    return True, pid or None


def start() -> tuple[bool, int | None]:
    """Start the systemd user service and report whether it was newly started."""
    running, pid = status()
    if running:
        return False, pid
    result = _systemctl("start")
    if result.returncode != 0:
        raise RuntimeError(_failure_message(result))
    running, pid = status()
    if not running:
        raise RuntimeError(
            "systemd 未能保持服务运行；请执行 "
            "journalctl --user -u b360gt-ui.service"
        )
    return True, pid


def request_stop() -> bool:
    """Stop the systemd user service if it is running."""
    running, _pid = status()
    if not running:
        return False
    result = _systemctl("stop")
    if result.returncode != 0:
        raise RuntimeError(_failure_message(result))
    return True


def start_main() -> int:
    try:
        started, pid = start()
    except RuntimeError as exc:
        print(f"启动失败：{exc}")
        return 1
    action = "已启动" if started else "已在运行"
    pid_text = f"（PID {pid}）" if pid is not None else ""
    print(f"B360GT 后台控制台{action}{pid_text}")
    print(f"控制页面：{CONTROL_URL}")
    return 0


def status_main() -> int:
    running, pid = status()
    if not running:
        print("B360GT 后台控制台未运行")
        return 1
    pid_text = f"（PID {pid}）" if pid is not None else ""
    print(f"B360GT 后台控制台正在运行{pid_text}")
    print(f"控制页面：{CONTROL_URL}")
    return 0


def stop_main() -> int:
    try:
        stopped = request_stop()
    except RuntimeError as exc:
        print(f"停止失败：{exc}")
        return 1
    if stopped:
        print("B360GT 后台控制台已停止")
    else:
        print("B360GT 后台控制台未运行")
    return 0
