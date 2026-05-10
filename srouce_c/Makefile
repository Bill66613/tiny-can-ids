CC ?= gcc
CFLAGS ?= -D_GNU_SOURCE -O2 -Wall -Wextra -std=c11
LDFLAGS ?= -lm
TARGET := can_test_app
SRCS := main.c can_sender.c attack_generator.c dataset_replay.c ids_runtime.c tiny_ids_tnn_inference.c
OBJS := $(SRCS:.c=.o)

all: $(TARGET)

$(TARGET): $(OBJS)
	$(CC) $(CFLAGS) -o $@ $(OBJS) $(LDFLAGS)

clean:
	rm -f $(TARGET) $(OBJS)
