# ---------------------------------------------------------------------------
# Architecture selection
# Usage: make [ARCH=native|x86_64|aarch64|armv7] [STATIC=0|1]
#   make                       → native (host toolchain)
#   make ARCH=aarch64          → aarch64-linux-gnu-gcc
#   make ARCH=armv7            → arm-linux-gnueabihf-gcc  (Linux hard-float)
#   make ARCH=armv7 STATIC=1   → static ARMv7 binary
#   make multi                 → builds native + aarch64 + armv7 in sequence
#
# Override toolchain manually: make ARCH=aarch64 CC=my-custom-gcc
# ---------------------------------------------------------------------------

ARCH ?= native
STATIC ?= 1

ifeq ($(ARCH),native)
  CROSS_PREFIX :=
  ARCH_CFLAGS  :=
  CC           ?= gcc
else ifeq ($(ARCH),x86_64)
  CROSS_PREFIX := x86_64-linux-gnu-
  ARCH_CFLAGS  := -m64
  override CC  := $(CROSS_PREFIX)gcc
else ifeq ($(ARCH),aarch64)
  CROSS_PREFIX := aarch64-linux-gnu-
  ARCH_CFLAGS  :=
  override CC  := $(CROSS_PREFIX)gcc
else ifeq ($(ARCH),armv7)
  CROSS_PREFIX := arm-linux-gnueabihf-
  ARCH_CFLAGS  :=
  override CC  := $(CROSS_PREFIX)gcc
else
  $(error Unknown ARCH '$(ARCH)'. Valid: native x86_64 aarch64 armv7)
endif

CFLAGS  ?= -D_GNU_SOURCE -O2 -Wall -Wextra -std=c11 $(ARCH_CFLAGS)

LDFLAGS ?=
LDLIBS  ?= -lm

ifeq ($(STATIC),1)
  LDFLAGS += -static
endif

TARGET      := can_test_app
BUILD_DIR   := build/$(ARCH)
TARGET_PATH := $(BUILD_DIR)/$(TARGET)

# Source layout:
# - app entrypoint: src/main.c
# - model implementations: src/models/*.c
CORE_SRCS  := src/main.c
MODEL_SRCS := $(wildcard src/models/*.c)
SRCS       := $(CORE_SRCS) $(MODEL_SRCS)

OBJS := $(patsubst %.c,$(BUILD_DIR)/%.o,$(SRCS))

MULTI_ARCHS := native aarch64 armv7

.PHONY: all clean info multi $(MULTI_ARCHS)

all: $(TARGET_PATH)

# Build all supported architectures in sequence
multi:
	@for arch in $(MULTI_ARCHS); do \
		echo ""; \
		echo "=== Building ARCH=$$arch ==="; \
		$(MAKE) ARCH=$$arch STATIC=$(STATIC) || exit 1; \
	done
	@echo ""
	@echo "=== Multi-arch build complete ==="
	@ls -lh $(patsubst %,build/%/$(TARGET),$(MULTI_ARCHS)) 2>/dev/null || true

info:
	@echo "ARCH:       $(ARCH)"
	@echo "STATIC:     $(STATIC)"
	@echo "CC:         $(CC)"
	@echo "CFLAGS:     $(CFLAGS)"
	@echo "LDFLAGS:    $(LDFLAGS)"
	@echo "LDLIBS:     $(LDLIBS)"
	@echo "Sources:    $(SRCS)"
	@echo "Output:     $(TARGET_PATH)"

$(BUILD_DIR):
	mkdir -p $(BUILD_DIR)

$(BUILD_DIR)/%.o: %.c | $(BUILD_DIR)
	mkdir -p $(dir $@)
	$(CC) $(CFLAGS) -c $< -o $@

$(TARGET_PATH): $(OBJS)
	$(CC) $(CFLAGS) $(LDFLAGS) -o $@ $(OBJS) $(LDLIBS)

clean:
	rm -rf build
