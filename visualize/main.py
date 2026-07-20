import asyncio
import json
import os
import re
import shutil
import sys
import threading
import time

from contextlib import asynccontextmanager

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

# Make the repo root importable so can_attack_sim can be loaded
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

try:
    import can
    from tests.simulation.can_attack_sim import (
        attack_scenario,
        choose_interface,
        _VIRTUAL_SENTINEL,
    )

    _CAN_AVAILABLE = True
except ImportError:
    _CAN_AVAILABLE = False

# ---------------------------------------------------------------------------
# Shared attack state: each key maps to 1 (attacking) or 0 (normal)
# ---------------------------------------------------------------------------

_ATTACK_KEYS = ["dos", "fuzzy", "gear", "rpm", "manual"]
_attack_state: dict[str, int] = {k: 0 for k in _ATTACK_KEYS}
_ATTACK_TYPE_MAP = {
    "Dos": "dos",
    "Fuzzy": "fuzzy",
    "Gear": "gear",
    "RPM": "rpm",
    "Manual": "manual",
}

_SCENARIO_PATH = os.path.join(os.path.dirname(__file__), "test_scenario.json")

_DETECT_ATTACK = ["dos", "fuzzy", "gear", "rpm", "manual"]
_DETECT_MODEL = ["tnn", "dt", "lr"]
_DETECT_BINARY = os.getenv("VISUALIZE_DETECTION_BINARY", "./can_test_app")
_DETECT_INTERFACE = os.getenv("VISUALIZE_DETECTION_INTERFACE", "")
_PREDICTION_RE = re.compile(
    r"^\[(PRED|ALERT)\]\s+([a-z]+)/([a-z]+)\b.*prediction=(\d+)",
    re.IGNORECASE,
)


def _run_scenario_loop() -> None:
    """Background thread: run test_scenario.json forever via attack_scenario."""
    if not _CAN_AVAILABLE:
        return

    def _on_state_change(attack_type: str, active: int) -> None:
        key = _ATTACK_TYPE_MAP.get(attack_type)
        if key:
            _attack_state[key] = active

    iface = choose_interface(
        0
    )  # 0 = first detected CAN interface; falls back to virtual
    if iface == _VIRTUAL_SENTINEL:
        bus = can.Bus(interface="virtual", channel="vcan_viz")
    else:
        bus = can.Bus(interface="socketcan", channel=iface)
    try:
        while True:  # Replay the scenario forever until the process is terminated
            attack_scenario(bus, path=_SCENARIO_PATH, on_state_change=_on_state_change)
    finally:
        bus.shutdown()


@asynccontextmanager
async def lifespan(app: FastAPI):
    t = threading.Thread(target=_run_scenario_loop, daemon=True)
    t.start()
    yield


app = FastAPI(lifespan=lifespan)
app.mount("/static", StaticFiles(directory="static"), name="static")


@app.get("/")
def index():
    return FileResponse("static/index.html")


async def read_json_command(command: str):
    process = await asyncio.create_subprocess_shell(
        command,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )

    try:
        while True:
            line = await process.stdout.readline()

            if not line:
                break

            text = line.decode(errors="replace").strip()

            try:
                yield json.loads(text)
            except Exception:
                yield {"raw": text}

    finally:
        process.terminate()
        await process.wait()


async def read_log_command(command: str):
    process = await asyncio.create_subprocess_shell(
        command,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )

    try:
        while True:
            line = await process.stdout.readline()

            if not line:
                break

            yield line.decode(errors="replace").rstrip()

    finally:
        process.terminate()
        await process.wait()


async def simulation_chart():
    while True:
        yield {
            "dos": _attack_state["dos"],
            "fuzzy": _attack_state["fuzzy"],
            "gear": _attack_state["gear"],
            "rpm": _attack_state["rpm"],
            "manual": _attack_state["manual"],
        }
        await asyncio.sleep(0.5)


def _resolve_detection_interface() -> str:
    if _DETECT_INTERFACE:
        return _DETECT_INTERFACE

    if _CAN_AVAILABLE:
        iface = choose_interface(0)
        if iface == _VIRTUAL_SENTINEL:
            return "vcan_viz"
        return iface

    return "vcan0"


