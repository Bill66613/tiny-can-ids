#include "attack_generator.h"
#include "dataset_replay.h"
#include "can_test_app.h"
#include "ids_runtime.h"

#include <getopt.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <strings.h>
#include <time.h>
#include <unistd.h>

static void print_usage(const char *prog) {
    printf(
        "Usage:\n"
        "  %s --interface vcan0 --mode synthetic [--rate 500] [--duration 10] [--infer-sent]\n"
        "  %s --interface vcan0 --mode attack --attack-type dos [--rate 1000] [--duration 10] [--infer-sent]\n"
        "  %s --interface vcan0 --mode replay --dataset data.csv [--realtime | --rate 500] [--loop] [--infer-sent]\n"
        "  %s --interface vcan0 --mode ids [--duration 30]\n"
        "\n"
        "Options:\n"
        "  -i, --interface NAME       CAN interface, e.g. vcan0/can0\n"
        "  -m, --mode MODE           synthetic | attack | replay | ids\n"
        "  -a, --attack-type TYPE    dos | fuzzy | gear | rpm\n"
        "  -d, --dataset PATH        CSV dataset path for replay mode\n"
        "  -r, --rate FPS            Send rate in frames per second. 0 = unlimited\n"
        "  -t, --duration SEC        Duration in seconds. 0 = run until dataset ends / forever\n"
        "      --loop                Loop dataset replay\n"
        "      --realtime            Replay using timestamp column timing\n"
        "      --json                Print final stats as JSON\n"
        "      --infer-sent          Run Tiny IDS inference on frames sent by this app\n"
        "      --ids-window N        Sliding window size for IDS inference, default 64\n"
        "      --seed N              Random seed for fuzzy attack\n"
        "  -h, --help                Show this help\n",
        prog, prog, prog, prog
    );
}

static app_mode_t parse_mode(const char *s) {
    if (strcasecmp(s, "synthetic") == 0) return MODE_SYNTHETIC;
    if (strcasecmp(s, "attack") == 0) return MODE_ATTACK;
    if (strcasecmp(s, "replay") == 0) return MODE_REPLAY;
    if (strcasecmp(s, "ids") == 0) return MODE_IDS;
    return MODE_SYNTHETIC;
}

static attack_type_t parse_attack_type(const char *s) {
    if (strcasecmp(s, "dos") == 0) return ATTACK_DOS;
    if (strcasecmp(s, "fuzzy") == 0) return ATTACK_FUZZY;
    if (strcasecmp(s, "gear") == 0) return ATTACK_GEAR;
    if (strcasecmp(s, "rpm") == 0) return ATTACK_RPM;
    return ATTACK_NONE;
}

static const char *mode_name(app_mode_t mode) {
    switch (mode) {
        case MODE_SYNTHETIC: return "synthetic";
        case MODE_ATTACK: return "attack";
        case MODE_REPLAY: return "replay";
        case MODE_IDS: return "ids";
        default: return "unknown";
    }
}

static const char *attack_name(attack_type_t type) {
    switch (type) {
        case ATTACK_DOS: return "dos";
        case ATTACK_FUZZY: return "fuzzy";
        case ATTACK_GEAR: return "gear";
        case ATTACK_RPM: return "rpm";
        case ATTACK_NONE: return "none";
        default: return "unknown";
    }
}

static int validate_config(const app_config_t *cfg) {
    if (cfg->interface_name[0] == '\0') {
        fprintf(stderr, "Missing --interface\n");
        return -1;
    }
    if (cfg->mode == MODE_ATTACK && cfg->attack_type == ATTACK_NONE) {
        fprintf(stderr, "Missing or invalid --attack-type for attack mode\n");
        return -1;
    }
    if (cfg->mode == MODE_REPLAY && cfg->dataset_path[0] == '\0') {
        fprintf(stderr, "Missing --dataset for replay mode\n");
        return -1;
    }
    return 0;
}

static void print_stats(const app_config_t *cfg, const app_stats_t *stats) {
    double fps = stats->elapsed_sec > 0.0 ? (double)stats->frames_sent / stats->elapsed_sec : 0.0;

    if (cfg->json_output) {
        printf("{\"interface\":\"%s\",\"mode\":\"%s\",\"attack_type\":\"%s\",\"frames_sent\":%llu,\"frames_failed\":%llu,\"elapsed_sec\":%.3f,\"rate_fps\":%.2f}\n",
               cfg->interface_name,
               mode_name(cfg->mode),
               attack_name(cfg->attack_type),
               (unsigned long long)stats->frames_sent,
               (unsigned long long)stats->frames_failed,
               stats->elapsed_sec,
               fps);
        return;
    }

    printf("\n=== CAN Test App Stats ===\n");
    printf("Interface    : %s\n", cfg->interface_name);
    printf("Mode         : %s\n", mode_name(cfg->mode));
    printf("Attack type  : %s\n", attack_name(cfg->attack_type));
    printf("Frames sent  : %llu\n", (unsigned long long)stats->frames_sent);
    printf("Frames failed: %llu\n", (unsigned long long)stats->frames_failed);
    printf("Elapsed      : %.3f sec\n", stats->elapsed_sec);
    printf("Actual rate  : %.2f fps\n", fps);
}

