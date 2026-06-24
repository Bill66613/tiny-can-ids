# SUMMARY REPORT OF CAN IDS SIMULATION TEST RESULTS

## 1. DoS/DT Model Evaluation (Denial of Service - Decision Tree)

- **Scenario 1: Baseline Normal (False Positive Check)**
  - **Objective:** Inject a large volume of normal data without any attacks to measure whether the model is overly sensitive and falsely identifies clean packets as attacks.
  - **Result:** The Inference App returned Total Attack Sessions: 0. This indicates that no attacks were detected, confirming the absence of false positives.

- **Scenario 2: DoS with distinct attack sessions**
  - **Objective:** Inject DoS attacks with a uniform number of frames (100 frames) interleaved with Normal traffic across 3 different sessions. This tests the required occupancy ratio of attack frames within a window for successful detection.
  - **Result:** All 3 attack sessions were successfully detected without any being missed.

- **Scenario 3: Interleaved DoS with varied lengths**
  - **Objective:** Inject DoS attacks with varying frame counts (50, 150, 300 frames) interleaved with Normal traffic.
  - **Result:** All 3 injected sessions were accurately detected.

- **Scenario 4: High-Intensity Droplet Attack (Stress Test)**
  - **Objective:** Inject 10 very short DoS attacks (60 frames each), continuously spaced only 0.02 seconds apart.
  - **Result:** Because the 0.02s interval of normal traffic was insufficient to create consecutive normal windows, the inference app successfully grouped all these short bursts into a single prolonged Attack Session. This proves that the Debouncing (anti-fragmentation) mechanism works exactly as designed.

## 2. RPM/DT Model Evaluation (RPM Spoofing - Decision Tree)

- **Scenario 1: Baseline Normal**
  - **Objective:** Inject normal data to check for false positive detections.
  - **Result:** The Inference App returned Total Attack Sessions: 0, meaning no attacks were detected.

- **Scenario 2 & 3: Interleaved RPM (Uniform and Varied Lengths)**
  - **Objective:** Inject RPM attacks with uniform counts (100 frames) and varied counts (50, 150, 300 frames) interleaved with Normal traffic to test the model's detection threshold.
  - **Result:** All 3 sessions in both scenarios were successfully and fully detected.

- **Scenario 4: High-Intensity RPM Droplet Attack**
  - **Objective:** Inject 10 short RPM bursts (60 frames each) spaced 0.02 seconds apart.
  - **Result:** The attack frames were grouped into a single prolonged session, further validating the effectiveness of the Debouncing mechanism in a real-world scenario.

## 3. Evaluation of Dummy Frame Filtering Mechanism

- **Scenario 5: Dummy Frame Injection & Real Attack (Filter Test)**

- **Objective:** Continuously inject dummy frames with ID: 0x400 and Data 00 00 00 00 00 00 00 00, then set a timeout for network stabilization, and finally trigger a high-intensity DoS attack. This scenario tests the ability to automatically remove junk from the hardware (CHUB) without affecting the ability to detect real attacks.

- **Results:**
  - **Data Cleanliness:** The application silently removes all 0x400 packets. These packets are not pushed into the Windows buffer, keeping the terminal clean (no unnecessary logs) and preventing the Total Windows Processed metric from artificially increasing.
  - **AI Reliability:** As soon as a real DoS attack occurred in the later stages, the AI ​​model immediately detected the signal and activated [PRED], accurately recording 1 Attack Session.

- **Assessment:** The pre-processing filter mechanism worked perfectly. It helped protect the integrity of the input data for the AI, saved CPU cycles on the embedded device, and completely prevented the risk of misidentification due to background noise.

## 4. Model Accuracy & Key Findings

- **Model Accuracy & Reliability:** Both the DoS/DT and RPM/DT models demonstrated excellent accuracy throughout the simulation. The models achieved a 0% False Positive rate during the Baseline Normal scenarios and successfully detected 100% of the designated attack sessions across all burst and interleaved scenarios (No False Negatives at the session level).

- **Detection Threshold (Limitation):** During the attack injection process, if the number of attack frames within a given window is less than 15 (which accounts for less than 30% of the window's capacity), that specific window is classified as Normal.

- **System Latency:** When comparing the timestamps, there is a time difference of approximately 10 to 50 milliseconds between the logs output by the inference app and the simulation app.