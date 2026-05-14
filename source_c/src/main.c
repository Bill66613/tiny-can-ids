#include <getopt.h>
#include <stdbool.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

typedef enum {
	ATTACK_DOS,
	ATTACK_FUZZY,
	ATTACK_GEAR,
	ATTACK_RPM,
	ATTACK_UNKNOWN
} attack_type_t;

typedef enum {
	MODEL_DT,
	MODEL_TNN,
	MODEL_LR,
	MODEL_UNKNOWN
} model_type_t;

typedef struct {
	attack_type_t attack_type;
	model_type_t model;
	const char *interface_name;
} app_config_t;

static void print_help(const char *prog_name) {
	printf("Usage: %s --attack-type <dos|fuzzy|gear|rpm> --model <dt|tnn|lr> --interface <can0|vcan0|...>\n",
		   prog_name);
	printf("\n");
	printf("Options:\n");
	printf("  -a, --attack-type   Attack type: dos, fuzzy, gear, rpm\n");
	printf("  -m, --model         Model: dt, tnn, lr\n");
	printf("  -i, --interface     CAN interface name, example: can0, vcan0\n");
	printf("  -h, --help          Show this help message\n");
	printf("\n");
	printf("Example:\n");
	printf("  %s --attack-type dos --model tnn --interface vcan0\n", prog_name);
}

static attack_type_t parse_attack_type(const char *value) {
	if (value == NULL) {
		return ATTACK_UNKNOWN;
	}

	if (strcmp(value, "dos") == 0) {
		return ATTACK_DOS;
	}
	if (strcmp(value, "fuzzy") == 0) {
		return ATTACK_FUZZY;
	}
	if (strcmp(value, "gear") == 0) {
		return ATTACK_GEAR;
	}
	if (strcmp(value, "rpm") == 0) {
		return ATTACK_RPM;
	}

	return ATTACK_UNKNOWN;
}

static model_type_t parse_model_type(const char *value) {
	if (value == NULL) {
		return MODEL_UNKNOWN;
	}

	if (strcmp(value, "dt") == 0) {
		return MODEL_DT;
	}
	if (strcmp(value, "tnn") == 0) {
		return MODEL_TNN;
	}
	if (strcmp(value, "lr") == 0) {
		return MODEL_LR;
	}

	return MODEL_UNKNOWN;
}

static const char *attack_type_to_string(attack_type_t attack_type) {
	switch (attack_type) {
	case ATTACK_DOS:
		return "dos";
	case ATTACK_FUZZY:
		return "fuzzy";
	case ATTACK_GEAR:
		return "gear";
	case ATTACK_RPM:
		return "rpm";
	default:
		return "unknown";
	}
}

static const char *model_type_to_string(model_type_t model) {
	switch (model) {
	case MODEL_DT:
		return "dt";
	case MODEL_TNN:
		return "tnn";
	case MODEL_LR:
		return "lr";
	default:
		return "unknown";
	}
}

static bool parse_arguments(int argc, char **argv, app_config_t *cfg) {
	static const struct option long_options[] = {
		{"attack-type", required_argument, NULL, 'a'},
		{"model", required_argument, NULL, 'm'},
		{"interface", required_argument, NULL, 'i'},
		{"help", no_argument, NULL, 'h'},
		{0, 0, 0, 0},
	};

	int opt = 0;
	while ((opt = getopt_long(argc, argv, "a:m:i:h", long_options, NULL)) != -1) {
		switch (opt) {
		case 'a':
			cfg->attack_type = parse_attack_type(optarg);
			if (cfg->attack_type == ATTACK_UNKNOWN) {
				fprintf(stderr, "Error: invalid attack type '%s'. Use dos|fuzzy|gear|rpm.\n", optarg);
				return false;
			}
			break;
		case 'm':
			cfg->model = parse_model_type(optarg);
			if (cfg->model == MODEL_UNKNOWN) {
				fprintf(stderr, "Error: invalid model '%s'. Use dt|tnn|lr.\n", optarg);
				return false;
			}
			break;
		case 'i':
			cfg->interface_name = optarg;
			if (cfg->interface_name[0] == '\0') {
				fprintf(stderr, "Error: interface must not be empty.\n");
				return false;
			}
			break;
		case 'h':
			print_help(argv[0]);
			exit(EXIT_SUCCESS);
		default:
			print_help(argv[0]);
			return false;
		}
	}

	if (cfg->attack_type == ATTACK_UNKNOWN || cfg->model == MODEL_UNKNOWN || cfg->interface_name == NULL) {
		fprintf(stderr, "Error: missing required arguments.\n\n");
		print_help(argv[0]);
		return false;
	}

	return true;
}

int main(int argc, char **argv) {
	app_config_t cfg = {
		.attack_type = ATTACK_UNKNOWN,
		.model = MODEL_UNKNOWN,
		.interface_name = NULL,
	};

	if (!parse_arguments(argc, argv, &cfg)) {
		return EXIT_FAILURE;
	}

	printf("Tiny CAN IDS app starting...\n");
	printf("  attack_type: %s\n", attack_type_to_string(cfg.attack_type));
	printf("  model      : %s\n", model_type_to_string(cfg.model));
	printf("  interface  : %s\n", cfg.interface_name);
	printf("\n");
	printf("Helper: runtime logic will be added in next step.\n");

	return EXIT_SUCCESS;
}
