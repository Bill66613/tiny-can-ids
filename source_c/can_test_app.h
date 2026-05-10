#ifndef CAN_TEST_APP_H
#define CAN_TEST_APP_H

#include <stdint.h>
#include <stdbool.h>
#include <linux/can.h>

typedef enum {
    MODE_SYNTHETIC = 0,
    MODE_ATTACK,
    MODE_REPLAY,
    MODE_IDS
} app_mode_t;

typedef enum {
    ATTACK_NONE = 0,
    ATTACK_DOS,
    ATTACK_FUZZY,
    ATTACK_GEAR,
    ATTACK_RPM
} attack_type_t;

typedef struct {
    char interface_name[32];
    app_mode_t mode;
    attack_type_t attack_type;
    char dataset_path[512];
    unsigned int rate_fps;
    unsigned int duration_sec;
    bool loop_replay;
    bool realtime_replay;
    bool json_output;
    bool infer_sent;
    unsigned int ids_window;
    uint32_t seed;
} app_config_t;

typedef struct {
    uint64_t frames_sent;
    uint64_t frames_failed;
    double elapsed_sec;
} app_stats_t;

int open_can_socket(const char *ifname);
int send_can_frame(int sock, const struct can_frame *frame);
void sleep_for_rate(unsigned int rate_fps);
uint64_t now_us(void);
void sleep_until_us(uint64_t target_us);

#endif
