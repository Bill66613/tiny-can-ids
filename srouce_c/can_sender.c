#include "can_test_app.h"

#include <errno.h>
#include <net/if.h>
#include <stdio.h>
#include <string.h>
#include <sys/ioctl.h>
#include <sys/socket.h>
#include <time.h>
#include <unistd.h>

int open_can_socket(const char *ifname) {
    int sock = socket(PF_CAN, SOCK_RAW, CAN_RAW);
    if (sock < 0) {
        perror("socket(PF_CAN)");
        return -1;
    }

    struct ifreq ifr;
    memset(&ifr, 0, sizeof(ifr));
    snprintf(ifr.ifr_name, sizeof(ifr.ifr_name), "%s", ifname);

    if (ioctl(sock, SIOCGIFINDEX, &ifr) < 0) {
        perror("ioctl(SIOCGIFINDEX)");
        close(sock);
        return -1;
    }

    struct sockaddr_can addr;
    memset(&addr, 0, sizeof(addr));
    addr.can_family = AF_CAN;
    addr.can_ifindex = ifr.ifr_ifindex;

    if (bind(sock, (struct sockaddr *)&addr, sizeof(addr)) < 0) {
        perror("bind(AF_CAN)");
        close(sock);
        return -1;
    }

    return sock;
}

int send_can_frame(int sock, const struct can_frame *frame) {
    ssize_t n = write(sock, frame, sizeof(struct can_frame));
    if (n != (ssize_t)sizeof(struct can_frame)) {
        if (n < 0) {
            perror("write(CAN frame)");
        } else {
            fprintf(stderr, "partial CAN frame write: %zd bytes\n", n);
        }
        return -1;
    }
    return 0;
}

uint64_t now_us(void) {
    struct timespec ts;
    clock_gettime(CLOCK_MONOTONIC, &ts);
    return (uint64_t)ts.tv_sec * 1000000ULL + (uint64_t)(ts.tv_nsec / 1000ULL);
}

void sleep_until_us(uint64_t target_us) {
    while (1) {
        uint64_t current = now_us();
        if (current >= target_us) {
            return;
        }
        uint64_t diff = target_us - current;
        struct timespec req;
        req.tv_sec = (time_t)(diff / 1000000ULL);
        req.tv_nsec = (long)((diff % 1000000ULL) * 1000ULL);
        nanosleep(&req, NULL);
    }
}

void sleep_for_rate(unsigned int rate_fps) {
    if (rate_fps == 0) {
        return;
    }
    uint64_t interval_us = 1000000ULL / rate_fps;
    if (interval_us == 0) {
        interval_us = 1;
    }
    struct timespec req;
    req.tv_sec = (time_t)(interval_us / 1000000ULL);
    req.tv_nsec = (long)((interval_us % 1000000ULL) * 1000ULL);
    nanosleep(&req, NULL);
}
