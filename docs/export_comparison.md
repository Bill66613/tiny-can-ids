# ``.tflite`` export vs ``.c/.h`` export vs ``ONNX`` format 

The choice between exporting in ``.tflite`` (TensorFlow Lite) format, pure ``.c/.h`` source code, or the open-source ``ONNX`` format depends on the hardware architecture and memory resources of the embedded device. The comparison below details the differences between these two methods based on the project modules:

## 1. Technical nature
- **.tflite (TensorFlow Lite):** This is a binary file (flatbuffer) containing the graph structure of the neural network and quantized weights. To run this file, your device needs an interpreter called **TFLite Micro Interpreter**.

- **.c / .h (C Code Generation):** This is pure C source code. Weights are stored as static arrays, and matrix multiplication operations are written directly into for loops. It doesn't require any interpreter.

- **ONNX (.onnx):** An open format (Open Neural Network Exchange) that allows model conversion between various frameworks (PyTorch, TensorFlow). To run on a device, it requires the ONNX Runtime (ORT).

## 2. Resource Footprint

| **Specifications** | **.tflite (TensorFlow Lite)** | **.c / .h (Source Code)** | ONNX (ORT Web/Mobile) |
|--------|---------------|---------|------------|
| **Included library** | TFLite Micro library integration is required (additional Flash/RAM cost). | Standard math library (math.h) is needed. | Requires ONNX Runtime (typically significantly heavier than TFLite Micro). |
| **Model Size** | It's usually slightly larger because it contains flatbuffer metadata. | Extremely small (TNN ~0.8 KB, LR ~1 KB) because it only contains raw data. | Usually the largest because it's designed to support multiple platforms. |
| **Memory** | TFLite typically requires a cache (Tensor Arena). | No dynamic memory usage; it runs entirely on the stack. | Using flexible memory management is more resource-intensive. |

## 3. Performance & Optimization
- **.tflite:** Advantageous if microcontroller has a dedicated AI accelerator (such as an NPU or ARM's CMSIS-NN instruction sets). TFLite will automatically leverage this hardware to speed up inference.

- **.c / .h:** Best suited for "bare-metal" chips without an AI accelerator. The project's C source code is very clear, making it easy for compilers to optimize for specific chip families like STM32 or Infineon AURIX.

- **ONNX:** Distinguished by its powerful graph optimization capabilities and support for a wide range of hardware (CPU, GPU, NPU) through various Execution Providers.

## 4. Flexibility and Extensibility
- **.tflite:** Only supports the Tiny Neural Network (TNN) model.

- **.c / .h:** Supports all models in the project, including Logistic Regression (LR) and Decision Tree (DT). In particular, the Decision Tree model is converted to an if-else structure, making it much faster than running it through Interpreter.

- **ONNX:** Most flexible because it supports most current AI operators and allows easy conversion from PyTorch to other formats without loss of graph information.

## 5. Deployment Strategy

- **Use .tflite when:** Developing on modern boards (such as Arduino Nano 33 BLE, ESP32, Raspberry Pi) that already support TensorFlow Lite Micro and you want to easily change the network architecture without modifying the C code.

- **Use .c / .h when:** Working with specialized automotive-grade MCUs, where Flash/RAM capacity is extremely valuable and high system security is required (complex external libraries or dynamic memory are not allowed).

- **Use ONNX when:** You need to deploy a model in a browser (Web) via the ONNX Runtime Web or on more powerful Edge devices that require compatibility between different frameworks.