def _build_detection_commands() -> list[list[str]]:
    interface = _resolve_detection_interface()
    commands: list[list[str]] = []

    for attack in _DETECT_ATTACK:
        for model in _DETECT_MODEL:
            commands.append(
                [
                    _DETECT_BINARY,
                    "-a",
                    attack,
                    "-m",
                    model,
                    "-i",
                    interface,
                    "-s",
                    "50",
                ]
            )

    return commands


def parse_detection_line(line: str) -> dict | None:
    match = _PREDICTION_RE.match(line.strip())
    if not match:
        return None

    attack = match.group(2).lower()
    model = match.group(3).lower()
    prediction = int(match.group(4))

    if attack not in _DETECT_ATTACK or model not in _DETECT_MODEL:
        return None

    payload = {name: 0 for name in _DETECT_ATTACK}
    payload[attack] = min(prediction, 1)
    return {
        "attack": attack,
        "model": model,
        "line": line,
        "data": payload,
    }


async def _stream_detection_command(command: list[str], queue: asyncio.Queue):
    process = await asyncio.create_subprocess_exec(
        *command,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
    )

    try:
        while True:
            line = await process.stdout.readline()

            if not line:
                break

            text = line.decode(errors="replace").rstrip()
            parsed = parse_detection_line(text)
            if parsed is not None:
                await queue.put(parsed)
    finally:
        if process.returncode is None:
            process.terminate()
        await process.wait()
        await queue.put(None)


async def detection_chart2():
    commands = _build_detection_commands()
    queue: asyncio.Queue = asyncio.Queue()
    tasks = [
        asyncio.create_task(_stream_detection_command(command, queue))
        for command in commands
    ]
    active_tasks = len(tasks)

    try:
        while active_tasks > 0:
            item = await queue.get()
            if item is None:
                active_tasks -= 1
                continue

            yield item
    finally:
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)


async def candump_log(interface: str):
    if shutil.which("candump"):
        async for line in read_log_command(f"candump {interface}"):
            yield line
    elif shutil.which("tdr_can_dump"):
        async for line in read_log_command(f"tdr_can_dump {interface} 0 0"):
            yield line
    else:
        yield "[FAILED] No CAN dump tool found (candump / tdr_can_dump)"
        return


@app.websocket("/ws/chart1")
async def websocket_chart1(websocket: WebSocket):
    await websocket.accept()

    reader = simulation_chart()

    try:
        async for payload in reader:
            await websocket.send_json(
                {
                    "timestamp": int(time.time() * 1000),
                    "source": "chart1",
                    "data": payload,
                }
            )
    except WebSocketDisconnect:
        pass


@app.websocket("/ws/chart2")
async def websocket_chart2(websocket: WebSocket):
    await websocket.accept()

    await websocket.send_json(
        {
            "timestamp": int(time.time() * 1000),
            "source": "chart2",
            "modes": {
                "attacks": _DETECT_ATTACK,
                "models": _DETECT_MODEL,
            },
        }
    )

    detection_commands = _build_detection_commands()
    if not detection_commands:
        await websocket.send_json(
            {
                "timestamp": int(time.time() * 1000),
                "source": "chart2",
                "line": "[FAILED] No detection commands configured",
            }
        )
        await websocket.close()
        return

    await websocket.send_json(
        {
            "timestamp": int(time.time() * 1000),
            "source": "chart2",
            "line": "[chart2] commands: "
            + "; ".join(" ".join(command) for command in detection_commands),
        }
    )

    reader = detection_chart2()

    try:
        async for payload in reader:
            await websocket.send_json(
                {
                    "timestamp": int(time.time() * 1000),
                    "source": "chart2",
                    "attack": payload["attack"],
                    "model": payload["model"],
                    "line": payload["line"],
                    "data": payload["data"],
                }
            )
    except WebSocketDisconnect:
        pass


@app.websocket("/ws/log")
async def websocket_log(websocket: WebSocket):
    await websocket.accept()

    if _CAN_AVAILABLE:
        iface = choose_interface(0)
        if iface == _VIRTUAL_SENTINEL:
            iface = "vcan_viz"
        reader = candump_log(iface)
    else:
        reader = candump_log("vcan0")  # fallback virtual interface

    try:
        async for line in reader:
            await websocket.send_json(
                {
                    "timestamp": int(time.time() * 1000),
                    "source": "log",
                    "line": line,
                }
            )
    except WebSocketDisconnect:
        pass
