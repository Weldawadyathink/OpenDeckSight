/* Native-mode fixed-refresh control for the disposable USB lab.
 * No VRR request, clock/range override, AUX/MMIO access or firmware operation.
 * Build: cc -std=c11 -O2 -Wall -Wextra -Werror $(pkg-config --cflags libdrm)
 *        fixed_present.c -o ods-fixed-present $(pkg-config --libs libdrm)
 */
#define _POSIX_C_SOURCE 200809L
#include <errno.h>
#include <fcntl.h>
#include <poll.h>
#include <signal.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/mman.h>
#include <time.h>
#include <unistd.h>
#include <xf86drm.h>
#include <xf86drmMode.h>
#include <drm_mode.h>

static volatile sig_atomic_t stopped;
static const char expected_edid[] =
    "00ffffffffffff00126f01500100000001230104a509107817b974ae503db723"
    "0b4f5100000001010101010101010101010101010101ee37388c408024702008"
    "82005aa00000001e000000fc004465636b53696768740a202020000000000000"
    "00000000000000000000000000000000000000000000000000000000000001e4"
    "02030b00e60605016a6a00000000000000000000000000000000000000000000"
    "0000000000000000000000000000000000000000000000000000000000000000"
    "0000000000000000000000000000000000000000000000000000000000000000"
    "000000000000000000000000000000000000000000000000000000000000002a";
_Static_assert(sizeof(expected_edid) == 513, "full 256-byte r04 EDID required");

