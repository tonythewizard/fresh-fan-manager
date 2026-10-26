// SPDX-License-Identifier: GPL-3.0-or-later
#include <stdio.h>
#include <stdlib.h>
#include <unistd.h>
#include <sys/io.h>
#include <stdint.h>
#include <string.h>
#include <time.h>

#define APPLESMC_DATA_PORT   0x300
#define APPLESMC_CMD_PORT    0x304

#define SMC_STATUS_AWAITING_DATA  (1 << 0) // 0x01
#define SMC_STATUS_IB_CLOSED      (1 << 1) // 0x02
#define SMC_STATUS_BUSY           (1 << 2) // 0x04

#define SMC_CMD_READ   0x10
#define SMC_CMD_WRITE  0x11

static void smc_sleep_us(unsigned int us) {
    struct timespec ts = {0, (long)us * 1000};
    nanosleep(&ts, NULL);
}

static int wait_status(uint8_t val, uint8_t mask) {
    unsigned int us = 10;
    for (int i = 0; i < 24; i++) {
        uint8_t status = inb(APPLESMC_CMD_PORT);
        if ((status & mask) == val)
            return 0;
        smc_sleep_us(us);
        if (i > 9)
            us <<= 1;
    }
    return -1;
}

static int send_command(uint8_t cmd) {
    if (wait_status(0, SMC_STATUS_IB_CLOSED) != 0)
        return -1;
    outb(cmd, APPLESMC_CMD_PORT);
    return 0;
}

static int send_byte(uint8_t val, uint16_t port) {
    if (wait_status(0, SMC_STATUS_IB_CLOSED) != 0)
        return -1;
    if (wait_status(SMC_STATUS_BUSY, SMC_STATUS_BUSY) != 0)
        return -2;
    outb(val, port);
    return 0;
}

static int smc_sane(void) {
    for (int i = 0; i < 16; i++) {
        uint8_t status = inb(APPLESMC_CMD_PORT);
        if (!(status & SMC_STATUS_AWAITING_DATA))
            break;
        inb(APPLESMC_DATA_PORT);
    }
    if (wait_status(0, SMC_STATUS_BUSY) == 0)
        return 0;
    if (send_command(SMC_CMD_READ) != 0)
        return -1;
    return wait_status(0, SMC_STATUS_BUSY);
}

static int write_smc(const char *key, const uint8_t *buffer, uint8_t len) {
    if (smc_sane() != 0) return -10;
    if (send_command(SMC_CMD_WRITE) != 0) return -11;
    for (int i = 0; i < 4; i++) {
        if (send_byte((uint8_t)key[i], APPLESMC_DATA_PORT) != 0)
            return -12;
    }
    if (send_byte(len, APPLESMC_DATA_PORT) != 0)
        return -13;
    for (int i = 0; i < len; i++) {
        if (send_byte(buffer[i], APPLESMC_DATA_PORT) != 0)
            return -14;
    }
    if (wait_status(0, SMC_STATUS_BUSY) != 0)
        return -15;
    return 0;
}

static int read_smc(const char *key, uint8_t *buffer, uint8_t len) {
    if (smc_sane() != 0) return -20;
    if (send_command(SMC_CMD_READ) != 0) return -21;
    for (int i = 0; i < 4; i++) {
        if (send_byte((uint8_t)key[i], APPLESMC_DATA_PORT) != 0)
            return -22;
    }
    if (send_byte(len, APPLESMC_DATA_PORT) != 0)
        return -23;
    for (int i = 0; i < len; i++) {
        if (wait_status(SMC_STATUS_AWAITING_DATA | SMC_STATUS_BUSY,
                        SMC_STATUS_AWAITING_DATA | SMC_STATUS_BUSY) != 0)
            return -24;
        buffer[i] = inb(APPLESMC_DATA_PORT);
    }
    for (int i = 0; i < 16; i++) {
        uint8_t status = inb(APPLESMC_CMD_PORT);
        if (!(status & SMC_STATUS_AWAITING_DATA))
            break;
        inb(APPLESMC_DATA_PORT);
    }
    if (wait_status(0, SMC_STATUS_BUSY) != 0)
        return -25;
    return 0;
}

