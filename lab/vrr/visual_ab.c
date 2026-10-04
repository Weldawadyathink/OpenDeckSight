/* SPDX-License-Identifier: MIT
 * Bounded visual A/B stimulus. It requires the guarded driver for VRR.
 * Reuse the native-mode framebuffer, timing, event and cleanup helpers.
 */
#define main ods_fixed_control_entry
#include "../usb/fixed_present.c"
#undef main
#include "ods_vrr_guard.h"

static void rect(struct buffer *b, unsigned x, unsigned y, unsigned w, unsigned h, uint32_t color)
{
    /* Landscape coordinates, rotated into the panel's native portrait buffer. */
    for (unsigned i = x; i < x + w && i < 1920; i++) {
        uint32_t *row = (uint32_t *)((uint8_t *)b->pixels + i * b->pitch);
        for (unsigned j = y; j < y + h && j < 1080; j++) row[1079-j] = color;
    }
}
static const unsigned char *glyph(char c)
{
    static const struct { char c; unsigned char rows[7]; } font[] = {
        {'A',{14,17,17,31,17,17,17}}, {'B',{30,17,17,30,17,17,30}},
        {'C',{14,17,16,16,16,17,14}}, {'D',{30,17,17,17,17,17,30}},
        {'E',{31,16,16,30,16,16,31}}, {'F',{31,16,16,30,16,16,16}},
        {'G',{14,17,16,23,17,17,15}},
        {'H',{17,17,17,31,17,17,17}}, {'I',{31,4,4,4,4,4,31}},
        {'P',{30,17,17,30,16,16,16}}, {'Q',{14,17,17,17,21,18,13}},
        {'R',{30,17,17,30,20,18,17}}, {'S',{15,16,16,14,1,1,30}},
        {'T',{31,4,4,4,4,4,4}}, {'U',{17,17,17,17,17,17,14}},
        {'V',{17,17,17,17,17,10,4}}, {'X',{17,17,10,4,10,17,17}},
        {'Z',{31,1,2,4,8,16,31}}, {'0',{14,17,19,21,25,17,14}},
        {'1',{4,12,4,4,4,4,14}}, {'2',{14,17,1,2,4,8,31}},
        {'3',{30,1,1,14,1,1,30}}, {'4',{2,6,10,18,31,2,2}},
        {'5',{31,16,16,30,1,1,30}}, {'6',{14,16,16,30,17,17,14}},
        {'7',{31,1,2,4,8,8,8}}, {'8',{14,17,17,14,17,17,14}},
        {'9',{14,17,17,15,1,1,14}}, {'.',{0,0,0,0,0,12,12}},
        {' ',{0,0,0,0,0,0,0}}
    };
    for (unsigned i = 0; i < sizeof(font)/sizeof(font[0]); i++)
        if (font[i].c == c) return font[i].rows;
    return font[sizeof(font)/sizeof(font[0])-1].rows;
}
static void label(struct buffer *b, unsigned x, unsigned y, const char *s)
{
    for (; *s; s++, x += 48) {
        const unsigned char *g = glyph(*s);
        for (unsigned row = 0; row < 7; row++)
            for (unsigned col = 0; col < 5; col++)
                if (g[row] & (1u << (4-col))) rect(b, x+col*8, y+row*8, 8, 8, 0xa0a0a0);
    }
}
static unsigned stimulus_total(unsigned frame)
{
    unsigned step = (frame - 1) % 720;
    unsigned triangle = step <= 360 ? step : 720-step;
    return 1960 + 26*triangle/360; /* Interior of the guarded 1957..1989 window. */
}
static uint64_t period_ns(unsigned frame)
{
    return (uint64_t)stimulus_total(frame) * 1220 * 1000000000u / 143180000u;
}
static void visual(struct buffer *b, unsigned frame, uint64_t elapsed, bool variable)
{
    memset(b->pixels, 0x20, b->size);
    label(b, 112, 112, variable ? "B VRR REQUESTED" : "A FIXED 60 HZ");
    char text[48];
    snprintf(text, sizeof(text), "TARGET FPS %.3f", 143180000.0/(1220.0*stimulus_total(frame)));
    label(b, 112, 210, text);
    rect(b, 120, 740, 1680, 4, 0x505050);
    for (unsigned x = 160; x < 1800; x += 160) rect(b, x, 730, 4, 24, 0x606060);
    unsigned travel = (elapsed * 420 / 1000000000u) % 3200;
    unsigned position = travel <= 1600 ? travel : 3200-travel;
    rect(b, 144+position, 340, 28, 360, 0xa0a0a0);
    for (unsigned bit = 0; bit < 8; bit++)
        rect(b, 120+bit*64, 900, 56, 56, frame & (1u<<bit) ? 0x808080 : 0x303030);
}
static int property(int fd, uint32_t obj, uint32_t type, const char *name, uint32_t *id, uint64_t *value)
{
    drmModeObjectProperties *ps = drmModeObjectGetProperties(fd, obj, type);
    if (!ps) return -1;
    int found = -1;
    for (uint32_t i = 0; i < ps->count_props; i++) {
        drmModePropertyPtr p = drmModeGetProperty(fd, ps->props[i]);
        if (p && !strcmp(p->name, name)) { *id = p->prop_id; *value = ps->prop_values[i]; found = 0; }
        if (p) drmModeFreeProperty(p);
    }
    drmModeFreeObjectProperties(ps);
    return found;
}
static int set_vrr(int fd, uint32_t crtc, uint32_t prop, bool enabled)
{
    drmModeAtomicReq *r = drmModeAtomicAlloc();
    if (!r) return -1;
    int result = drmModeAtomicAddProperty(r, crtc, prop, enabled) < 0 ? -1 : 0;
    if (!result) result = drmModeAtomicCommit(fd, r, DRM_MODE_ATOMIC_TEST_ONLY, NULL);
    if (!result) result = drmModeAtomicCommit(fd, r, 0, NULL);
    drmModeAtomicFree(r);
    return result;
}
static bool opted_in(void)
{
    FILE *f = fopen("/sys/module/amdgpu/parameters/ods_vrr_59_60", "r");
    if (!f) return false;
    int c = fgetc(f);
    fclose(f);
    return c == 'Y' || c == '1';
}
static int sleep_to(uint64_t deadline)
{
    /* Render ahead with three buffers; sleep, then spin only the final 300 us. */
    uint64_t wake = deadline > 300000 ? deadline-300000 : deadline;
    struct timespec t = { .tv_sec = wake/1000000000u, .tv_nsec = wake%1000000000u };
    int e;
    do { e = clock_nanosleep(CLOCK_MONOTONIC, TIMER_ABSTIME, &t, NULL); }
    while (e == EINTR && !stopped);
    if (e && e != EINTR) { errno = e; return -1; }
    while (!stopped && now_ns() < deadline) {}
    return 0;
}
static int preview(void)
{
    struct buffer b = {.pitch = 1080*4, .size = 1080*1920*4};
    b.pixels = malloc(b.size);
    if (!b.pixels) return 1;
    visual(&b, 181, 4000000000u, true);
    printf("P6\n1920 1080\n255\n");
    for (unsigned y=0; y<1080; y++) for (unsigned x=0; x<1920; x++) {
        uint32_t p = ((uint32_t *)b.pixels)[x*1080+1079-y];
        unsigned char rgb[3] = {p>>16, p>>8, p};
        fwrite(rgb, 1, 3, stdout);
    }
    free(b.pixels);
    return ferror(stdout) ? 1 : 0;
}
int main(int argc, char **argv)
{
    if (argc == 2 && !strcmp(argv[1], "--preview")) return preview();
    bool experiment = argc == 3 && !strcmp(argv[1], "--experiment");
    bool control = argc == 3 && !strcmp(argv[1], "--control");
    if (argc != 3 || (!experiment && !control && strcmp(argv[1], "--check"))) {
        fprintf(stderr, "Usage: %s --preview | --check|--control|--experiment /dev/dri/cardN\n", argv[0]); return 2;
    }
    bool run = experiment || control, changed = false, vrr_requested = false;
    int result = 1, fd = -1;
    drmModeRes *res = NULL;
    drmModeConnector *sink = NULL;
    drmModeCrtc *saved = NULL;
    struct buffer b[3] = {0};
    uint32_t vrr_prop = 0, id = 0;
    uint64_t value = 0, capability = 0;
    setvbuf(stdout, NULL, _IOLBF, 0);
    fd = open(argv[2], (run ? O_RDWR : O_RDONLY) | O_CLOEXEC);
    if (fd < 0 || drmSetClientCap(fd, DRM_CLIENT_CAP_ATOMIC, 1)) goto done;
    res = drmModeGetResources(fd);
    if (!res || res->count_connectors > 32) goto done;
    for (int i=0; i<res->count_connectors; i++) {
        drmModeConnector *c = drmModeGetConnectorCurrent(fd, res->connectors[i]);
        if (!c) goto done;
        if (c->connection == DRM_MODE_CONNECTED) {
            if (sink || c->connector_type != DRM_MODE_CONNECTOR_eDP) { drmModeFreeConnector(c); goto done; }
            sink = c;
        } else drmModeFreeConnector(c);
    }
    if (!sink || property(fd,sink->connector_id,DRM_MODE_OBJECT_CONNECTOR,"EDID",&id,&value)) goto done;
    drmModePropertyBlobPtr edid = drmModeGetPropertyBlob(fd,value);
    bool identity = edid && ods_vrr_identity(true,true,edid->data,edid->length);
    if (edid) drmModeFreePropertyBlob(edid);
    if (!identity || property(fd,sink->connector_id,DRM_MODE_OBJECT_CONNECTOR,"vrr_capable",&id,&capability)) goto done;
    drmModeEncoder *encoder = drmModeGetEncoder(fd,sink->encoder_id);
    if (!encoder) goto done;
    saved = drmModeGetCrtc(fd,encoder->crtc_id);
    drmModeFreeEncoder(encoder);
    if (!saved || !saved->buffer_id || !saved->mode_valid || saved->x || saved->y || !native_mode(&saved->mode)) goto done;
    if (property(fd,saved->crtc_id,DRM_MODE_OBJECT_CRTC,"VRR_ENABLED",&vrr_prop,&value) || value) goto done;
    if (drmGetCap(fd,DRM_CAP_TIMESTAMP_MONOTONIC,&value) || value != 1) goto done;
    if (experiment && (capability != 1 || !opted_in())) {
        fprintf(stderr,"Experiment requires the guarded driver with its explicit boot opt-in.\n"); goto done;
    }
    printf("{\"event\":\"preflight\",\"native_mode_verified\":true,\"vrr_capable\":%llu,\"opt_in\":%s,\"experiment\":%s}\n",
           (unsigned long long)capability,opted_in()?"true":"false",experiment?"true":"false");
    if (!run) { result=0; goto done; }
    if (!drmIsMaster(fd)) { fprintf(stderr,"No display takeover attempted.\n"); goto done; }
    struct sigaction action = {.sa_handler=stop};
    sigemptyset(&action.sa_mask);
    sigaction(SIGINT,&action,NULL); sigaction(SIGTERM,&action,NULL);
    for (unsigned i=0; i<3; i++) {
        if (create_buffer(fd,&b[i])) goto done;
        visual(&b[i],1,0,false);
    }
    if (drmModeSetCrtc(fd,saved->crtc_id,b[0].fb,0,0,&sink->connector_id,1,&saved->mode)) goto done;
    changed=true;
    unsigned current=0;
    for (unsigned phase=0; phase<(experiment?3u:1u) && !stopped; phase++) {
        bool variable = phase==1;
        unsigned frames=phase==2 ? 360 : 720;
        /* Mark intent before applying: cleanup must also handle a partial error. */
        vrr_requested = variable;
        if (set_vrr(fd,saved->crtc_id,vrr_prop,variable)) goto done;
        printf("{\"event\":\"phase\",\"phase\":%u,\"vrr_requested\":%s,\"frames\":%u}\n",phase,variable?"true":"false",frames);
        uint64_t start=now_ns(), deadline=start+period_ns(1);
        unsigned next=(current+1)%3;
        visual(&b[next],1,deadline-start,variable);
        for (unsigned frame=1; frame<=frames && !stopped; frame++) {
            if (now_ns()-start > 16000000000ULL) { fprintf(stderr,"Phase exceeded wall-clock bound.\n"); goto done; }
            if (sleep_to(deadline)) goto done;
            if (stopped) break;
            struct event e={.pending=true};
            uint64_t submitted=now_ns();
            if (drmModePageFlip(fd,saved->crtc_id,b[next].fb,DRM_MODE_PAGE_FLIP_EVENT,&e)) goto done;
            unsigned spare=(next+1)%3;
            uint64_t next_deadline=deadline+period_ns(frame+1);
            if (frame<frames) visual(&b[spare],frame+1,next_deadline-start,variable);
            if (wait_flip(fd,&e)) goto done;
            printf("{\"event\":\"flip\",\"phase\":%u,\"frame\":%u,\"target_total\":%u,\"deadline_ns\":%llu,\"submitted_ns\":%llu,\"event_ns\":%llu,\"sequence\":%u}\n",
                phase,frame,stimulus_total(frame),(unsigned long long)deadline,
                (unsigned long long)submitted,(unsigned long long)e.time_ns,e.sequence);
            current=next; next=spare; deadline=next_deadline;
        }
    }
    result=stopped?130:0;
done:
    if (fd>=0 && saved && vrr_prop && (changed || vrr_requested)) {
        if (set_vrr(fd,saved->crtc_id,vrr_prop,false)) { perror("restore VRR off"); result=3; }
        else vrr_requested=false;
    }
    if (changed) {
        bool restored = !drmModeSetCrtc(fd,saved->crtc_id,saved->buffer_id,saved->x,saved->y,&sink->connector_id,1,&saved->mode);
        drmModeCrtc *check=drmModeGetCrtc(fd,saved->crtc_id);
        restored = restored && check && check->buffer_id==saved->buffer_id && check->mode_valid && native_mode(&check->mode);
        if (check) drmModeFreeCrtc(check);
        restored = restored && !property(fd,saved->crtc_id,DRM_MODE_OBJECT_CRTC,"VRR_ENABLED",&id,&value) && value==0;
        printf("{\"event\":\"restore\",\"success\":%s}\n",restored?"true":"false");
        if (!restored) result=3;
    }
    if (fd>=0) {
        for (unsigned i=0;i<3;i++) destroy_buffer(fd,&b[i]);
        if (saved) drmModeFreeCrtc(saved);
        if (sink) drmModeFreeConnector(sink);
        if (res) drmModeFreeResources(res);
        close(fd);
    }
    if (result==1) fprintf(stderr,"Visual test failed or preflight refused: %s\n",strerror(errno));
    return result;
}
