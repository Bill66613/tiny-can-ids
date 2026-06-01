# CAN Test App for tiny-can-ids

Linux SocketCAN test app for validating the TinyML CAN IDS inference app.

## Build

```bash
make info
make
```

Build output is placed in `build/<arch>/` (default: `build/native/`):

```bash
./build/native/can_test_app --help
```

## Setup vcan0

```bash
sudo modprobe vcan
sudo ip link add dev vcan0 type vcan
sudo ip link set up vcan0
```

Monitor frames:

```bash
candump vcan0
```

Install can-utils if needed:

```bash
sudo apt-get update
sudo apt-get install -y can-utils
```

## Usage

Detect DoS attack:

```bash
./build/native/can_test_app --interface vcan0 --mode dt --attack-type dos --timeout 10
```

Detect Fuzzy attack:

```bash
./build/native/can_test_app --interface vcan0 --mode tnn --attack-type fuzzy --timeout 10
```

Detect Gear spoofing:

```bash
./build/native/can_test_app --interface vcan0 --mode lr --attack-type gear --timeout 10
```

Detect RPM spoofing:

```bash
./build/native/can_test_app --interface vcan0 --mode dt --attack-type rpm --timeout 10
```

## CSV format

CSV format:

```csv
timestamp,can_id,dlc,data,label
0.000000,164,8,00 11 22 33 44 55 66 77,normal
0.001000,000,8,00 00 00 00 00 00 00 00,dos
```

`can_id` is parsed as hexadecimal. `data` supports either space-separated bytes or compact hex:

```csv
0.001000,164,8,0011223344556677,normal
```

## Notes

- `dos` uses CAN ID `0x000` with zero payload at high rate.
- `fuzzy` generates random CAN IDs and random payloads.
- `gear` and `rpm` spoof frames using simple representative IDs. Adjust IDs/payload layout to match your dataset/vehicle if needed.

## All-in-one Tiny IDS inference

This package includes the generated TinyML model source:

- `tiny_ids_tnn_weights.h`
- `tiny_ids_tnn_inference.c`
- `ids_runtime.c`
- `ids_runtime.h`

The `Makefile` links `tiny_ids_tnn_inference.c`, and that file includes `tiny_ids_tnn_weights.h`, so the binary uses the uploaded trained model weights.