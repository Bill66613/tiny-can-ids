#include "ids_runtime.h"
#include "can_test_app.h"

#include <errno.h>
#include <math.h>
#include <poll.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>

int tiny_ids_tnn_predict(const float *input, int n_input);

#define IDS_MAX_WINDOW 256

typedef struct {
    struct can_frame frame;
    uint64_t ts_us;
} ids_sample_t;

static ids_sample_t g_window[IDS_MAX_WINDOW];
static unsigned int g_pos = 0;
static unsigned int g_count = 0;
static unsigned int g_window_size = 64;

static void push_frame(const struct can_frame *frame, uint64_t timestamp_us) {
    g_window[g_pos].frame = *frame;
    g_window[g_pos].ts_us = timestamp_us;
    g_pos = (g_pos + 1U) % g_window_size;
    if (g_count < g_window_size) {
        g_count++;
    }
}

static const ids_sample_t *window_at(unsigned int i) {
    unsigned int start = (g_pos + g_window_size - g_count) % g_window_size;
    return &g_window[(start + i) % g_window_size];
}

static float safe_div(float a, float b) {
    return b == 0.0f ? 0.0f : a / b;
}

static void build_features(float out[IDS_FEATURE_SIZE]) {
    memset(out, 0, sizeof(float) * IDS_FEATURE_SIZE);
    if (g_count == 0) return;

    const canid_t tracked_ids[8] = {0x000, 0x043, 0x164, 0x201, 0x260, 0x2A0, 0x316, 0x329};
    float id_counts[8] = {0};
    float dlc_sum = 0.0f;
    float dlc_min = 8.0f;
    float dlc_max = 0.0f;
    float byte_sum[8] = {0};
    float byte_sq_sum[8] = {0};
    float zero_payload_count = 0.0f;
    float ff_payload_count = 0.0f;
    float id_sum = 0.0f;
    float id_sq_sum = 0.0f;
    float intervals_sum = 0.0f;
    float intervals_sq_sum = 0.0f;
    float intervals_min = 1e9f;
    float intervals_max = 0.0f;
    unsigned int unique = 0;
    canid_t ids_seen[IDS_MAX_WINDOW];
    unsigned int ids_seen_n = 0;

    for (unsigned int i = 0; i < g_count; ++i) {
        const ids_sample_t *s = window_at(i);
        canid_t id = s->frame.can_id & CAN_SFF_MASK;
        id_sum += (float)id;
        id_sq_sum += (float)id * (float)id;

        bool known = false;
        for (unsigned int k = 0; k < ids_seen_n; ++k) {
            if (ids_seen[k] == id) { known = true; break; }
        }
        if (!known && ids_seen_n < IDS_MAX_WINDOW) ids_seen[ids_seen_n++] = id;

        for (int k = 0; k < 8; ++k) {
            if (id == tracked_ids[k]) id_counts[k] += 1.0f;
        }

        float dlc = (float)s->frame.can_dlc;
        dlc_sum += dlc;
        if (dlc < dlc_min) dlc_min = dlc;
        if (dlc > dlc_max) dlc_max = dlc;

        bool all_zero = true;
        bool all_ff = true;
        for (int b = 0; b < 8; ++b) {
            float v = b < s->frame.can_dlc ? (float)s->frame.data[b] : 0.0f;
            byte_sum[b] += v;
            byte_sq_sum[b] += v * v;
            if (b < s->frame.can_dlc && s->frame.data[b] != 0x00) all_zero = false;
            if (b < s->frame.can_dlc && s->frame.data[b] != 0xFF) all_ff = false;
        }
        if (all_zero) zero_payload_count += 1.0f;
        if (all_ff) ff_payload_count += 1.0f;

        if (i > 0) {
            const ids_sample_t *prev = window_at(i - 1);
            float dt_ms = (float)(s->ts_us - prev->ts_us) / 1000.0f;
            intervals_sum += dt_ms;
            intervals_sq_sum += dt_ms * dt_ms;
            if (dt_ms < intervals_min) intervals_min = dt_ms;
            if (dt_ms > intervals_max) intervals_max = dt_ms;
        }
    }

    unique = ids_seen_n;
    float n = (float)g_count;
    float ni = g_count > 1 ? (float)(g_count - 1) : 1.0f;
    float id_mean = id_sum / n;
    float id_var = fmaxf(0.0f, id_sq_sum / n - id_mean * id_mean);
    float dlc_mean = dlc_sum / n;
    float int_mean = intervals_sum / ni;
    float int_var = fmaxf(0.0f, intervals_sq_sum / ni - int_mean * int_mean);

    int idx = 0;
    out[idx++] = safe_div((float)g_count, (float)g_window_size);
    out[idx++] = safe_div((float)unique, n);
    out[idx++] = id_mean / 2047.0f;
    out[idx++] = sqrtf(id_var) / 2047.0f;
    out[idx++] = dlc_mean / 8.0f;
    out[idx++] = dlc_min / 8.0f;
    out[idx++] = dlc_max / 8.0f;
    out[idx++] = int_mean / 100.0f;
    out[idx++] = sqrtf(int_var) / 100.0f;
    out[idx++] = intervals_min == 1e9f ? 0.0f : intervals_min / 100.0f;
    out[idx++] = intervals_max / 100.0f;
    out[idx++] = zero_payload_count / n;
    out[idx++] = ff_payload_count / n;

    for (int k = 0; k < 8; ++k) out[idx++] = id_counts[k] / n;
    for (int b = 0; b < 8; ++b) out[idx++] = (byte_sum[b] / n) / 255.0f;
    for (int b = 0; b < 8; ++b) {
        float mean = byte_sum[b] / n;
        float var = fmaxf(0.0f, byte_sq_sum[b] / n - mean * mean);
        out[idx++] = sqrtf(var) / 255.0f;
    }

    const ids_sample_t *last = window_at(g_count - 1);
    out[idx++] = (float)(last->frame.can_id & CAN_SFF_MASK) / 2047.0f;
    out[idx++] = (float)last->frame.can_dlc / 8.0f;
    for (int b = 0; b < 6 && idx < IDS_FEATURE_SIZE; ++b) {
        out[idx++] = (float)last->frame.data[b] / 255.0f;
    }
    while (idx < IDS_FEATURE_SIZE) out[idx++] = 0.0f;
}