int smc_port_set_fan_manual(int fan_idx, int rpm) {
    if (ioperm(0x300, 5, 1) != 0) {
        return -1;
    }
    if (fan_idx < 1 || fan_idx > 10) return -30;
    int idx = fan_idx - 1;
    uint8_t fs_buf[2] = {0, 0};
    if (read_smc("FS! ", fs_buf, 2) == 0) {
        uint16_t mask = (fs_buf[0] << 8) | fs_buf[1];
        mask |= (1 << idx);
        fs_buf[0] = (mask >> 8) & 0xff;
        fs_buf[1] = mask & 0xff;
    } else {
        return -31;
    }
    int r1 = 0;

    char mx_key[5] = {'F', (char)('0' + idx), 'M', 'x', '\0'};
    uint8_t mx_val[2];
    if (read_smc(mx_key, mx_val, 2) != 0) return -32;
    int maximum = ((mx_val[0] << 8) | mx_val[1]) >> 2;
    if (maximum <= 0 || rpm < 0 || rpm > maximum) return -33;
    int target = rpm;
    uint16_t raw = (uint16_t)(target << 2);
    uint8_t tg_val[2] = {(uint8_t)((raw >> 8) & 0xff), (uint8_t)(raw & 0xff)};

    char tg_key[5] = {'F', (char)('0' + idx), 'T', 'g', '\0'};
    int r2 = write_smc(tg_key, tg_val, 2);

    // Also write to F%dMn to ensure min limit matches target
    char mn_key[5] = {'F', (char)('0' + idx), 'M', 'n', '\0'};
    int r3 = write_smc(mn_key, tg_val, 2);
    if (r2 != 0 || r3 != 0) return r2 != 0 ? r2 : r3;
    r1 = write_smc("FS! ", fs_buf, 2);
    return r1;
}

int smc_port_set_fan_auto(int fan_idx, int original_minimum) {
    if (ioperm(0x300, 5, 1) != 0) {
        return -1;
    }
    if (fan_idx < 1 || fan_idx > 10) return -30;
    int idx = fan_idx - 1;
    uint8_t fs_buf[2] = {0, 0};
    if (read_smc("FS! ", fs_buf, 2) == 0) {
        uint16_t mask = (fs_buf[0] << 8) | fs_buf[1];
        mask &= ~(1 << idx);
        fs_buf[0] = (mask >> 8) & 0xff;
        fs_buf[1] = mask & 0xff;
    } else {
        return -31;
    }
    int r1 = write_smc("FS! ", fs_buf, 2);

    // Restore the hardware's original limit saved by the privileged helper.
    if (original_minimum < 0 || original_minimum > 16383) return -33;
    uint16_t def_min = original_minimum << 2;
    uint8_t mn_val[2] = {(uint8_t)((def_min >> 8) & 0xff), (uint8_t)(def_min & 0xff)};
    char mn_key[5] = {'F', (char)('0' + idx), 'M', 'n', '\0'};
    int r2 = write_smc(mn_key, mn_val, 2);
    return r1 != 0 ? r1 : r2;
}

int smc_port_get_fan_rpm(int fan_idx) {
    if (ioperm(0x300, 5, 1) != 0) {
        return -1;
    }
    if (fan_idx < 1 || fan_idx > 10) return -30;
    int idx = fan_idx - 1;
    char ac_key[5] = {'F', (char)('0' + idx), 'A', 'c', '\0'};
    uint8_t buf[2] = {0, 0};
    if (read_smc(ac_key, buf, 2) != 0) {
        return -2;
    }
    return ((buf[0] << 8) | buf[1]) >> 2;
}

int smc_port_is_fan_manual(int fan_idx) {
    if (ioperm(0x300, 5, 1) != 0) {
        return -1;
    }
    if (fan_idx < 1 || fan_idx > 10) return -30;
    int idx = fan_idx - 1;
    uint8_t buf[2] = {0, 0};
    if (read_smc("FS! ", buf, 2) != 0) {
        return -2;
    }
    uint16_t mask = (buf[0] << 8) | buf[1];
    return (mask >> idx) & 1;
}

int smc_port_get_fan_min(int fan_idx) {
    if (fan_idx < 1 || fan_idx > 10) return -30;
    if (ioperm(0x300, 5, 1) != 0) return -1;
    char key[5] = {'F', (char)('0' + fan_idx - 1), 'M', 'n', '\0'};
    uint8_t buf[2];
    if (read_smc(key, buf, 2) != 0) return -2;
    return ((buf[0] << 8) | buf[1]) >> 2;
}
