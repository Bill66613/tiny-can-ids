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
This step is the most crucial stage in converting the data into mathematical features that the AI ​​model can understand using the Sliding Window technique.

### Sliding Window Technique
Instead of analyzing each message individually, the system groups consecutive messages into a window (default is 50 or 100 frames).

Each window will generate **a unique Feature Vector** representing the network's behavior during that time period.

### Extracting 46 Specific Features: 
Each window was analyzed to extract 4 groups of metrics: 
- **ID Frequency (22 metrics):** Calculates the occurrence rate of the 20 most common IDs and measures network entropy through Shannon Entropy. 

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
The ``run_pipeline.py`` source code automatically outputs a summary table to give you an overview:

- Lists all models (LR, DT, TNN) along with their Acc, F1, and Size metrics.

- Sorts them in descending order of F1-Score to prioritize the smartest models.

**Result:** Select the best model or the model that best suits the resources of the target device.

## 7. Quantize the Tiny Neural Network (INT8)
### Data Type Conversion
- **Concept:** Converts weights and biases from floating-point numbers (float32, 4 bytes) to integers (int8, 1 byte).

- **Purpose:** Reduces model size by 4 times (from ~3 KB to ~0.8 KB).

### Symmetric Quantization 
- **Mechanism:** Finds the largest absolute value ($max_val$) of the weights in each class. 
- **Scale Factor:** Calculates a scale value to map the range of real numbers to the range of integers from -127 to 127. 
- **Formula:** $Weight_{int8} = \text{round}(\frac{Weight_{float32}}{Scale})$.

### Embedded Benefits
- **Saving Flash/RAM:** The quantized model is extremely compact, easily fitting into the limited memory of the MCU.

- **Increased Computational Speed:** Microcontrollers (such as the ARM Cortex-M series) perform integer multiplications faster and consume less power than floating-point multiplications.

- **Compatibility:** The results of this step will provide static arrays const int8_t for the C file export in the next step.

## 8. Export to TFLite (optional)
This step is for systems that support the TensorFlow Lite Micro library.

- **Conversion:** Use TFLiteConverter to convert the Keras model into a binary .tflite file (flatbuffer).

- **Full-integer Quantization:** Use a representative dataset to align the value ranges, ensuring the model runs entirely in integers for optimal speed.

- **Validation:** Run a test of the .tflite model on computer to ensure accuracy is not significantly reduced after conversion.

## 9. Export selected model(s) to C code

This is the most flexible and lightweight implementation method, requiring no external libraries.

- **Header creation (.h):** Converts the quantified weights (INT8) into static constant arrays (const int8_t). SCALE coefficients are also defined as the ``#define`` macro.

- **Source creation (.c):** Automatically writes the ``ids_predict()`` function. This function performs matrix multiplication loops (for Neural Networks) or tree traversal loops (for Decision Trees).

- **Bare-metal optimization:** The generated source code does not use dynamic memory (malloc), ensuring absolute safety and resource efficiency for chip families such as Infineon AURIX or ARM Cortex-M.

## 10. Print deployment summary.
- **Completion message:** The system prints "Pipeline complete" and displays the absolute path to the output/ directory.

- **File list:** Lists the generated files, including the ``.tflite`` model file, the ``.h`` header files containing weights, and the ``.c`` source files containing inference functions.