void ids_runtime_init(ids_runtime_t *rt, unsigned int window_size) {
    memset(rt, 0, sizeof(*rt));
    if (window_size == 0 || window_size > IDS_MAX_WINDOW) window_size = 64;
    rt->window_size = window_size;
    g_window_size = window_size;
    g_pos = 0;
    g_count = 0;
    memset(g_window, 0, sizeof(g_window));
}

int ids_runtime_on_frame(ids_runtime_t *rt, const struct can_frame *frame, uint64_t timestamp_us, int *prediction_out) {
    if (prediction_out) *prediction_out = -1;
    push_frame(frame, timestamp_us);
    rt->frames_seen++;

    if (g_count < rt->window_size) {
        return 0;
    }

    float features[IDS_FEATURE_SIZE];
    build_features(features);
    int pred = tiny_ids_tnn_predict(features, IDS_FEATURE_SIZE);
    rt->predictions++;
    if (pred) rt->attacks_detected++;
    rt->last_score = (float)pred;
    if (prediction_out) *prediction_out = pred;
    return 1;
}

int run_ids_monitor(const char *ifname, unsigned int duration_sec, unsigned int window_size) {
    int sock = open_can_socket(ifname);
    if (sock < 0) return -1;

    ids_runtime_t rt;
    ids_runtime_init(&rt, window_size);
    uint64_t start = now_us();
    uint64_t end = duration_sec > 0 ? start + (uint64_t)duration_sec * 1000000ULL : 0;

    printf("Starting IDS monitor: interface=%s duration=%u window=%u\n", ifname, duration_sec, rt.window_size);

    while (duration_sec == 0 || now_us() < end) {
        struct pollfd pfd;
        pfd.fd = sock;
        pfd.events = POLLIN;
        int prc = poll(&pfd, 1, 100);
        if (prc < 0) {
            if (errno == EINTR) continue;
            perror("poll(CAN)");
            close(sock);
            return -1;
        }
        if (prc == 0) continue;

        struct can_frame frame;
        ssize_t n = read(sock, &frame, sizeof(frame));
        if (n != (ssize_t)sizeof(frame)) continue;

        int pred = -1;
        if (ids_runtime_on_frame(&rt, &frame, now_us(), &pred) && pred == 1) {
            printf("[IDS] ATTACK frame=%u predictions=%u can_id=0x%03X\n",
                   rt.frames_seen, rt.predictions, frame.can_id & CAN_SFF_MASK);
        }
    }

    printf("\n=== IDS Monitor Stats ===\n");
    printf("Frames seen     : %u\n", rt.frames_seen);
    printf("Predictions     : %u\n", rt.predictions);
    printf("Attack detected : %u\n", rt.attacks_detected);
    close(sock);
    return 0;
}
