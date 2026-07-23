"""Silent Windows launcher for the local B360GT control panel."""

from __future__ import annotations

import logging
import os
import json
import ctypes
import subprocess
import sys
import threading
import time
from ctypes import wintypes
from logging.handlers import RotatingFileHandler
from pathlib import Path

import psutil

from .web_ui import run_ui

SINGLE_INSTANCE_MUTEX_NAME = r"Local\B360GT.Background.v1"
ERROR_ALREADY_EXISTS = 183


def _acquire_instance_mutex():
    """Acquire the process-lifetime Windows single-instance mutex."""
    if os.name != "nt":
        return object()

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    create_mutex = kernel32.CreateMutexW
    create_mutex.argtypes = [wintypes.LPVOID, wintypes.BOOL, wintypes.LPCWSTR]
    create_mutex.restype = wintypes.HANDLE
    handle = create_mutex(None, False, SINGLE_INSTANCE_MUTEX_NAME)
    if not handle:
        raise ctypes.WinError(ctypes.get_last_error())
    if ctypes.get_last_error() == ERROR_ALREADY_EXISTS:
        kernel32.CloseHandle(handle)
        return None
    return handle


def _release_instance_mutex(handle) -> None:
    if handle is None or os.name != "nt":
        return
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    close_handle = kernel32.CloseHandle
    close_handle.argtypes = [wintypes.HANDLE]
    close_handle.restype = wintypes.BOOL
    close_handle(handle)


def state_directory() -> Path:
    """Return the per-user background state directory."""
    base = os.environ.get("LOCALAPPDATA")
    if base:
        root = Path(base)
    else:
        root = Path.home() / "AppData" / "Local"
    return root / "b360gt"


def log_path() -> Path:
    return state_directory() / "logs" / "background.log"


def pid_path() -> Path:
    return state_directory() / "background.pid"


def stop_path() -> Path:
    return state_directory() / "background.stop"


def _running_process() -> psutil.Process | None:
    try:
        record = json.loads(pid_path().read_text(encoding="utf-8"))
        process = psutil.Process(int(record["pid"]))
        if abs(process.create_time() - float(record["created"])) > 2:
            return None
        return process
    except (
        OSError,
        ValueError,
        KeyError,
        TypeError,
        json.JSONDecodeError,
        psutil.NoSuchProcess,
        psutil.AccessDenied,
    ):
        return None


def status() -> tuple[bool, int | None]:
    """Return whether the silent service is running and its PID."""
    process = _running_process()
    if process is None:
        pid_path().unlink(missing_ok=True)
        return False, None
    return True, process.pid


def start(*, timeout: float = 5) -> tuple[bool, int]:
    """Start the installed silent Windows entry point."""
    running, pid = status()
    if running:
        return False, int(pid)
    if os.name != "nt":
        raise RuntimeError("b360gt start 目前仅用于 Windows 静默后台入口")

    executable = Path(sys.executable).with_name("b360gt-background.exe")
    if not executable.is_file():
        raise RuntimeError(
            "找不到 b360gt-background.exe；请先在虚拟环境中重新安装项目"
        )
    process = subprocess.Popen(
        [str(executable)],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        close_fds=True,
        creationflags=(
            subprocess.CREATE_NEW_PROCESS_GROUP
            | subprocess.DETACHED_PROCESS
            | subprocess.CREATE_NO_WINDOW
        ),
    )
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        running, pid = status()
        if running:
            time.sleep(0.25)
            if process.poll() is not None:
                break
            return True, int(pid)
        if process.poll() is not None:
            break
        time.sleep(0.05)
    raise RuntimeError(f"后台服务启动失败；请查看日志：{log_path()}")


def start_main() -> int:
    try:
        started, pid = start()
        if started:
            print(f"B360GT 后台服务已启动（PID {pid}）")
        else:
            print(f"B360GT 后台服务已在运行（PID {pid}）")
        print("控制页面：http://127.0.0.1:8765/")
        return 0
    except RuntimeError as exc:
        print(f"启动失败：{exc}")
        return 1


def status_main() -> int:
    running, pid = status()
    if running:
        print(f"B360GT 后台服务正在运行（PID {pid}）")
        print("控制页面：http://127.0.0.1:8765/")
        return 0
    print("B360GT 后台服务未运行")
    return 1


def request_stop(*, timeout: float = 15) -> bool:
    """Request graceful shutdown and wait for the background process."""
    process = _running_process()
    if process is None:
        pid_path().unlink(missing_ok=True)
        stop_path().unlink(missing_ok=True)
        return False
    stop_path().touch()
    try:
        process.wait(timeout=timeout)
    except psutil.TimeoutExpired as exc:
        raise RuntimeError(
            "B360GT 后台服务未能在安全时限内停止；请查看后台日志"
        ) from exc
    finally:
        pid_path().unlink(missing_ok=True)
        stop_path().unlink(missing_ok=True)
    return True


def stop_main() -> int:
    """Console entry point for graceful background shutdown."""
    try:
        if request_stop():
            print("B360GT 后台服务已停止")
        else:
            print("B360GT 后台服务未运行")
        return 0
    except RuntimeError as exc:
        print(f"停止失败：{exc}")
        return 1


def main() -> int:
    """Run the control panel without opening a browser or console window."""
    instance_mutex = _acquire_instance_mutex()
    if instance_mutex is None:
        return 0

    path = log_path()
    path.parent.mkdir(parents=True, exist_ok=True)

    logger = logging.getLogger("b360gt.background")
    logger.setLevel(logging.INFO)
    logger.propagate = False
    handler = RotatingFileHandler(
        path,
        maxBytes=2 * 1024 * 1024,
        backupCount=3,
        encoding="utf-8",
    )
    handler.setFormatter(
        logging.Formatter("%(asctime)s %(levelname)s %(message)s")
    )
    logger.addHandler(handler)
    shutdown_event = threading.Event()
    owns_pid_record = False
    try:
        existing = _running_process()
        if existing is not None and existing.pid != os.getpid():
            logger.error("B360GT background control panel is already running")
            return 0
        stop_path().unlink(missing_ok=True)
        process = psutil.Process()
        pid_path().parent.mkdir(parents=True, exist_ok=True)
        pid_path().write_text(
            json.dumps(
                {"pid": process.pid, "created": process.create_time()}
            ),
            encoding="utf-8",
        )
        owns_pid_record = True

        def watch_stop_file() -> None:
            while not stop_path().exists():
                time.sleep(0.2)
            shutdown_event.set()

        threading.Thread(
            target=watch_stop_file,
            name="b360gt-stop-file-watcher",
            daemon=True,
        ).start()
        logger.info("Starting B360GT background control panel on 127.0.0.1:8765")
        run_ui(
            port=8765,
            open_browser=False,
            quiet=True,
            shutdown_event=shutdown_event,
        )
        logger.info("B360GT background control panel stopped")
        return 0
    except Exception:
        logger.exception("B360GT background control panel failed")
        return 1
    finally:
        if owns_pid_record:
            pid_path().unlink(missing_ok=True)
            stop_path().unlink(missing_ok=True)
        logger.removeHandler(handler)
        handler.close()
        _release_instance_mutex(instance_mutex)
