from __future__ import annotations

import logging
import os
import socket
import subprocess
import sys
import threading
import time
import traceback
import urllib.request
import webbrowser
from pathlib import Path


DEFAULT_PORT = 17831


def resolve_install_root(*, frozen: bool | None = None, executable: str | None = None) -> Path:
    is_frozen = getattr(sys, "frozen", False) if frozen is None else frozen
    if is_frozen:
        return Path(executable or sys.executable).resolve().parent
    return Path(__file__).resolve().parents[2]


def is_running(port: int) -> bool:
    try:
        with urllib.request.urlopen(
            f"http://127.0.0.1:{port}/api/v1/desktop/status",
            timeout=0.8,
        ) as response:
            return response.status == 200
    except (OSError, ValueError):
        return False


def find_available_port(preferred: int) -> int:
    for port in range(preferred, preferred + 10):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
            try:
                probe.bind(("127.0.0.1", port))
            except OSError:
                continue
        return port
    raise RuntimeError("HuTao Assistant could not find an available local port")


def wait_for_server(port: int, timeout: float = 60.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if is_running(port):
            return True
        time.sleep(0.25)
    return False


def browser_app_executable() -> str:
    candidates = [
        r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    ]
    for candidate in candidates:
        if os.path.isfile(candidate):
            return candidate
    return ""


class _WindowApi:
    """Bridge exposed to the frameless window's custom titlebar controls."""

    def __init__(self) -> None:
        self.window = None
        self.maximized = False

    def minimize(self) -> None:
        if self.window:
            self.window.minimize()

    def toggle_maximize(self) -> None:
        if not self.window:
            return
        if self.maximized:
            self.window.restore()
        else:
            self.window.maximize()
        self.maximized = not self.maximized

    def close(self) -> None:
        if self.window:
            self.window.destroy()


def open_app_window(url: str) -> str:
    """Open the local app in the most native window available.

    Returns a short label describing which backend was used so callers can log it.
    The chain is deliberately resilient: if the preferred native backend is not
    installed or fails to start, we fall back instead of crashing.
    """
    # 1) pywebview: a real frameless native window with its own taskbar icon.
    try:
        import webview  # type: ignore

        api = _WindowApi()
        window = webview.create_window(
            "AI 助手",
            url,
            width=1280,
            height=820,
            min_size=(920, 620),
            background_color="#121318",
            frameless=True,
            easy_drag=True,
            js_api=api,
        )
        api.window = window
        webview.start()
        return "native"
    except Exception as exc:  # noqa: BLE001 - optional dependency, must not crash
        logging.info("pywebview unavailable, falling back: %s", exc)

    # 2) Chromeless app window via Edge/Chrome: standalone window, no tabs/address bar.
    executable = browser_app_executable()
    if executable:
        try:
            subprocess.Popen(
                [
                    executable,
                    f"--app={url}",
                    "--no-first-run",
                    "--no-default-browser-check",
                ],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            return "app-window"
        except OSError as exc:
            logging.info("app-window fallback failed: %s", exc)

    # 3) System default browser tab (previous behaviour).
    webbrowser.open(url)
    return "browser"


def configure_process_logging(logs_root: Path) -> None:
    log_path = logs_root / "launcher.log"
    output = log_path.open("a", encoding="utf-8", buffering=1)
    if sys.stdout is None:
        sys.stdout = output
    if sys.stderr is None:
        sys.stderr = output
    logging.basicConfig(
        filename=log_path,
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
        encoding="utf-8",
        force=True,
    )


def main() -> None:
    install_root = resolve_install_root()
    if str(install_root) not in sys.path:
        sys.path.insert(0, str(install_root))
    os.chdir(install_root)
    os.environ.setdefault("HUTAO_INSTALL_ROOT", str(install_root))
    logs_root = install_root / "logs"
    logs_root.mkdir(parents=True, exist_ok=True)
    configure_process_logging(logs_root)

    preferred_port = int(os.environ.get("PORT", str(DEFAULT_PORT)))

    if is_running(preferred_port):
        open_app_window(f"http://127.0.0.1:{preferred_port}/app")
        return

    port = find_available_port(preferred_port)
    app_url = f"http://127.0.0.1:{port}/app"

    import uvicorn
    from app.main import app

    server = uvicorn.Server(
        uvicorn.Config(
            app,
            host="127.0.0.1",
            port=port,
            loop="app.loop_factory:selector_loop_factory",
            log_level="info",
        )
    )
    thread = threading.Thread(target=server.run, name="hutao-server", daemon=True)
    thread.start()

    if not wait_for_server(port):
        logging.error("Local service did not become ready in time")
        if sys.stderr is not None:
            print("胡桃助手本地服务启动超时，请查看 logs\\launcher.log。", file=sys.stderr)
        return

    window_backend = open_app_window(app_url)
    logging.info("App window opened via backend: %s", window_backend)

    if window_backend == "native":
        # pywebview already blocked until the window closed; stop the local service.
        server.should_exit = True
        thread.join(timeout=5)
    else:
        # Fallback windows are detached processes; keep this process (and the
        # local service) alive until the user closes or uninstalls the app.
        thread.join()


if __name__ == "__main__":
    try:
        main()
    except Exception:
        logging.exception("HuTao Assistant failed to start")
        if sys.stderr is not None:
            traceback.print_exc(file=sys.stderr)
        if sys.platform == "win32":
            import ctypes

            ctypes.windll.user32.MessageBoxW(
                None,
                "胡桃助手启动失败，请查看安装目录下的 logs\\launcher.log。",
                "HuTao Assistant",
                0x10,
            )
        raise SystemExit(1)