int main(int argc, char **argv) {
    app_config_t cfg;
    memset(&cfg, 0, sizeof(cfg));
    snprintf(cfg.interface_name, sizeof(cfg.interface_name), "vcan0");
    cfg.mode = MODE_SYNTHETIC;
    cfg.attack_type = ATTACK_NONE;
    cfg.rate_fps = 500;
    cfg.duration_sec = 10;
    cfg.ids_window = 64;
    cfg.seed = (uint32_t)time(NULL);

    static const struct option long_opts[] = {
        {"interface", required_argument, 0, 'i'},
        {"mode", required_argument, 0, 'm'},
        {"attack-type", required_argument, 0, 'a'},
        {"dataset", required_argument, 0, 'd'},
        {"rate", required_argument, 0, 'r'},
        {"duration", required_argument, 0, 't'},
        {"loop", no_argument, 0, 1000},
        {"realtime", no_argument, 0, 1001},
        {"json", no_argument, 0, 1002},
        {"seed", required_argument, 0, 1003},
        {"infer-sent", no_argument, 0, 1004},
        {"ids-window", required_argument, 0, 1005},
        {"help", no_argument, 0, 'h'},
        {0, 0, 0, 0}
    };

    int opt;
    while ((opt = getopt_long(argc, argv, "i:m:a:d:r:t:h", long_opts, NULL)) != -1) {
        switch (opt) {
            case 'i': snprintf(cfg.interface_name, sizeof(cfg.interface_name), "%s", optarg); break;
            case 'm': cfg.mode = parse_mode(optarg); break;
            case 'a': cfg.attack_type = parse_attack_type(optarg); break;
            case 'd': snprintf(cfg.dataset_path, sizeof(cfg.dataset_path), "%s", optarg); break;
            case 'r': cfg.rate_fps = (unsigned int)strtoul(optarg, NULL, 10); break;
            case 't': cfg.duration_sec = (unsigned int)strtoul(optarg, NULL, 10); break;
            case 1000: cfg.loop_replay = true; break;
            case 1001: cfg.realtime_replay = true; break;
            case 1002: cfg.json_output = true; break;
            case 1003: cfg.seed = (uint32_t)strtoul(optarg, NULL, 10); break;
            case 1004: cfg.infer_sent = true; break;
            case 1005: cfg.ids_window = (unsigned int)strtoul(optarg, NULL, 10); break;
            case 'h': print_usage(argv[0]); return 0;
            default: print_usage(argv[0]); return 1;
        }
    }

    if (validate_config(&cfg) != 0) {
        print_usage(argv[0]);
        return 1;
    }

    srand(cfg.seed);

    if (cfg.mode == MODE_IDS) {
        return run_ids_monitor(cfg.interface_name, cfg.duration_sec, cfg.ids_window) == 0 ? 0 : 1;
    }

    int sock = open_can_socket(cfg.interface_name);
    if (sock < 0) {
        return 1;
    }

    printf("Starting CAN test app: interface=%s mode=%s attack=%s rate=%u duration=%u\n",
           cfg.interface_name, mode_name(cfg.mode), attack_name(cfg.attack_type), cfg.rate_fps, cfg.duration_sec);

    app_stats_t stats;
    memset(&stats, 0, sizeof(stats));

    int rc = 0;
    switch (cfg.mode) {
        case MODE_SYNTHETIC:
            rc = run_synthetic_mode(sock, &cfg, &stats);
            break;
        case MODE_ATTACK:
            rc = run_attack_mode(sock, &cfg, &stats);
            break;
        case MODE_REPLAY:
            rc = run_replay_mode(sock, &cfg, &stats);
            break;
        case MODE_IDS:
            rc = run_ids_monitor(cfg.interface_name, cfg.duration_sec, cfg.ids_window);
            break;
        default:
            rc = -1;
            break;
    }

    close(sock);
    print_stats(&cfg, &stats);
    return rc == 0 ? 0 : 1;
}
