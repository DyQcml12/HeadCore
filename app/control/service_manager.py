from __future__ import annotations

import os
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path

from app.core.config import PROJECT_ROOT


WORKSPACE_ROOT = PROJECT_ROOT.parent
RUNTIME_PYTHON = Path(r"D:\Tool\Progrmming-Tool\anaconda\envs\new\python.exe")
SERVICE_LOG_DIR = PROJECT_ROOT / "logs" / "control-center" / "services"


@dataclass(frozen=True)
class ControlServiceSpec:
    id: str
    label: str
    command: tuple[str, ...]
    cwd: Path
    log_name: str
    controllable: bool = True
    note: str = ""


@dataclass
class ManagedProcess:
    process: subprocess.Popen
    log_file: object
    started_at: float


SERVICE_SPECS: dict[str, ControlServiceSpec] = {
    "hutao_core": ControlServiceSpec(
        id="hutao_core",
        label="Core API",
        command=(
            str(RUNTIME_PYTHON),
            "-m",
            "uvicorn",
            "app.main:app",
            "--host",
            "127.0.0.1",
            "--port",
            "8000",
        ),
        cwd=PROJECT_ROOT,
        log_name="core_api.log",
        controllable=False,
        note="控制中心本身运行在核心 API 内；这里仅展示启动命令，不从页面停止自身。",
    ),
    "gpt_sovits": ControlServiceSpec(
        id="gpt_sovits",
        label="GPT-SoVITS Hu Tao API",
        command=(str(PROJECT_ROOT / "external" / "GPT-SoVITS-v2pro-20250604" / "runtime" / "python.exe"), "api_v2.py", "-a", "127.0.0.1", "-p", "9880", "-c", "GPT_SoVITS/configs/tts_infer.yaml"),
        cwd=PROJECT_ROOT / "external" / "GPT-SoVITS-v2pro-20250604",
        log_name="gpt_sovits_api.log",
        note="Local GPT-SoVITS Hu Tao TTS API on 127.0.0.1:9880.",
    ),
}


_PROCESSES: dict[str, ManagedProcess] = {}


def list_services() -> list[dict[str, object]]:
    cleanup_finished_processes()
    return [service_status(service_id) for service_id in SERVICE_SPECS]


def service_status(service_id: str) -> dict[str, object]:
    spec = get_service_spec(service_id)
    managed = _PROCESSES.get(service_id)
    running = bool(managed and managed.process.poll() is None)
    return {
        "id": spec.id,
        "label": spec.label,
        "controllable": spec.controllable,
        "running": running,
        "pid": managed.process.pid if running and managed else None,
        "cwd": str(spec.cwd),
        "command": " ".join(spec.command),
        "log_path": str(SERVICE_LOG_DIR / spec.log_name),
        "note": spec.note,
    }


def start_service(service_id: str) -> dict[str, object]:
    spec = get_service_spec(service_id)
    if not spec.controllable:
        raise ValueError(f"Service is not controllable from web UI: {service_id}")
    cleanup_finished_processes()
    if service_id in _PROCESSES and _PROCESSES[service_id].process.poll() is None:
        return service_status(service_id)
    if not spec.cwd.exists():
        raise FileNotFoundError(f"Service cwd not found: {spec.cwd}")
    SERVICE_LOG_DIR.mkdir(parents=True, exist_ok=True)
    log_path = SERVICE_LOG_DIR / spec.log_name
    log_file = log_path.open("a", encoding="utf-8", errors="replace")
    log_file.write(f"\n\n===== control start {spec.label} {time.strftime('%Y-%m-%d %H:%M:%S')} =====\n")
    log_file.flush()
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"
    process = subprocess.Popen(
        list(spec.command),
        cwd=spec.cwd,
        env=env,
        stdout=log_file,
        stderr=subprocess.STDOUT,
        text=True,
    )
    _PROCESSES[service_id] = ManagedProcess(process=process, log_file=log_file, started_at=time.time())
    return service_status(service_id)


def stop_service(service_id: str) -> dict[str, object]:
    spec = get_service_spec(service_id)
    if not spec.controllable:
        raise ValueError(f"Service is not controllable from web UI: {service_id}")
    managed = _PROCESSES.get(service_id)
    if managed is None or managed.process.poll() is not None:
        cleanup_finished_processes()
        return service_status(service_id)
    managed.process.terminate()
    try:
        managed.process.wait(timeout=10)
    except subprocess.TimeoutExpired:
        managed.process.kill()
    close_process_log(managed)
    _PROCESSES.pop(service_id, None)
    return service_status(service_id)


def cleanup_finished_processes() -> None:
    for service_id, managed in list(_PROCESSES.items()):
        if managed.process.poll() is not None:
            close_process_log(managed)
            _PROCESSES.pop(service_id, None)


def close_process_log(managed: ManagedProcess) -> None:
    try:
        managed.log_file.close()
    except Exception:
        return


def get_service_spec(service_id: str) -> ControlServiceSpec:
    if service_id not in SERVICE_SPECS:
        raise ValueError(f"Unsupported service: {service_id}")
    return SERVICE_SPECS[service_id]
