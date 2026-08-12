import asyncio
import json
import os
import shutil
import sys
import threading
import time

from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

try:
    import paho.mqtt.client as mqtt

    _MQTT_AVAILABLE = True
except ImportError:
    _MQTT_AVAILABLE = False

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

# _DETECT_ATTACK = ["dos", "fuzzy", "gear", "rpm"]
# _DETECT_MODEL = ["tnn", "dt", "lr"]
_DETECT_ATTACK = ["dos"]
_DETECT_MODEL = ["tnn", "dt"]
_MQTT_HOST = os.getenv("VISUALIZE_MQTT_HOST", "127.0.0.1")
_MQTT_PORT = int(os.getenv("VISUALIZE_MQTT_PORT", "1883"))
_MQTT_TOPIC = os.getenv("VISUALIZE_MQTT_TOPIC", "/ids")
_MQTT_CLIENT_ID = os.getenv("VISUALIZE_MQTT_CLIENT_ID", "viz-chart2")
_MQTT_USERNAME = os.getenv("VISUALIZE_MQTT_USERNAME", "")
_MQTT_PASSWORD = os.getenv("VISUALIZE_MQTT_PASSWORD", "")
_LAST_DETECTION_VALUES: dict[str, int] = {
    f"{attack_name} - {model_name}": 0
    for attack_name in _DETECT_ATTACK
    for model_name in _DETECT_MODEL
}


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


@app.post("/api/test-publish")
async def api_test_publish(payload: dict[str, Any] | None = None):
    body = payload or {}
    attack = str(body.get("attack-type", body.get("attack_type", "dos"))).lower()
    model = str(body.get("model", "tnn")).lower()
    mode = str(body.get("mode", "inference")).lower()
    pred = body.get("pred")
    if pred is None:
        pred = body.get("data")
    if pred is None:
        pred = 1

    msg = {
        "attack-type": attack,
        "model": model,
        "mode": mode,
        "pred": int(pred),
    }

    if not _MQTT_AVAILABLE:
        return {
            "ok": False,
            "error": "paho-mqtt is not installed. Run: pip install paho-mqtt",
            "message": msg,
        }

    client = mqtt.Client(client_id=f"{_MQTT_CLIENT_ID}-test")
    if _MQTT_USERNAME:
        client.username_pw_set(_MQTT_USERNAME, _MQTT_PASSWORD)

    try:
        client.connect(_MQTT_HOST, _MQTT_PORT, keepalive=30)
        client.publish(_MQTT_TOPIC, json.dumps(msg), qos=0, retain=False)
        client.disconnect()
    except Exception as exc:
        return {
            "ok": False,
            "error": str(exc),
            "message": msg,
        }

    return {
        "ok": True,
        "topic": _MQTT_TOPIC,
        "message": msg,
    }


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


def _build_detection_payload(attack: str, model: str, pred: int) -> dict[str, int]:
    payload = _LAST_DETECTION_VALUES.copy()
    payload[f"{attack} - {model}"] = 1 if pred else 0
    _LAST_DETECTION_VALUES.update(payload)
    return payload


def parse_detection_message(message: dict[str, Any]) -> dict | None:
    attack = str(message.get("attack-type", message.get("attack_type", ""))).lower()
    model = str(message.get("model", "")).lower()
    mode = str(message.get("mode", "")).lower()

    if mode != "inference":
        return None
    if attack not in _DETECT_ATTACK or model not in _DETECT_MODEL:
        return None

    try:
        prediction = int(message.get("pred", 0))
    except (TypeError, ValueError):
        return None

    payload = _build_detection_payload(attack, model, prediction)
    return {
        "attack": attack,
        "model": model,
        "timestamp": int(time.time() * 1000),
        "line": f"[MQTT] attack-type={attack} model={model} mode={mode} pred={prediction}",
        "data": payload,
    }


