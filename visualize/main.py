import asyncio
import json
import os
import random
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


def _run_scenario_loop() -> None:
    """Background thread: run test_scenario.json forever via attack_scenario."""
    if not _CAN_AVAILABLE:
        return

    def _on_state_change(attack_type: str, active: int) -> None:
        key = _ATTACK_TYPE_MAP.get(attack_type)
        if key:
            _attack_state[key] = active

    iface = choose_interface(0)  # 0 = first detected CAN interface; falls back to virtual
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


async def demo_chart2():
    signals = {
        "c": 2,
        "d": 3,
    }

    while True:
        for key in signals:
            signals[key] = max(0, min(3, signals[key] + random.choice([-1, 0, 1])))

        yield signals.copy()
        await asyncio.sleep(0.7)


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
            await websocket.send_json({
                "timestamp": int(time.time() * 1000),
                "source": "chart1",
                "data": payload,
            })
    except WebSocketDisconnect:
        pass


@app.websocket("/ws/chart2")
async def websocket_chart2(websocket: WebSocket):
    await websocket.accept()

    # Demo mode
    reader = demo_chart2()

    # Real command mode
    # reader = read_json_command("your_chart_2_command")

    try:
        async for payload in reader:
            await websocket.send_json({
                "timestamp": int(time.time() * 1000),
                "source": "chart2",
                "data": payload,
            })
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
            await websocket.send_json({
                "timestamp": int(time.time() * 1000),
                "source": "log",
                "line": line,
            })
    except WebSocketDisconnect:
        pass