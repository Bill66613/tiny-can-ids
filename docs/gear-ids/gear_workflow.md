# Gear Spoofing-IDS

## Concept
Develop an **Intrusion Detection System (IDS)** to detect and prevent **Gear Spoofing attacks** on a CAN Bus network. Gear Attack is a form of Targeted Spoofing Attack aimed at the CAN ID responsible for transmitting the status of the gear selector or automatic transmission (P, R, N, D modes), continuously injecting spoofed messages into the network.

The goal of the attack is to deceive the Dashboard into displaying the wrong gear, or more dangerously, to force the Transmission Control Unit (TCU) to perform an unintended gear shift.

## 1. What is Gear Attack?
The core nature of a Gear Attack is very similar to an RPM Attack (both are Spoofing), but it carries its own specific data characteristics and physical consequences.

* **Targeted ID & Payload:** Attackers do not inject data blindly. They perform reverse engineering to find the ID of the gear selector module (e.g., ID `0x043F` in some vehicle models). Then, they must find exactly which data byte dictates P, R, N, or D (e.g., the first byte `0x40` is P, `0x45` is R).

* **High-Frequency Overriding:** The CAN network lacks an authentication mechanism. Because the legitimate gear/transmission ECU is still continuously sending the correct status (e.g., the car is driving in D, sending every 20ms), the attacker is forced to use a computer to inject fake signals (e.g., gear R) at an extremely high frequency (usually 1ms/time) to completely crush the real signal.

* **Discrete State Manipulation:** Unlike RPM, which is a continuous range of values (engine speed increasing or decreasing gradually), Gear consists of discrete states (it can only be P, R, N, or D). Therefore, the data (Payload) of a Gear Attack is usually a completely static byte sequence (Static Payload) repeated over and over.

## 2. Real-World Scenario & Consequences
Imagine a car driving on a highway at a speed of 100 km/h:

* **Normal State:** The gear selector reads the position and sends the message `[State: D (Drive)]` onto the bus every 20ms.

* **Attack Initiation:** The attacker suddenly injects a massive stream of data: `[State: R (Reverse)]` at a rate of 1ms/message.

* **Physical Consequences:**
    - **Dashboard:** The letter D on the instrument cluster immediately flashes or changes to the letter R, causing the driver to panic.
    - **Mechanical Hazard (Extremely Dangerous):** If the Automatic Transmission (TCU) lacks a robust software fail-safe mechanism to reject reverse commands while driving at high speeds, it might attempt to engage Reverse. This would instantly shatter the transmission gears, locking the wheels, leading to a rollover or a severe accident.

## Feature Engineering
To detect this highly destructive attack, the **Decision Tree (DT)** model extracts 7 core features from a sliding window of 50 frames.

### The 7 Core Characteristics for Gear Attack Detection
1. **Dominant ID Frequency (`max_freq`):** The occurrence rate of the most frequent ID in the window.
    - **Normal State:** The gear selector only sends its status at a fairly slow cycle (e.g., 50ms/time). In a 50-frame window, the gear selector's ID accounts for only a tiny fraction (about **1% - 2%**).
    - **During a Gear Attack:** The attacker uses a computer to aggressively flood the gear selector ID (like `0x043F`) at a rate of 1ms/time to force the car into reverse (R). This ID immediately takes over the entire network. `max_freq` will spike to **80% - 100%**. The DT only needs a simple branching rule like `IF max_freq > 0.6` to detect it instantly.

2. **Longest Consecutive ID Sequence (`max_consecutive`):** The maximum length of identical, consecutive IDs.
    - **Normal State:** The electronic control units (ECUs) take turns communicating on the CAN Bus. It is almost unheard of for the transmission ECU to send 2-3 identical messages in a row without being interrupted by another ECU.
    - **During a Gear Attack:** The hacking tool discharges data so fast that the gear selector's transmission frames queue up tail-to-back on the Bus. The DT will see this consecutive sequence jump from 1 to **15, 20, or even 50**.

3. **Shannon ID Entropy (`entropy`):** The randomness/diversity of the ID distribution.
    - **Normal State:** A car driving on the road will have signals from the brakes, accelerator, steering wheel, transmission, air conditioning... interleaving each other. Diversity is very high ➔ **High entropy**.
    - **During a Gear Attack:** The 50-frame window is flooded by a single spoofed ID. Diversity completely disappears, pushing the **Entropy plummeting close to 0**.

4. **Message Rate (`message_rate`):** The network speed / Number of messages per second.
    - **Normal State:** Network traffic remains stable at the manufacturer's original design level (e.g., **1500 frames/second**).
    - **During a Gear Attack:** The bandwidth is forced to receive thousands of additional spoofed frames, causing the `message_rate` to explode (potentially reaching **8000 frames/second**).

5. **Min Delta (`min_dt`):** The minimum time interval between messages.
    - **Normal State:** Mechanical ECUs always have a signal processing delay. They cannot transmit signals as fast as microseconds.
    - **During a Gear Attack:** Attack tools push data onto the network without regard to hardware delays. `min_dt` will hit the physical limit of the CAN cable.

6. **Mean Δt (`avg_dt`):** The average time interval between messages.
    - **Normal State:** Averages around a few **milliseconds (ms)**.
    - **During a Gear Attack:** The massive amount of stuffed frames causes the average distance to drop drastically to the **microsecond (μs)** level.

7. **Data Change Rate (`data_change_rate`):** The rate at which the Payload data changes.
    - **Normal State:** Signals on the car (RPM, wheel speed) are continuously changing physical values.
    - **During a Gear Attack:** The attacker's goal is to pin the transmission state at a dangerous position (e.g., R - Reverse). They will repeatedly send a completely static byte sequence (e.g., `0x45` for reverse). If within 50 frames, the data sequence has absolutely no shift or change (**Change Rate = 0**), it is an extremely clear sign of a forced gear spoofing attack.