async def detection_chart2_mqtt():
    if not _MQTT_AVAILABLE:
        while True:
            yield {
                "timestamp": int(time.time() * 1000),
                "source": "chart2",
                "attack": "",
                "model": "",
                "line": "[FAILED] paho-mqtt is not installed. Run: pip install paho-mqtt",
                "data": _build_detection_payload("dos", "tnn", 0),
            }
            await asyncio.sleep(1)

    queue: asyncio.Queue = asyncio.Queue()
    loop = asyncio.get_running_loop()

    client = mqtt.Client(client_id=_MQTT_CLIENT_ID, clean_session=True)
    client.reconnect_delay_set(min_delay=1, max_delay=5)
    if _MQTT_USERNAME:
        client.username_pw_set(_MQTT_USERNAME, _MQTT_PASSWORD)

    def _emit(item: dict[str, Any]) -> None:
        loop.call_soon_threadsafe(queue.put_nowait, item)

    def on_connect(client, userdata, flags, rc):
        if rc == 0:
            client.subscribe(_MQTT_TOPIC)
            _emit(
                {
                    "timestamp": int(time.time() * 1000),
                    "source": "chart2",
                    "attack": "",
                    "model": "",
                    "line": f"[chart2] MQTT connected: {_MQTT_HOST}:{_MQTT_PORT}, topic={_MQTT_TOPIC}",
                    "data": _LAST_DETECTION_VALUES.copy(),
                }
            )
        else:
            _emit(
                {
                    "timestamp": int(time.time() * 1000),
                    "source": "chart2",
                    "attack": "",
                    "model": "",
                    "line": f"[FAILED] MQTT connect rc={rc}",
                    "data": _LAST_DETECTION_VALUES.copy(),
                }
            )

    def on_disconnect(client, userdata, rc):
        _emit(
            {
                "timestamp": int(time.time() * 1000),
                "source": "chart2",
                "attack": "",
                "model": "",
                "line": f"[chart2] MQTT disconnected (rc={rc}); reconnecting...",
                "data": _LAST_DETECTION_VALUES.copy(),
            }
        )

    def on_message(client, userdata, msg):
        try:
            decoded = msg.payload.decode("utf-8")
            message = json.loads(decoded)
        except (UnicodeDecodeError, json.JSONDecodeError):
            return

        parsed = parse_detection_message(message)
        if parsed is not None:
            _emit(parsed)

    client.on_connect = on_connect
    client.on_disconnect = on_disconnect
    client.on_message = on_message

    try:
        while True:
            try:
                client.connect(_MQTT_HOST, _MQTT_PORT, keepalive=30)
                client.loop_start()
                break
            except Exception as exc:
                _emit(
                    {
                        "timestamp": int(time.time() * 1000),
                        "source": "chart2",
                        "attack": "",
                        "model": "",
                        "line": f"[chart2] MQTT reconnecting: {exc}",
                        "data": _LAST_DETECTION_VALUES.copy(),
                    }
                )
                await asyncio.sleep(2)

        while True:
            try:
                item = await asyncio.wait_for(queue.get(), timeout=1.0)
                yield item
            except asyncio.TimeoutError:
                yield {
                    "timestamp": int(time.time() * 1000),
                    "source": "chart2",
                    "attack": "",
                    "model": "",
                    "line": "[chart2] keepalive",
                    "data": _LAST_DETECTION_VALUES.copy(),
                }
    finally:
        try:
            client.loop_stop()
            client.disconnect()
        except Exception:
            pass


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

    await websocket.send_json(
        {
            "timestamp": int(time.time() * 1000),
            "source": "chart2",
            "line": f"[chart2] waiting MQTT: {_MQTT_HOST}:{_MQTT_PORT}, topic={_MQTT_TOPIC}",
        }
    )

    reader = detection_chart2_mqtt()

    try:
        async for payload in reader:
            await websocket.send_json(
                {
                    "timestamp": payload["timestamp"],
                    "source": "chart2",
                    "attack": payload.get("attack", ""),
                    "model": payload.get("model", ""),
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
    except (WebSocketDisconnect, RuntimeError):
        pass
