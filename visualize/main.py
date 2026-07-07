import asyncio
import json
import random
import time

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

app = FastAPI()
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


async def demo_chart1():
    signals = {
        "a": 0,
        "b": 1,
    }

    while True:
        for key in signals:
            signals[key] = max(0, min(3, signals[key] + random.choice([-1, 0, 1])))

        yield signals.copy()
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


async def demo_log():
    counter = 0

    while True:
        counter += 1
        level = random.choice(["INFO", "WARN", "DEBUG", "ERROR"])

        yield f"[{level}] message #{counter} from log command"

        await asyncio.sleep(1)


@app.websocket("/ws/chart1")
async def websocket_chart1(websocket: WebSocket):
    await websocket.accept()

    # Demo mode
    reader = demo_chart1()

    # Real command mode
    # reader = read_json_command("your_chart_1_command")

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

    # Demo mode
    reader = demo_log()

    # Real command mode
    # reader = read_log_command("your_log_command")

    try:
        async for line in reader:
            await websocket.send_json({
                "timestamp": int(time.time() * 1000),
                "source": "log",
                "line": line,
            })
    except WebSocketDisconnect:
        pass