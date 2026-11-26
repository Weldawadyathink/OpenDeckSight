/* Optical positioning and fixed-refresh control; no VRR or timing writes.
 * Reuse the exact native-mode/EDID guard and restoration helpers.
 */
#pragma push_macro("main")
#undef main
#define main ods_original_fixed_entry
#include "../usb/fixed_present.c"
#undef main
#pragma pop_macro("main")

static void optical(struct buffer *b, bool lit)
{
    for (unsigned y=0; y<1920; y++) {
        uint32_t *row=(uint32_t *)((uint8_t *)b->pixels+y*b->pitch);
        for (unsigned x=0; x<1080; x++) {
            uint32_t color=0x101010;
            /* Centered marker: rotation does not change its location. */
            if (x>=436 && x<644 && y>=856 && y<1064) color=0x505050;
            if (x>=440 && x<640 && y>=860 && y<1060) color=0x101010;
            if (x>=460 && x<620 && y>=880 && y<1040)
                color=lit ? 0x808080 : 0x101010;
            row[x]=color;
        }
    }
}

static bool marker(unsigned frame)
{
    if (frame<120) return false;   /* dark 2 s */
    if (frame<240) return true;    /* gray 2 s */
    if (frame<360) return false;   /* dark 2 s */
    if (frame<480) return ((frame-360)/2)%2; /* 30 optical edges/s */
    if (frame<960) return (frame-480)%2;    /* 60 optical edges/s */
    return false;                 /* dark 2 s; 1,080 frames total */
}

static int preview(void)
{
    struct buffer b={.pitch=1080*4,.size=1080*1920*4};
    b.pixels=malloc(b.size);
    if (!b.pixels) return 1;
    optical(&b,true);
    printf("P6\n1920 1080\n255\n");
    for (unsigned y=0;y<1080;y++) for (unsigned x=0;x<1920;x++) {
        uint32_t p=((uint32_t *)b.pixels)[x*1080+1079-y];
        unsigned char rgb[3]={p>>16,p>>8,p};
        fwrite(rgb,1,3,stdout);
    }
    free(b.pixels);
    return ferror(stdout)?1:0;
}

int main(int argc,char **argv)
{
    if (argc==2 && !strcmp(argv[1],"--preview")) return preview();
    bool position=argc==3 && !strcmp(argv[1],"--position");
    bool measure=argc==3 && !strcmp(argv[1],"--measure");
    bool run=position||measure;
    if (argc!=3 || (!run && strcmp(argv[1],"--check"))) {
        fprintf(stderr,"Usage: %s --preview | --check|--position|--measure /dev/dri/cardN\n",argv[0]);
        return 2;
    }
    int result=1,fd=-1;
    bool changed=false;
    drmModeRes *res=NULL;
    drmModeConnector *sink=NULL;
    drmModeCrtc *saved=NULL;
    struct buffer b[2]={0};
    setvbuf(stdout,NULL,_IOLBF,0);
    fd=open(argv[2],(run?O_RDWR:O_RDONLY)|O_CLOEXEC);
    if (fd<0) goto done;
    res=drmModeGetResources(fd);
    if (!res || res->count_connectors>32) goto done;
    for (int i=0;i<res->count_connectors;i++) {
        drmModeConnector *c=drmModeGetConnectorCurrent(fd,res->connectors[i]);
        if (!c) goto done;
        if (c->connection==DRM_MODE_CONNECTED) {
            if (sink || c->connector_type!=DRM_MODE_CONNECTOR_eDP) {
                drmModeFreeConnector(c); goto done;
            }
            sink=c;
        } else drmModeFreeConnector(c);
    }
    if (!sink || !expected_sink(fd,sink)) goto done;
    drmModeEncoder *enc=drmModeGetEncoder(fd,sink->encoder_id);
    if (!enc) goto done;
    saved=drmModeGetCrtc(fd,enc->crtc_id);
    drmModeFreeEncoder(enc);
    if (!saved || !saved->mode_valid || !saved->buffer_id || saved->x || saved->y ||
        !native_mode(&saved->mode)) goto done;
    uint64_t mono=0;
    if (drmGetCap(fd,DRM_CAP_TIMESTAMP_MONOTONIC,&mono) || mono!=1) goto done;
    printf("{\"event\":\"preflight\",\"native_mode_verified\":true,\"vrr_capable\":0,\"active\":%s}\n",run?"true":"false");
    if (!run) { result=0; goto done; }
    if (!drmIsMaster(fd)) { fprintf(stderr,"DRM master unavailable; refusing takeover.\n"); goto done; }
    struct sigaction sa={.sa_handler=stop};
    sigemptyset(&sa.sa_mask);
    sigaction(SIGINT,&sa,NULL); sigaction(SIGTERM,&sa,NULL); sigaction(SIGHUP,&sa,NULL);
    for (unsigned i=0;i<2;i++) {
        if (create_buffer(fd,&b[i])) goto done;
        optical(&b[i],i!=0);
    }
    if (drmModeSetCrtc(fd,saved->crtc_id,b[position?1:0].fb,0,0,&sink->connector_id,1,&saved->mode)) goto done;
    changed=true;
    if (position) {
        printf("{\"event\":\"position\",\"location\":\"center\",\"marker_size\":160,\"timeout_seconds\":600}\n");
        uint64_t deadline=now_ns()+600000000000ULL;
        struct timespec pause={.tv_sec=0,.tv_nsec=100000000};
        while (!stopped && now_ns()<deadline) nanosleep(&pause,NULL);
    } else {
        for (unsigned frame=0;frame<1080 && !stopped;frame++) {
            bool lit=marker(frame);
            struct event e={.pending=true};
            uint64_t submitted=now_ns();
            if (drmModePageFlip(fd,saved->crtc_id,b[lit?1:0].fb,DRM_MODE_PAGE_FLIP_EVENT,&e) || wait_flip(fd,&e)) goto done;
            printf("{\"event\":\"flip\",\"frame\":%u,\"marker_lit\":%s,\"sequence\":%u,\"submitted_ns\":%llu,\"event_ns\":%llu}\n",
                   frame,lit?"true":"false",e.sequence,(unsigned long long)submitted,(unsigned long long)e.time_ns);
        }
    }
    result=stopped?130:0;
done:
    if (changed) {
        bool restored=false;
        if (!drmModeSetCrtc(fd,saved->crtc_id,saved->buffer_id,saved->x,saved->y,&sink->connector_id,1,&saved->mode)) {
            drmModeCrtc *check=drmModeGetCrtc(fd,saved->crtc_id);
            restored=check && check->buffer_id==saved->buffer_id && check->mode_valid &&
                     native_mode(&check->mode) && !check->x && !check->y;
            if (check) drmModeFreeCrtc(check);
        }
        printf("{\"event\":\"restore\",\"success\":%s}\n",restored?"true":"false");
        if (!restored) result=3;
    }
    if (fd>=0) {
        for (unsigned i=0;i<2;i++) destroy_buffer(fd,&b[i]);
        if (saved) drmModeFreeCrtc(saved);
        if (sink) drmModeFreeConnector(sink);
        if (res) drmModeFreeResources(res);
        close(fd);
    }
    return result;
}
