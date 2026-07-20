#!/usr/bin/env python3
"""Mock can_test_app for visualization testing.

Usage:
    ./mock_can_test_app.py -a dos -m dt -i vcan0 -s 50
    
Outputs [PRED] and [ALERT] lines in the expected format.
"""

import argparse
import random
import sys
import time


def main():
    parser = argparse.ArgumentParser(description="Mock CAN intrusion detection app")
    parser.add_argument("-a", "--attack", required=True, help="Attack type (dos, fuzzy, gear, rpm, manual)")
    parser.add_argument("-m", "--model", required=True, help="Model (tnn, dt, lr)")
    parser.add_argument("-i", "--interface", required=True, help="CAN interface (vcan0, vcan_viz, etc.)")
    parser.add_argument("-s", "--sample-size", type=int, default=50, help="Sample size for each prediction")
    
    args = parser.parse_args()
    
    attack = args.attack.lower()
    model = args.model.lower()
    interface = args.interface
    sample_size = args.sample_size
    
    print(f"[INFO] Mock detection: attack={attack}, model={model}, interface={interface}, sample_size={sample_size}", flush=True)
    
    counter = 0
    try:
        while True:
            counter += 1
            
            # Randomly generate prediction (0 or 1) — ~10% chance of attack
            prediction = 1 if random.random() < 0.10 else 0
            
            # Output PRED line with timestamp
            ts = time.time()
            print(f"[PRED] {attack}/{model} ts={ts:.6f} prediction={prediction}", flush=True)
            
            # Small delay between predictions
            time.sleep(1)
            
            # Stop after a reasonable number to avoid infinite loops in testing
            if counter >= 100:
                print(f"[INFO] Mock app completed {counter} predictions", flush=True)
                break
    except KeyboardInterrupt:
        print(f"[INFO] Mock app interrupted after {counter} predictions", flush=True)
        sys.exit(0)


if __name__ == "__main__":
    main()
