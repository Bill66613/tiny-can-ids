# Optimizing methods for TinyML

When optimizing a TinyML model for resource-constrained devices like MCUs, the primary goal is to **reduce memory footprint (RAM and Flash)** and **inference latency** while maintaining an acceptable level of accuracy. There are several methods are suitable:

## Recommended methods

### 1. INT8 Quantization
This is considered the most suitable method. It compresses the model size by a factor of 4 and enables the model to run on CPUs that lack floating-point units (FPUs).

- **Mechanism:** It converts floating-point weights and activations to **8-bit integers (INT8)**. The codebase uses symmetric min-max INT8 quantization, where values are mapped to the `[-127, 127]` range.

- **Key Benefits:**
    * **Memory Reduction:** Reduces model size by exactly 4x.
    * **FPU Avoidance:** Enables the model to run on low-cost CPUs that lack Floating Point Units (FPUs) by using integer arithmetic.
    * **Bandwidth Optimization:** A 32-bit CPU register can load four INT8 values simultaneously, significantly speeding up memory access.

### 2. Tree Pruning
This is especially important if using a Decision Tree (DT) model.
- **Mechanism:** By pruning the less important branches of the tree, the model reduces the number of `if-else` statements needed in the generated C code, which significantly increases inference speed. The source code accomplishes this through pruning based on the `max_depth` parameter.

- **Key Benefits:**
    * **Reduced Logic Complexity:** Fewer if-else statements in the generated C code.
    * **Latency Reduction:** Shortens the tree traversal path, allowing for micro-second response times on the CAN bus.

### 3. Feature Selection (RFE)
The current pipeline extracts **46 features**. Reducing this to the 10-15 most critical features means the CPU expends much less effort on preprocessing calculations.

- **Key Benefits:**
    * **Preprocessing Relief:** Saves significant CPU cycles by reducing the statistical calculations (Mean, Std, Entropy) required for every data window before the AI even runs.

### 4. Activation Lookup Tables - LUT
Critical for Neural Networks (TNN) and Logistic Regression (LR).

- **Mechanism:** Instead of calculating complex non-linear functions like Sigmoid or Tanh using expf() (which is computationally expensive), values are pre-calculated and stored in a small static C-array (e.g., 256 entries).
- **Key Benefits:**
    * **Instant Computation:** Replaces heavy mathematical operations with a single memory lookup, drastically reducing latency.

### 5. Fixed-Point Arithmetic
Ensuring 100% integer execution.

- **Mechanism:** Ensures that even intermediate calculations and output scaling are performed using integers (INT32/INT64) rather than floating-point variables.
- **Key Benefits:**
    * **Maximum Efficiency:** Eliminates the need for any software-based float emulation, ensuring the fastest possible execution on bare-metal hardware.

## Unrecommended methods

### 1. Weight Sharing
This method involves clustering similar weights and storing a lookup table. During matrix multiplication, the CPU must perform an extra step to access the lookup table. Its computational complexity makes it unsuitable for the high-speed requirements of CAN networks.

### 2. Huffman Encoding
This is a lossless compression technique that reduces storage size but requires the MCU to decompress the weights into RAM before computation. The decompression process consumes an unacceptable amount of CPU cycles.


## Summary table of TinyML optimization methods

| Method | RAM/Flash Impact | Latency Impact | Recommendation| 
| ------ | ---------------- | -------------- | ------------- | 
| **INT8 Quantization** | High Reduction (4x) | Much Faster | Required | 
| **Tree Pruning**| Moderate Reduction | Faster | Recommended | 
| **Feature Selection** | Low Reduction | Faster (Preprocessing) | Recommended | 
| **Sigmoid LUT** | Negligible (Static Array) | Instant | Recommended |
| **Weight Sharing** | High Reduction | Slower (Overhead) | Not Recommended | 
| **Huffman Encoding** | High Reduction | Very Slow (Decompression) | Not Recommended | 
