# TinyML Model Benchmarking Specification
## 1. Overview
Benchmark in TinyML is the standardized process of measuring the **performance, energy efficiency, and accuracy** of machine learning models running on resource-constrained embedded systems. The primary objective is to evaluate how effectively the model processes inputs and produces results within tight memory, power, and latency budgets.

## 2. Key Metrics in TinyML

**1. Inference Latency:** The time required for AI model to process a single unit of data (e.g., a window of 50 CAN frames). The goal is to match or exceed the real-time requirements of the CAN Bus (500kbps - 1Mbps).

**2. Accuracy & Quality:** Model meet specific target thresholds to qualify, ensuring the model remains valid after optimization.

**3. Memory Usage:** Consumption of Flash (ROM) for model storage and RAM for runtime execution.

**4. CPU Utilization:** The percentage of processor load dedicated to AI tasks, ensuring headroom for other critical ECU/TCU functions.

**5. Energy Consumption:** Measured in microjoules (μJ) per inference, critical for always-on battery-powered applications.

## 3. Benchmarking Methodology: What We Measure
**A. Accuracy & Quality Benchmark**
* **Host-Target Cross-Validation:** We run the same data on both the Python reference model and the exported C/TFLite model. A deviation (Delta) > 1-2% indicates that the Quantization process has compromised the model's logic.

**B. Latency Benchmark**
* **Host-side Timing:** Measured using system-level functions (e.g., time.time()). To mitigate OS background noise, we apply the μ+2σ (Mean + 2 Standard Deviations) threshold to identify and filter performance regressions.
* **On-chip Cycle Counting:** The standard for embedded systems. We use hardware counters (e.g., DWT->CYCCNT) to measure the exact clock cycles consumed by the model, providing nanosecond precision.

**C. Memory Usage**
* **Static Analysis (Flash):** Measuring the size of the compiled binary, specifically the .h (weights) and .c (inference logic) files. This determines the permanent storage footprint on the chip.
* **Dynamic Tracking (RAM):** Monitoring the peak memory usage during inference. This includes the Tensor Arena and intermediate buffers required for neural network layer activations.

**D. CPU Utilization**
* **Workload Monitoring:** Determining the CPU load percentage when the model is processing a continuous stream of CAN messages.
* **Significance:** High CPU usage (>80%) leads to thermal throttling and may cause the system to miss high-priority interrupts from the vehicle network.

**E. Power Consumption (Optional)**
* **Physical Measurement:** Using an Oscilloscope and Shunt Resistor on the TCU/MCU power rail to measure instantaneous voltage drops.
* **Energy Efficiency:** Calculated as *Energy = Power × Latency*. Low energy per inference is mandatory for automotive ECUs to prevent battery drain.


## 4. Setup and Execution Steps
1. **Workload Standardization:** Benchmarking is only valid when every model version is tested against the same dataset.
2. **Host-Target Correlation:** Establish the baseline accuracy on a PC (Host) to ensure the C-code logic matches the original Python intent.
3. **On-chip real-world measurement:**
    - Activate the machine cycle counter (DWT) to obtain latency accurate to the nanosecond.
    - Scan RAM memory to find peak usage points.
    - Monitor CPU percentage via the embedded operating system or debugger.
    - (Optional) Connect a shunt resistor and use an oscilloscope to measure instantaneous power.

## 5. Performance Targets: "What is Considered Good?"

| Metric | Target Threshold | Technical Explaination | 
|--------|------------------|-------------------------|
| Cross-Val Delta| < 1%-2% |Negligible intelligence loss after INT8 Quantization.|
| Inference Latency | < 500 μs  | Must process data faster than the CAN bus arrival rate. |
| CPU Utilization | < 15% | Reserves 85% of CPU for other vehicle control tasks. |
| RAM Usage | < 20 KB |Fits within the memory limits of low-cost device.|
| Flash Usage | < 50 KB | Minimizes hardware costs.|
| Energy Impact | Minimal | Prevents chip overheating and optimizes power draw. |
