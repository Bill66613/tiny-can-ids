# CAN Test App for tiny-can-ids

Linux SocketCAN test app for validating the TinyML CAN IDS inference app.

## Build

```bash
make info
make
```

Build output is placed in `build/`:

```bash
./build/can_test_app --help
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

Synthetic normal traffic:

```bash
./build/can_test_app --interface vcan0 --mode synthetic --rate 500 --duration 10
```

DoS attack:

```bash
./build/can_test_app --interface vcan0 --mode attack --attack-type dos --rate 1000 --duration 10
```

Fuzzy attack:

```bash
./build/can_test_app --interface vcan0 --mode attack --attack-type fuzzy --rate 1000 --duration 10
```

Gear spoofing:

```bash
./build/can_test_app --interface vcan0 --mode attack --attack-type gear --rate 100 --duration 10
```

RPM spoofing:

```bash
./build/can_test_app --interface vcan0 --mode attack --attack-type rpm --rate 100 --duration 10
```

Replay CSV:

```bash
./build/can_test_app --interface vcan0 --mode replay --dataset sample.csv --rate 500
```

Replay by timestamp:

```bash
./build/can_test_app --interface vcan0 --mode replay --dataset sample.csv --realtime
```

Loop replay:

```bash
./build/can_test_app --interface vcan0 --mode replay --dataset sample.csv --loop --duration 60
```

JSON stats:

```bash
./build/can_test_app --interface vcan0 --mode attack --attack-type dos --json
```

## CSV format

Expected CSV format:

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

### Generate traffic and run inference on sent frames

```bash
./build/can_test_app --interface vcan0 --mode attack --attack-type dos --rate 1000 --duration 10 --infer-sent
```

### Run IDS monitor only

```bash
./build/can_test_app --interface vcan0 --mode ids --duration 30 --ids-window 64
```

Then send traffic from another terminal:

```bash
./build/can_test_app --interface vcan0 --mode attack --attack-type fuzzy --rate 1000 --duration 10
```

Note: `ids_runtime.c` currently builds a 46-element feature vector from a sliding SocketCAN window. Keep this feature extractor aligned with the Python training feature engineering for best accuracy.
