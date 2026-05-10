#ifndef ATTACK_GENERATOR_H
#define ATTACK_GENERATOR_H

#include "can_test_app.h"

void fill_synthetic_normal_frame(struct can_frame *frame, uint64_t seq);
void fill_attack_frame(struct can_frame *frame, attack_type_t attack_type, uint64_t seq);
int run_synthetic_mode(int sock, const app_config_t *cfg, app_stats_t *stats);
int run_attack_mode(int sock, const app_config_t *cfg, app_stats_t *stats);

#endif
