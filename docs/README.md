# TinyML CAN-IDS Deployment Architectures

This directory documents three realistic deployment approaches for placing the TinyML-based CAN bus intrusion detection system on different automotive compute nodes.

## Deployment Targets at a Glance

| Aspect | **TCU / NAD** | **MCU** | **ECU** |
|--------|---------------|---------|---------|
| **Platform** | Linux (Yocto/AGL) on Cortex-A | Bare-metal / RTOS on Cortex-M | AUTOSAR Classic on Cortex-M/R |
| **Typical HW** | Qualcomm SA515M, i.MX8, Cinterion ELS62 | STM32F4/H7, NXP S32K, TI Hercules | Infineon AURIX TC3xx, NXP S32G |
| **RAM** | 256 MB – 1 GB | 64 KB – 1 MB | 256 KB – 4 MB |
| **Flash** | 256 MB – 4 GB | 256 KB – 2 MB | 2 MB – 16 MB |
| **CAN Access** | Via SocketCAN / CAN-over-IP | Direct CAN peripheral (MCAN) | Native CAN controller + MCAL |
| **ML Runtime** | TFLite, ONNX Runtime, Python, native C | Hand-written C (INT8) or CMSIS-NN | C library via AUTOSAR SWC |
| **Inference Time** | < 1 ms (overkill) | 50–500 us (tight budget) | 100 us – 2 ms |
| **Model Form** | `.tflite` / `.onnx` / shared-object | Static C arrays (INT8 weights) | Static C arrays inside SWC |
| **Update Path** | OTA via package manager | OTA via bootloader (A/B) | OTA via AUTOSAR UCM / UDS |

## Subdirectories

| Directory | Description |
|-----------|-------------|
| [`tcu-nad/`](tcu-nad/) | TCU / NAD (Telematics Control Unit / Network Access Device) — Linux environment with rich resources. Best for rapid prototyping, cloud-connected analytics, and running full Python or TFLite models. |
| [`mcu/`](mcu/) | MCU (Microcontroller Unit) — Bare-metal or RTOS. Runs the hand-coded INT8 C inference directly on the CAN controller. Lowest latency, tightest resource constraints. |
| [`ecu/`](ecu/) | ECU (Electronic Control Unit) — AUTOSAR-integrated deployment. Inference runs as an AUTOSAR SWC, consuming CAN data via the COM stack and raising DTCs on intrusion. |

## Which Approach to Choose?

```
                    ┌─────────────────────────────────────────┐
                    │  Do you have a Linux-based TCU/NAD?     │
                    └────────────┬───────────────┬────────────┘
                                 │ YES           │ NO
                                 ▼               ▼
                    ┌────────────────┐  ┌──────────────────────────┐
                    │  TCU/NAD path  │  │ Is the target AUTOSAR?   │
                    │  (easiest,     │  └──────┬───────────┬───────┘
                    │   most capable)│         │ YES       │ NO
                    └────────────────┘         ▼           ▼
                                     ┌──────────────┐ ┌──────────┐
                                     │  ECU path    │ │ MCU path │
                                     │  (AUTOSAR    │ │ (bare    │
                                     │   SWC)       │ │  metal)  │
                                     └──────────────┘ └──────────┘
```

### Decision Factors

1. **Time-to-prototype**: TCU/NAD >> MCU > ECU
2. **Latency / determinism**: MCU > ECU > TCU/NAD
3. **Integration with existing ECU networks**: ECU >> MCU > TCU/NAD
4. **OTA / remote analytics**: TCU/NAD >> ECU > MCU
5. **ASIL certification path**: ECU > MCU >> TCU/NAD
6. **Development toolchain complexity**: MCU < TCU/NAD < ECU

## Relationship to the Current Pipeline

The existing `tiny-can-ids` pipeline already generates artifacts for **all three** deployment targets:

| Pipeline Output | TCU/NAD | MCU | ECU |
|-----------------|---------|-----|-----|
| `tiny_ids_model.tflite` | Primary model format | Not used | Not used |
| `tiny_ids_weights.h` | Optional (C fallback) | Primary | Primary |
| `tiny_ids_inference.c` | Optional (C fallback) | Primary | Wrapped in SWC |
| Python model (`.pkl`) | Direct use possible | Not used | Not used |

## Architecture Diagram Legend

Throughout the subdirectory docs, diagrams use the following conventions:

```
┌──────────┐    Solid box     = hardware/OS component
│          │
└──────────┘

┌ ─ ─ ─ ─ ┐    Dashed box    = software module / process
│         │
└ ─ ─ ─ ─ ┘

───────►        Solid arrow   = data flow / CAN frames
─ ─ ─ ─►        Dashed arrow  = control / config / OTA
══════►         Double arrow  = high-bandwidth / bus
```
