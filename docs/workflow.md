# General workflow/dataflow for training pipeline

## 1. Load/Generate CAN bus dataset

### Standard CAN data structure
Input data must conform to the format of the open-source research dataset (Car Hacking Dataset) to ensure compatibility with subsequent processing modules.

- **Timestamp:** Real-time (seconds) to determine the frequency of message transmission.

- **CAN ID:** Device identifier (e.g., 0x130 for a transmission controller).

- **DLC & Data Payload:** Data length (0-8 bytes) and detailed message content.

- **Flag (Label):** The most important marker: R (Normal) or T (Attack).

### Two methods for initializing data
The system allows for the creation of simulated data in cases where actual datasets are unavailable:

- **Loading Real Dataset:**

    - Use the ``load_can_dataset`` or ``load_multi_attack_dataset`` functions to read CSV files from real vehicle tests.

    - The system automatically handles variable-length data lines (e.g., when DLC < 8) by adding zero bytes to ensure the data matrix remains consistent.

- **Synthetic Generation:**

    - Use the ``generate_synthetic_can_data`` function when real hardware or logs are unavailable.

    - **Normal Traffic:** Generated with fixed IDs and stable inter-arrival times.

    - **Attack Traffic:** Simulated by injecting high-frequency messages or random IDs to create statistical anomalies.

### Multi-class Attack Labeling
In this step, data is not only divided into "Attack/Normal" but also further categorized based on file names or data characteristics:

- **DoS (Label 1):** Denial-of-service attack by flooding the bus.

- **Fuzzy (Label 2):** ​​Attack by sending random IDs and data.

- **Gear/RPM Spoofing (Labels 3 & 4):** Attack by spoofing specific sensor values.

## 2. Preprocessing data frames
### Type Casting
Machine learning cannot work directly with strings. Therefore, data needs to be converted:

- **ID:** Convert from hexadecimal code (e.g., "0x123") to integer (int).

- **Timestamp:** Convert to a floating-point number (float) to calculate the time interval between messages.

- **Payload (Data0-Data7):** Convert all 8 bytes of data to integers (0-255).

### Numerical Labeling
The system converts text markup flags into numerical labels to train the model:

- **Binary:** Sets Flag R to 0 (Normal) and other flags to 1 (Attack).

- **Multi-class:** If there is an ``attack_type`` column, it will retain its value (0-4) to specifically classify the attack type (DoS, Fuzzy, gear, RPM).

### Sorting & Cleaning
For the Sliding Window technique to work correctly, the data must ensure sequentiality and integrity:

- **Time-based sorting:** Data is sorted in ascending order by the Timestamp column.

- **Missing Value Handling:** Removes rows without Timestamps or compensates for missing zeros in data columns to ensure the input matrix is ​​always complete.

## 3. Engineer features
This step is the most crucial stage in converting the data into mathematical features that the AI ​​model can understand using a fixed-window segmentation technique.
### Windowing Technique
Instead of analyzing each message individually, the system groups consecutive messages into fixed-size windows (default is 50 or 100 frames).
In the current implementation, these windows are **non-overlapping**: the data is partitioned into consecutive chunks of `window_size` frames rather than using a true sliding window with a configurable stride.
Each window generates **a unique Feature Vector** representing the network's behavior during that time period.

### Extracting 46 Specific Features: 
Each window was analyzed to extract 4 groups of metrics: 
- **ID Frequency (22 metrics):** Calculates the occurrence rate of the 20 most common IDs, includes one aggregated **other IDs** bucket for all remaining IDs, and measures network entropy through Shannon Entropy. 

- **Time (4 metrics):** Calculates the **mean**, standard deviation (**Std**), **min**, and **max** of the time interval between messages ($\Delta t$) to detect attacks. 
- **Payload Content (17 metrics):** Statistically calculates the mean/standard deviation of each data byte and calculates **Hamming Weight** (total number of '1' bits). 
- **Speed ​​& Novelty (3 metrics):** Measures the number of messages per second (Message Rate) and the rate of unusual IDs appearing on the bus.

### Window Labeling: 
- **Binary mode:** A window is considered "Attack" (label 1) if it contains at least one malicious message. 
- **Multi-class mode:** The window's label is determined by the type of attack that predominates within that window (e.g., DoS or Fuzzy). 

**Result:** A feature matrix $X$ of size (n_windows, 46) and a corresponding label vector $y$ are ready for model training.

## 4. Train/test split and scaling
### Data Splitting (Train/Test Split) 
- **Mechanism:** Data from the feature matrix $X$ and label $y$ are split into two separate parts, usually 80% for training and 20% for testing. 
- **Uniform Classification (Stratify):** Uses the stratify=y parameter to ensure that the proportion between classes (e.g., 95% normal, 5% attack) is maintained in both sets, avoiding the situation where the test set has no attack samples. 
### Feature Scaling 
- **Concept:** Uses StandardScaler to bring all 46 features to the same distribution with a mean of 0 and a standard deviation of 1
- **Why is it necessary?:** Features such as Message Rate (which can be in the thousands) and Entropy (only from 0 - 5) have very different scales. Without normalization, features with high values ​​will "overwhelm" features with lower values, causing the learning model to be skewed.

