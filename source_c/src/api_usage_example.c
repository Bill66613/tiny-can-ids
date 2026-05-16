#include <stdio.h>
#include <stdint.h>

#include "dos_ids_dt_weights.h"
#include "dos_ids_tnn_weights.h"

CAN_Frame_t can_window[DOS_IDS_TNN_WINDOW_SIZE]; 
int frame_counter = 0;
int window_count = 1;

void process_new_can_message(uint32_t id, uint8_t dlc, const uint8_t* data, double timestamp) {
    can_window[frame_counter].id = id;
    can_window[frame_counter].dlc = dlc;
    can_window[frame_counter].timestamp = timestamp;
    for(int i = 0; i < 8; i++) can_window[frame_counter].data[i] = data[i];
    frame_counter++;

    if (frame_counter == DOS_IDS_TNN_WINDOW_SIZE) {
        printf("\n=== EVALUATING WINDOW #%d ===\n", window_count++);

        int dt_result = 0;
        int tnn_result = 0;

        dos_ids_dt_process_window(can_window, &dt_result);
        dos_ids_tnn_process_window(can_window, &tnn_result);

        printf(">>> DT PREDICTION  : %s\n", dt_result == 1 ? "[WARNING] DOS ATTACK!" : "[STATUS] NORMAL");
        printf(">>> TNN PREDICTION : %s\n", tnn_result == 1 ? "[WARNING] DOS ATTACK!" : "[STATUS] NORMAL");

        frame_counter = 0; 
    }
}

int main() {
    uint8_t data_normal[8] = {0x11, 0x22, 0x33, 0x44, 0x55, 0x66, 0x77, 0x88};
    uint8_t data_attack[8] = {0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00};
    
    double current_time_us = 1000000.0; 

    printf("Starting Hybrid CAN Bus Stream Simulation...\n");

    for (int i = 0; i < 200; i++) {
        uint32_t current_id;
        double dt_us;
        uint8_t* current_data;

        // ----------------------------------------------------
        // Window 1 & 2 (Frame 0 -> 99): TRẠNG THÁI BÌNH THƯỜNG
        // ----------------------------------------------------
        if (i < 100) {
            current_id = 0x100 + (i % 10); 
            dt_us = 500.0; // 10ms -> ~100 msg/s
            current_data = data_normal;
            data_normal[0]++; 
        }
        
        // ----------------------------------------------------
        // Window 3 (Frame 100 -> 149): TRỘN LẪN (MIXED)
        // 30 frame đầu bình thường, 20 frame sau bị bơm DoS
        // ----------------------------------------------------
        else if (i >= 100 && i < 150) {
            if (i < 130) {
                current_id = 0x100 + (i % 10);
                dt_us = 500.0;           
                current_data = data_normal;
                data_normal[0]++;
            } else {
                // Tấn công DoS: Gửi mã ID ưu tiên cực cao (0x000), Data tĩnh, tốc độ chớp nhoáng
                current_id = 0x000;
                dt_us = 100.0; // 0.1ms 
                current_data = data_attack;
            }
        }
        
        // ----------------------------------------------------
        // Window 4 (Frame 150 -> 199): THUẦN DOS ATTACK
        // ----------------------------------------------------
        else {
            current_id = 0x000;
            dt_us = 100.0;
            current_data = data_attack;
        }

        current_time_us += dt_us;
        process_new_can_message(current_id, 8, current_data, current_time_us);
    }

    printf("\nSimulation Completed.\n");
    return 0;
}