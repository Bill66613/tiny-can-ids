# RPM Spoofing-IDS

## Concept
Develop an **Intrusion Detection System (IDS)** to detect and prevent **RPM Spoofing attacks** on a CAN Bus network. Unlike DoS attacks that aim to crash the network, RPM Spoofing is a targeted attack designed to manipulate specific vehicle behaviors, requiring a model that can detect subtle frequency anomalies and ID takeovers.

## 1. What is RPM Attack?
RPM (Revolutions Per Minute) Attack on a CAN network is a form of **Targeted Spoofing Attack**. Unlike DoS (which clogs the network with priority ID) or Fuzzy attacks (which inject random noise), an RPM Attack is highly calculated. The attacker specifically targets the communication channel (CAN ID) responsible for reporting the engine speed and injects malicious, fake data.

## 2. Technical Nature (Frequency Overriding Mechanism)
The core nature of an RPM Attack does not lie in disrupting overall bandwidth, but in data manipulation through a signal overriding mechanism.

* **Reverse Engineering & Targeting:** Before initiating the attack, the hacker must perform reverse engineering to pinpoint exactly which ECU (typically the Engine Control Module - ECM) is transmitting the RPM parameters and identify its corresponding CAN ID.

* **Frequency Overriding:** In a CAN network, there is no built-in source authentication mechanism. Any ECU on the network can broadcast a message using any ID.

    - However, the legitimate Engine ECU is still active and continuously broadcasting the correct RPM data (e.g., at a cycle of every 20 milliseconds).

    - To deceive the dashboard display or the automatic transmission, the attacker must inject the spoofed RPM packets at an extremely high frequency (e.g., every 1 millisecond).

    - **Consequence:** The receiving ECUs will be flooded with the spoofed data. They read and update the fake data so rapidly that the legitimate signal is completely overridden and ignored.

## 3. Real-World Scenario & Consequences
To understand the severity, consider a scenario where a vehicle is driving normally on the highway:

* **Normal State:** The Engine ECU reads the sensor and broadcasts a packet to the CAN network with `ID: 0x0316 | Data: [Value equivalent to 2000 RPM]`. The transmission frequency is **20ms/message**. The tachometer needle on the dashboard remains stable at 2000.

* **Attack Initiation:** The attacker starts injecting spoofed data with `ID: 0x0316 | Data: [Value equivalent to 8000 RPM - redline]`. The injection frequency is **1ms/message**.

* **Physical Consequences:**

    - The instrument panel receives twenty 8000 rpm notifications, each at 2000 rpm. The tachometer needle will immediately jump sharply to the maximum limit (8000) and fluctuate violently.

    - **Mechanical hazard:** The transmission control unit (TCU) also reads this ID code `0x0316`. Sensing the engine is running at 8000 rpm, the TCU may misinterpret the situation and perform a sudden gear shift to protect the engine. This can cause severe jerking or mechanical damage to the transmission, even if the driver maintains a steady throttle.

## Feature Engineering
The model utilizes a Sliding Window mechanism with a size of 50 frames/window for analysis.

### Features for Decision Tree (DT - 6 Features)
1. **Dominant ID Frequency (`max_freq`):** The occurrence rate of the most frequent ID in the window.

    - **Normal State:** In the CAN network, ID `0x0316` is sent every 20ms. In a 50-frame window, it typically appears only 1-2 times (accounting for about **2% - 4%**).

    - **During an RPM Attack:** Because the attacker pumps ID `0x0316` at a rate of 1ms/message, this ID will hijack the entire bus. The `max_freq` will spike to **80% - 100%**. The Decision Tree only needs a simple logic threshold (e.g., IF `max_freq` > 0.5) to flag the anomaly.

2. **Longest Consecutive ID Sequence (`max_consecutive`):** The maximum length of identical, consecutive IDs.

    - **Normal State:** It is extremely rare for a single ECU to successfully transmit 2-3 consecutive frames with the same ID (due to other higher-priority ECUs interleaving). This value is usually just **1 or 2**.

    - **During an RPM Attack:** The hacking tool discharges data so rapidly that the `0x0316` frames queue up back-to-back. This value can jump to **10, 20, or even 50** consecutive frames.

3. **Shannon ID Entropy (`entropy`):** The randomness/diversity of the ID distribution.

    - **Normal State:** A healthy CAN network is a rhythmic communication of dozens of different IDs ➔ **High entropy** (high diversity).

    - **During an RPM Attack:** The 50-frame window is now flooded with only one ID (`0x0316`). Diversity completely vanishes, causing the **Entropy to plummet close to 0**.

4. **Message Rate (`message_rate`):** The network speed / Number of messages per second.

    - **Normal State:** Depending on the vehicle, the network speed fluctuates stably within a certain threshold (e.g., **1000 - 2000 frames/s**).

    - **During an RPM Attack:** Cramming thousands of spoofed RPM frames to override the signal will cause the `message_rate` to explode to **8000 - 10000 frames/s**.

5. **Mean Δt (`avg_dt`):** The average time interval between messages.

    - **Normal State:** The average time gap between any two frames on the bus is typically around a few **milliseconds (ms)**.

    - **During an RPM Attack:** Due to the massive volume of frames packed tightly together, the `avg_dt` will drop drastically to the **microsecond (μs)** level.

6. **Min Delta (`min_dt`):** The minimum time interval between messages.

    - **Normal State:** Physical ECUs on a vehicle always possess hardware processing delays; they cannot send two adjacent messages microseconds apart.

    - **During an RPM Attack:** Attack tools (like `cangen`) inject data from a computer software, bypassing physical processing delays. The `min_dt` will hit the absolute bottom limit of the network cable.