## 5. Train Logistic Regression, Decision Tree, and Tiny Neural Network

### Model training
- Pipeline trains three algorithms so users can compare and select the optimal model in terms of both accuracy and memory resources.

- **Class Balancing:** All three models use the ``class_weight="balanced"`` technique to handle the specifics of CAN data (where attack frames account for a very small percentage of normal frames).

### 3 main AI models

### Logistic Regression
This is the most basic linear classification model. 
- **Principle:** The model calculates the weighted sum of 46 features: $z = w_0 + w_1x_1 + w_2x_2 + ... + w_{46}x_{46}$. The result $z$ is passed through a **Sigmoid** function to force the value to the range $[0, 1]$, representing the probability of an attack. 
- **Embedded structure:** In the file ``tiny_ids_lr_weights.h``, you will see an array of ``coef`` (coefficients $w$) and an ``intercept`` value (intercept coefficient $b$). 
- **Advantages:** Uses very little RAM because it only needs to store 47 real numbers (or integers after quantification). 
- **Limitations:** Difficult to detect attack types with complex combinations of features (non-linear).

### Decision Tree
This model doesn't use matrix multiplication but rather comparison logic. 
- **Principle:** The tree is built from nodes. At each node, the model asks: "Is feature $i$ less than or equal to threshold $X$?". Based on the answer, it will branch left or right until it reaches the "leaf" - which contains the predicted label (0 or 1). 
- **Optimization:** The project limits ``max_depth = 5`` to avoid the tree becoming too deep, saving memory and preventing rote learning of data. 
- **Why is it fast?:** On MCUs, if-else comparisons execute much faster than real number multiplication. This is the ideal model if your system requires extremely low response time (latency).

### Tiny Neural Network (TNN)
This is a model simulating how neural networks work. 
- **Structure (32-16-1):** 
    - **Hidden Layer 1 (32 neurons):** Learns basic feature combinations from 46 inputs. 
    - **Hidden Layer 2 (16 neurons):** Combines information from Layer 1 to understand sophisticated attack behaviors. 
    - **Output Layer:** Returns the final probability. 
    
**ReLU activation function:** Used in the hidden layers to remove negative values ​​($f(x) = max(0, x)$), which speeds up computation and avoids gradient suppression errors during training.


## 6. Evaluate all models and print comparison table

### Performance Evaluation Metrics
The system uses standard metrics to measure model reliability:

- **Accuracy:** The percentage of correct predictions out of the total number of samples.

- **F1-Score:** The most important metric for CAN data, combining the ability to correctly detect attacks and the ability to avoid false positives.

- **Classification Report:** A detailed table for each class (Normal, DoS, Fuzzy, etc.) to show which type of attack the model is weak against.

### Comparison Table
The ``run_pipeline.py`` source code automatically outputs a summary table to give  overview:

- Lists all models (LR, DT, TNN) along with their Acc, F1, and Size metrics.

- Sorts them in descending order of F1-Score to prioritize the smartest models.

**Result:** Select the best model or the model that best suits the resources of the target device.

## 7. Quantize the Tiny Neural Network (INT8)
### Data Type Conversion
Quantization is the process of converting model parameters (Weight) from floating-point number (float32, using 4 bytes/element) to lower-format integers (int8, using only 1 byte/element).

- **Purpose:** Reduce model size by 4 times (e.g., from ~3 KB to ~0.75 KB).

- **Significance:** Helps the model "break" on microcontrollers with extremely limited Flash memory (such as ARM Cortex-M0/M3 or AURIX).

### Symmetric Quantization 
- **Mechanism:** This mechanism maps the range of real numbers to the range of integers symmetrically around the zero point.
- **Scale Factor:** Find the largest absolute value $|maxval|$ of the real weights. The Scale factor is calculated to fit the range $[-maxval, maxval]$ into the integer range $[-127, 127]$.
$$Scale = \frac{max|Weight_{float32}|}{127}$$
- **Formula:** $Weight_{int8} = \text{round}(\frac{Weight_{float32}}{Scale})$.

- **Zero-point:** In symmetric quantification, the zero point of a real number perfectly matches the zero point of an integer ($Zero\_point = 0$), which speeds up computation because there is no need to add offsets in matrix multiplications.

### Essential meaning and practical benefits
Quantizing isn't just about saving space, it changes how the MCU processes data:

#### A. Avoiding Floating Point Units (FPU Avoidance)
Most microcontrollers do not have a hardware floating point unit (FPU).

