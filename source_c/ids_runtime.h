#ifndef IDS_RUNTIME_H
#define IDS_RUNTIME_H

#include <stdbool.h>
#include <stdint.h>
#include <linux/can.h>

#define IDS_FEATURE_SIZE 46

typedef struct {
    unsigned int window_size;
    unsigned int frames_seen;
    unsigned int predictions;
    unsigned int attacks_detected;
    float last_score;
} ids_runtime_t;

void ids_runtime_init(ids_runtime_t *rt, unsigned int window_size);
int ids_runtime_on_frame(ids_runtime_t *rt, const struct can_frame *frame, uint64_t timestamp_us, int *prediction_out);
int run_ids_monitor(const char *ifname, unsigned int duration_sec, unsigned int window_size);

#endif
