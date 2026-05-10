#include "dataset_replay.h"
#include "ids_runtime.h"

#include <ctype.h>
#include <errno.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#define LINE_BUF_SIZE 2048

static char *trim(char *s) {
    while (*s && isspace((unsigned char)*s)) {
        s++;
    }
    char *end = s + strlen(s);
    while (end > s && isspace((unsigned char)*(end - 1))) {
        --end;
    }
    *end = '\0';
    return s;
}

static bool looks_like_header(const char *line) {
    return strstr(line, "timestamp") || strstr(line, "can_id") || strstr(line, "CAN_ID") || strstr(line, "data");
}

static int parse_hex_byte(const char *s, uint8_t *out) {
    char *end = NULL;
    errno = 0;
    unsigned long v = strtoul(s, &end, 16);
    if (errno != 0 || end == s || v > 0xFFUL) {
        return -1;
    }
    *out = (uint8_t)v;
    return 0;
}

static int parse_data_bytes(char *data_str, struct can_frame *frame) {
    frame->can_dlc = 0;

    char *s = trim(data_str);
    size_t len = strlen(s);

    /* Format: "11 22 33 44 55 66 77 88" or "1122334455667788" */
    if (strchr(s, ' ') == NULL && strchr(s, ':') == NULL && len >= 2) {
        for (size_t i = 0; i + 1 < len && frame->can_dlc < 8; i += 2) {
            char tmp[3] = {s[i], s[i + 1], '\0'};
            if (parse_hex_byte(tmp, &frame->data[frame->can_dlc]) != 0) {
                return -1;
            }
            frame->can_dlc++;
        }
        return 0;
    }

    const char *delim = " :\t";
    char *save = NULL;
    char *tok = strtok_r(s, delim, &save);
    while (tok && frame->can_dlc < 8) {
        if (parse_hex_byte(tok, &frame->data[frame->can_dlc]) != 0) {
            return -1;
        }
        frame->can_dlc++;
        tok = strtok_r(NULL, delim, &save);
    }

    return frame->can_dlc > 0 ? 0 : -1;
}

static int parse_csv_line(char *line, double *timestamp, struct can_frame *frame) {
    memset(frame, 0, sizeof(*frame));

    char *cols[16] = {0};
    size_t n = 0;
    char *save = NULL;
    char *tok = strtok_r(line, ",", &save);
    while (tok && n < 16) {
        cols[n++] = trim(tok);
        tok = strtok_r(NULL, ",", &save);
    }

    if (n < 3) {
        return -1;
    }

    /* Expected simple format: timestamp,can_id,dlc,data,label */
    char *end = NULL;
    *timestamp = strtod(cols[0], &end);
    if (end == cols[0]) {
        return -1;
    }

    errno = 0;
    unsigned long can_id = strtoul(cols[1], &end, 16);
    if (errno != 0 || end == cols[1] || can_id > CAN_EFF_MASK) {
        return -1;
    }
    frame->can_id = (canid_t)can_id;

    int data_col = 3;
    long dlc = strtol(cols[2], &end, 10);
    if (end != cols[2] && dlc >= 0 && dlc <= 8 && n >= 4) {
        frame->can_dlc = (uint8_t)dlc;
        data_col = 3;
    } else {
        data_col = 2;
    }

    if ((size_t)data_col >= n) {
        return -1;
    }

    if (parse_data_bytes(cols[data_col], frame) != 0) {
        return -1;
    }

    if (dlc >= 0 && dlc <= 8 && frame->can_dlc > (uint8_t)dlc) {
        frame->can_dlc = (uint8_t)dlc;
    }

    return 0;
}

static int replay_file_once(int sock, const app_config_t *cfg, app_stats_t *stats, ids_runtime_t *ids) {
    FILE *fp = fopen(cfg->dataset_path, "r");
    if (!fp) {
        perror("fopen(dataset)");
        return -1;
    }

    char line[LINE_BUF_SIZE];
    bool first_frame = true;
    double first_ts = 0.0;
    uint64_t replay_start_us = now_us();

    while (fgets(line, sizeof(line), fp)) {
        char original[LINE_BUF_SIZE];
        snprintf(original, sizeof(original), "%s", line);
        char *p = trim(original);
        if (*p == '\0' || *p == '#') {
            continue;
        }
        if (looks_like_header(p)) {
            continue;
        }

        double ts = 0.0;
        struct can_frame frame;
        if (parse_csv_line(p, &ts, &frame) != 0) {
            continue;
        }

        if (cfg->realtime_replay) {
            if (first_frame) {
                first_ts = ts;
                replay_start_us = now_us();
                first_frame = false;
            }
            double offset_sec = ts - first_ts;
            if (offset_sec > 0) {
                uint64_t target = replay_start_us + (uint64_t)(offset_sec * 1000000.0);
                sleep_until_us(target);
            }
        } else if (cfg->rate_fps > 0) {
            sleep_for_rate(cfg->rate_fps);
        }

        if (send_can_frame(sock, &frame) == 0) {
            stats->frames_sent++;
            if (cfg->infer_sent && ids) {
                int pred = -1;
                if (ids_runtime_on_frame(ids, &frame, now_us(), &pred) && pred == 1) {
                    printf("[IDS] ATTACK on replay frame=%llu can_id=0x%03X\n",
                           (unsigned long long)stats->frames_sent, frame.can_id & CAN_SFF_MASK);
                }
            }
        } else {
            stats->frames_failed++;
        }
    }

    fclose(fp);
    return 0;
}

int run_replay_mode(int sock, const app_config_t *cfg, app_stats_t *stats) {
    uint64_t start = now_us();
    uint64_t end = cfg->duration_sec > 0 ? start + (uint64_t)cfg->duration_sec * 1000000ULL : 0;
    ids_runtime_t ids;
    if (cfg->infer_sent) {
        ids_runtime_init(&ids, cfg->ids_window);
    }

    do {
        if (replay_file_once(sock, cfg, stats, cfg->infer_sent ? &ids : NULL) != 0) {
            return -1;
        }
    } while (cfg->loop_replay && (cfg->duration_sec == 0 || now_us() < end));

    stats->elapsed_sec = (double)(now_us() - start) / 1000000.0;
    if (cfg->infer_sent) {
        printf("IDS predictions=%u attacks=%u window=%u\n", ids.predictions, ids.attacks_detected, ids.window_size);
    }
    return 0;
}