- If quantization is not performed, the MCU must use software to simulate floating point calculations, which is extremely slow and energy-intensive.

- After quantization, all calculations become integers (Integer Arithmetic), directly utilizing the chip's ALU, resulting in significantly faster response times (Latency).

#### B. Optimizing Memory Bandwidth
In each computation cycle, the CPU needs to load weights from Flash memory.

With int8, a 32-bit register of the MCU can load 4 weights (4 bytes) simultaneously, while with float32 only 1 weight can be loaded. This reduces data bottlenecks and increases overall processing speed.

#### C. Reduced Power Efficiency
Performing integer multiplication consumes significantly less energy than performing floating-point multiplication. This is crucial for automotive ECUs, which prioritize durability and energy efficiency.

### Comparing Quantization Levels
| Level | Size | Accuracy | Compatibility |
|--------|-----|----------|----------|
| **Float32** | 4 Bytes | 99% (original)| Only for powerful chips with FPUs. |
| **Int16** | 2 Bytes | high (>95%) | Balancing size and precision. |
| **Int8** | 1 Byte | Fair (~90 - 95%) | Best for embedded systems, fastest speed.

**In conclusion:** The INT8 quantization step is the "key" to transforming a theoretical AI model into a practical solution that can run smoothly on resource-intensive hardware.

## 8. Export to TFLite (optional)
This step is for systems that support the TensorFlow Lite Micro library.

### The nature of the data inside .tflite file.
A .tflite file is not a readable source code but a binary file structured in **FlatBuffers format**. Its contents include:

- **Execution Graph:** Defines the structure of the neural network layers (Input -> Dense -> ReLU -> Output).

- **Quantized Weights:** Contains the model's knowledge parameters as int8 (1 byte) or int16 (2 bytes) instead of floating-point numbers (4 bytes).

- **Metadata:** Contains version information and, in particular, scale factors so the decoder knows how to multiply or divide these integers to simulate the results of floating-point numbers.

### Deployment
To run a ``.tflite`` file on embedded hardware, the implementation process involves three working components:

1. **Model Loading:** Since the MCU doesn't have an operating system to read the file, the ``.tflite`` file is usually converted into a **C-Array** using the `xxd -i` command to load it directly into ``Flash`` memory.

2. **Interpreter:** Install the **TFLite Micro** library. This library acts as the "engine," reading the schematic in the ``.tflite`` file and performing mathematical calculations.

3. **Tensor Arena:** Declare an empty byte array in **RAM** (called the **Tensor Arena**). This is the space where the interpreter stores intermediate calculation results.

### Validation
- **Accuracy Check:** Run the ``.tflite`` model on computer using the Python API to compare its accuracy with the original model.

- **Latency & Memory:** Ensure the file size after conversion (e.g., ~0.8 KB for TNN) is within the allowed limits of the target device.

## 9. Export selected model(s) to C code

This is the most flexible and lightweight deployment method, allowing AI models to run directly on processing chips without needing to install any additional supporting libraries (such as TensorFlow Lite).

### What is the nature of the data in .c and .h files?
Instead of being stored as a difficult-to-read binary file, the model is now documented into familiar C language components:

- **Header File (.h):** Quantized weights (INT8) are stored as static arrays (``const int8_t``). Scale coefficients (SCALE) are also predefined using ``#define`` codes.

- **Source File (.c):** Contains "computation formulas". This is the source code that executes prediction functions such as ``tiny_ids_tnn_predict()``. It transforms complex AI operations into simple `for` loops (for matrix multiplication) or ``if-else`` statements (for traversing decision trees).

### Deployment

1. **Integration (Include):** Copy the two .c and .h files into hardware project and add the line #include "model.h" to the main source code.

2. **Input Preparation:** Take the 46 features extracted from the CAN network, perform multiplication/division with the available SCALE coefficients in the .h file to bring the data to the correct format required by the model.

3. **Calling the Prediction Function:** Call the ``predict()`` function (e.g., ``tiny_ids_dt_predict(input_data)``). The returned result will immediately tell whether it is a normal message or an attack.

### Benefit

- **Bare-metal security:** The source code does not use dynamic memory (malloc), completely avoiding memory overflow errors or system crashes. This is especially important for specialized automotive chips like the Infineon AURIX.

- **Maximum speed**: For Decision Tree models, converting to an if-else structure makes the chip process data dozens of times faster than running it through an intermediate decoder.

- **Zero-dependency operation:** If the chip is too weak to support complex mathematical libraries (math.h), replace complex functions like expf with a simple lookup table to ensure the system still runs smoothly.

## 10. Print deployment summary.
- **Completion message:** The system prints "Pipeline complete" and displays the absolute path to the output/ directory.

- **File list:** Lists the generated files, including the ``.tflite`` model file, the ``.h`` header files containing weights, and the ``.c`` source files containing inference functions.