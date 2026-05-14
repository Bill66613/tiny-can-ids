CC ?= gcc
CFLAGS ?= -D_GNU_SOURCE -O2 -Wall -Wextra -std=c11
LDFLAGS ?= -lm
TARGET := can_test_app
BUILD_DIR := build
TARGET_PATH := $(BUILD_DIR)/$(TARGET)

# Source layout:
# - app entrypoint: src/main.c
# - model implementations: src/models/*.c
CORE_SRCS := src/main.c
MODEL_SRCS := $(wildcard src/models/*.c)
SRCS := $(CORE_SRCS) $(MODEL_SRCS)
OBJS := $(patsubst %.c,$(BUILD_DIR)/%.o,$(SRCS))

.PHONY: all clean info

all: $(TARGET_PATH)

info:
	@echo "CC: $(CC)"
	@echo "CFLAGS: $(CFLAGS)"
	@echo "Sources: $(SRCS)"
	@echo "Output: $(TARGET_PATH)"

$(BUILD_DIR):
	mkdir -p $(BUILD_DIR)

$(BUILD_DIR)/%.o: %.c | $(BUILD_DIR)
	mkdir -p $(dir $@)
	$(CC) $(CFLAGS) -c $< -o $@

$(TARGET_PATH): $(OBJS)
	$(CC) $(CFLAGS) -o $@ $(OBJS) $(LDFLAGS)

clean:
	rm -rf $(BUILD_DIR)