struct buffer { uint32_t handle, fb, pitch; uint64_t size; void *pixels; };
struct event { bool pending; uint32_t sequence; uint64_t time_ns; };
static void stop(int sig) { (void)sig; stopped = 1; }
static uint64_t now_ns(void) {
    struct timespec t;
    if (clock_gettime(CLOCK_MONOTONIC, &t)) abort();
    return (uint64_t)t.tv_sec * 1000000000u + t.tv_nsec;
}
static void flipped(int fd, unsigned seq, unsigned sec, unsigned usec, void *data) {
    (void)fd;
    struct event *e = data;
    e->sequence = seq;
    e->time_ns = (uint64_t)sec * 1000000000u + (uint64_t)usec * 1000u;
    e->pending = false;
}
static int wait_flip(int fd, struct event *e) {
    drmEventContext ctx = { .version = 2, .page_flip_handler = flipped };
    uint64_t deadline = now_ns() + 2000000000u;
    while (e->pending) {
        if (now_ns() >= deadline) { errno = ETIMEDOUT; return -1; }
        struct pollfd p = { .fd = fd, .events = POLLIN };
        int n = poll(&p, 1, 100);
        if (n < 0 && errno == EINTR) continue;
        if (n < 0 || (p.revents & (POLLERR | POLLHUP | POLLNVAL))) return -1;
        if (n && drmHandleEvent(fd, &ctx)) return -1;
    }
    return 0;
}
static bool native_mode(const drmModeModeInfo *m) {
    return m->clock == 143180 && m->hdisplay == 1080 && m->hsync_start == 1112 &&
        m->hsync_end == 1120 && m->htotal == 1220 && m->hskew == 0 &&
        m->vdisplay == 1920 && m->vsync_start == 1928 && m->vsync_end == 1930 &&
        m->vtotal == 1956 && m->vscan == 0 && m->flags == 5;
}
static bool expected_sink(int fd, drmModeConnector *c) {
    bool edid_ok = false, fixed = false;
    if (strlen(expected_edid) != 512) return false;
    for (int i = 0; i < c->count_props; i++) {
        drmModePropertyPtr p = drmModeGetProperty(fd, c->props[i]);
        if (!p) return false;
        if (!strcmp(p->name, "vrr_capable")) fixed = c->prop_values[i] == 0;
        if (!strcmp(p->name, "EDID") && (p->flags & DRM_MODE_PROP_BLOB)) {
            drmModePropertyBlobPtr b = drmModeGetPropertyBlob(fd, c->prop_values[i]);
            if (b && b->length == 256) {
                edid_ok = true;
                for (unsigned j = 0; j < 256; j++) {
                    unsigned x;
                    if (sscanf(expected_edid + j * 2, "%2x", &x) != 1 ||
                        ((uint8_t *)b->data)[j] != x) edid_ok = false;
                }
            }
            if (b) drmModeFreePropertyBlob(b);
        }
        drmModeFreeProperty(p);
    }
    return edid_ok && fixed;
}
static int create_buffer(int fd, struct buffer *b) {
    struct drm_mode_create_dumb c = { .width = 1080, .height = 1920, .bpp = 32 };
    if (drmIoctl(fd, DRM_IOCTL_MODE_CREATE_DUMB, &c)) return -1;
    b->handle = c.handle; b->pitch = c.pitch; b->size = c.size;
    if (drmModeAddFB(fd, 1080, 1920, 24, 32, b->pitch, b->handle, &b->fb)) return -1;
    struct drm_mode_map_dumb m = { .handle = b->handle };
    if (drmIoctl(fd, DRM_IOCTL_MODE_MAP_DUMB, &m)) return -1;
    b->pixels = mmap(NULL, b->size, PROT_READ | PROT_WRITE, MAP_SHARED, fd, m.offset);
    if (b->pixels == MAP_FAILED) { b->pixels = NULL; return -1; }
    return 0;
}
static void destroy_buffer(int fd, struct buffer *b) {
    if (b->pixels) munmap(b->pixels, b->size);
    if (b->fb) drmModeRmFB(fd, b->fb);
    if (b->handle) {
        struct drm_mode_destroy_dumb d = { .handle = b->handle };
        drmIoctl(fd, DRM_IOCTL_MODE_DESTROY_DUMB, &d);
    }
}
static void draw(struct buffer *b, unsigned frame) {
    for (unsigned y = 0; y < 1920; y++) {
        uint32_t *row = (uint32_t *)((uint8_t *)b->pixels + y * b->pitch);
        for (unsigned x = 0; x < 1080; x++) {
            uint32_t color = 0x202020;
            if (y >= 900 && y < 1020 && x / 12 == frame % 90) color = 0x808080;
            if (y >= 1800 && y < 1864 && x < 512)
                color = (frame & (1u << (x / 64))) ? 0x606060 : 0x202020;
            row[x] = color;
        }
    }
}
int main(int argc, char **argv) {
    bool run = argc == 3 && !strcmp(argv[1], "--run");
    if (argc != 3 || (!run && strcmp(argv[1], "--check"))) {
        fprintf(stderr, "Usage: %s --check|--run /dev/dri/cardN\n", argv[0]); return 2;
    }
    int result = 1, fd = -1;
    bool changed = false, restored = false;
    drmModeRes *res = NULL;
    drmModeConnector *sink = NULL;
    drmModeCrtc *saved = NULL;
    struct buffer buffers[2] = {0};
    setvbuf(stdout, NULL, _IOLBF, 0);
    fd = open(argv[2], (run ? O_RDWR : O_RDONLY) | O_CLOEXEC);
    if (fd < 0) { perror("open DRM"); goto done; }
    res = drmModeGetResources(fd);
    if (!res || res->count_connectors > 32 || res->count_crtcs > 32) goto done;
    for (int i = 0; i < res->count_connectors; i++) {
        drmModeConnector *c = drmModeGetConnectorCurrent(fd, res->connectors[i]);
        if (!c) goto done;
        if (c->connection == DRM_MODE_CONNECTED) {
            if (sink || c->connector_type != DRM_MODE_CONNECTOR_eDP) {
                fprintf(stderr, "Requires exactly one connected display, internal eDP.\n");
                drmModeFreeConnector(c); goto done;
            }
            sink = c;
        } else drmModeFreeConnector(c);
    }
    if (!sink || !expected_sink(fd, sink)) {
        fprintf(stderr, "Exact r04 EDID and vrr_capable=0 are required.\n"); goto done;
    }
    drmModeEncoder *encoder = drmModeGetEncoder(fd, sink->encoder_id);
    if (!encoder) goto done;
    saved = drmModeGetCrtc(fd, encoder->crtc_id);
    drmModeFreeEncoder(encoder);
    if (!saved || !saved->mode_valid || !saved->buffer_id || saved->x || saved->y ||
        !native_mode(&saved->mode)) {
        fprintf(stderr, "Requires the existing exact r04 native 60 Hz mode at origin.\n"); goto done;
    }
    uint64_t mono = 0;
    if (drmGetCap(fd, DRM_CAP_TIMESTAMP_MONOTONIC, &mono) || mono != 1) {
        fprintf(stderr, "Monotonic DRM event timestamps are required.\n"); goto done;
    }
    printf("{\"event\":\"preflight\",\"native_mode_verified\":true,\"vrr_capable\":0,\"active_test\":%s}\n", run ? "true" : "false");
    if (!run) { result = 0; goto done; }
    if (!drmIsMaster(fd)) { fprintf(stderr, "DRM master is already held; refusing takeover.\n"); goto done; }
    struct sigaction action = { .sa_handler = stop };
    sigemptyset(&action.sa_mask);
    sigaction(SIGINT, &action, NULL); sigaction(SIGTERM, &action, NULL);
    for (unsigned i = 0; i < 2; i++) {
        if (create_buffer(fd, &buffers[i])) { perror("create framebuffer"); goto done; }
        draw(&buffers[i], i);
    }
    if (drmModeSetCrtc(fd, saved->crtc_id, buffers[0].fb, 0, 0,
                       &sink->connector_id, 1, &saved->mode)) {
        perror("set unchanged native mode"); goto done;
    }
    changed = true;
    unsigned current = 0, count = 0;
    for (unsigned frame = 1; frame <= 240 && !stopped; frame++) {
        unsigned next = current ^ 1;
        unsigned delay_us = frame > 120 && frame % 2 == 0 ? 20000 : 1000;
        struct timespec delay = { .tv_nsec = delay_us * 1000 };
        while (nanosleep(&delay, &delay) && errno == EINTR && !stopped) {}
        if (stopped) break;
        draw(&buffers[next], frame);
        struct event e = { .pending = true };
        uint64_t submitted = now_ns();
        if (drmModePageFlip(fd, saved->crtc_id, buffers[next].fb, DRM_MODE_PAGE_FLIP_EVENT, &e)) {
            perror("page flip"); goto done;
        }
        if (wait_flip(fd, &e)) { perror("wait for page flip"); goto done; }
        printf("{\"event\":\"flip\",\"frame\":%u,\"delay_us\":%u,\"sequence\":%u,\"submitted_ns\":%llu,\"event_ns\":%llu}\n",
            frame, delay_us, e.sequence, (unsigned long long)submitted, (unsigned long long)e.time_ns);
        current = next; count++;
    }
    printf("{\"event\":\"completed\",\"frames\":%u,\"interrupted\":%s}\n", count, stopped ? "true" : "false");
    result = stopped ? 130 : 0;
done:
    if (changed) {
        if (drmModeSetCrtc(fd, saved->crtc_id, saved->buffer_id, saved->x, saved->y,
                           &sink->connector_id, 1, &saved->mode)) {
            perror("restore original framebuffer"); result = 3;
        } else {
            drmModeCrtc *check = drmModeGetCrtc(fd, saved->crtc_id);
            restored = check && check->buffer_id == saved->buffer_id &&
                check->mode_valid && native_mode(&check->mode) &&
                check->x == saved->x && check->y == saved->y;
            if (check) drmModeFreeCrtc(check);
            if (!restored) result = 3;
        }
        printf("{\"event\":\"restore\",\"success\":%s}\n", restored ? "true" : "false");
    }
    if (fd >= 0) {
        for (unsigned i = 0; i < 2; i++) destroy_buffer(fd, &buffers[i]);
        if (saved) drmModeFreeCrtc(saved);
        if (sink) drmModeFreeConnector(sink);
        if (res) drmModeFreeResources(res);
        close(fd);
    }
    return result;
}