### Feature for Tiny Neural Network (TNN - 12 Features)

1. **Mean Δt (`avg_dt` - Average time interval)**

    - **Normal state:** The average time interval between any two frames on the Bus is around a few milliseconds.

    - **During an RPM Attack:** Due to the massive volume of frames packed tightly together, `avg_dt` will drop drastically to the microsecond level.

2. **Std Δt (`std_dt` - Standard deviation of time interval)** *(Extended Feature for TNN)*

    - **Normal state:** Time jitter on the bus exists but is maintained within an acceptable variance.

    - **During an RPM Attack:** Attackers often inject messages asynchronously relative to the network's natural rhythm. This disruption breaks the natural pace, causing the time dispersion (`std_dt`) to change highly abnormally.

3. **Min Δt (`min_dt` - Minimum time interval)**

    - **Normal state:** Physical ECUs on the vehicle always have hardware processing delays; they cannot send two adjacent messages microseconds apart.

    - **During an RPM Attack:** Attack tools (like cangen) pump data without physical delays. `min_dt` will hit the absolute bottom limit of the network cable.

4. **Max Δt (`max_dt` - Maximum time interval)** *(Extended Feature for TNN)*

    - **Normal state:** Controlled by the longest transmission cycle of active ECUs.

    - **During an RPM Attack:** Attackers injecting high-frequency data can "exhaust" bandwidth, preventing the sending of low-priority, legitimate messages. As a result, the time between these legitimate messages is extended, creating unusual "gaps" that increase `max_dt`.

5. **Message Rate (`message_rate` - Network speed / Number of messages per second)**

    - **Normal state:** Depending on the vehicle, the network speed fluctuates stably within a certain threshold (e.g., 1000 - 2000 frames/second).

    - **During an RPM Attack:** Cramming thousands of spoofed RPM frames will cause the `message_rate` to explode (6000 - 8000 frames/s).

6. **Dominant ID Frequency (`max_freq` - Frequency of the most occurring ID)**

    - **Normal state:** In a CAN network, ID 0x0316 is sent every 20ms. In a 50-frame window, it typically appears only 1-2 times (accounting for about 2% - 4%).

    - **During an RPM Attack:** Because the attacker continuously sends ID `0x0316` at a rate of 1ms/message, this ID will take control of the entire bus. `max_freq` will skyrocket to 80% - 100%. A decision tree only needs a threshold such as IF `max_freq` > 0.5 to detect the anomaly.

7. **Shannon ID Entropy (`entropy` - Randomness/Diversity of IDs)**

    - **Normal state:** A CAN network involves communication from dozens of different IDs ➔ High entropy (high diversity).

    - **During an RPM Attack:** The 50-frame window is now flooded with only one ID `0x0316`. Diversity completely vanishes, pushing Entropy down close to 0.

8. **Timing CV (`timing_cv` - Coefficient of Variation of time: std/mean)** *(Extended Feature for TNN)*

    - **Normal state:** This is the normalized ratio between the standard deviation and the mean. In a normal vehicle, this coefficient is quite stable.

    - **During an RPM Attack:** Even if the attacker cleverly adjusts the insertion rate (so that `avg_dt` isn't too low to bypass the rules), the nature of asynchronous message insertion still disrupts `std_dt`. The std/mean ratio amplifies this anomaly, helping TNN detect "stealth" spoofing attacks.

9. **Data Change Rate (`data_change_rate` - Ratio of payload content changes)** *(Extended Feature for TNN)*

    - **Normal state:** Sensors (wheel speed, RPM, steering wheel) continuously update physical values, so the data bytes (Payload) change very smoothly and continuously between transmission frames.

    - **During an RPM Attack:** The goal of a spoofing attack is to trick the dashboard and gauges (e.g., forcing the tachometer to always display 8000 rpm). The attacker typically continuously pumps a static (fixed) payload. This causes the `data_change_rate` (the rate at which frames have different data compared to the previous frame) to suddenly drop to 0 during the attack.
    
10. **Max Consecutive (`max_consecutive` - Longest sequence of consecutive IDs)**

    - **Normal state:** It is extremely rare for an ECU to be allowed to send 2-3 consecutive transmission frames carrying the same ID (due to other ECUs interleaving). This value is usually just 1 or 2.

    - **During an RPM Attack:** The hacking tool discharges data so fast that the `0x0316` transmission frames queue up back-to-back. This value can jump to 10, 20, or even 50 consecutive frames.

11. **High Priority Ratio (`high_priority_ratio` - Ratio of high-priority IDs)** *(Extended Feature for TNN)*

    - **Normal state:** IDs with small values (< 256) carry high priority (like RPM, brakes, steering) and maintain a stable appearance ratio compared to large IDs (Infotainment, AC).

    - **During an RPM Attack:** RPM is a core operational parameter, typically using a very small ID to win arbitration. When an attacker floods this ID, the ratio of IDs < 256 suddenly spikes overwhelmingly compared to the normal equilibrium state.

12. **Unique ID Ratio (`unique_id_ratio` - Ratio of unique IDs)** *(Extended Feature for TNN)*

    - **Normal state:** Within 50 frames, there are usually 15-20 different IDs present (Ratio = 15/50 = 30%).

    - **During an RPM Attack:** Because the fake ID takes up space, other legitimate IDs are pushed back. The number of unique IDs in the window drops sharply (possibly to just 2-3 IDs), and this ratio plummets to an extremely low level.