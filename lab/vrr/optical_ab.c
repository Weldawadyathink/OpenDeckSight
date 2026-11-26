/* Bounded optical A/B/A test, using the existing guarded 59-60 Hz driver.
 * Exact r04/native timing only. No AUX, MMIO or firmware operations here.
 */
#pragma push_macro("main")
#undef main
#define main ods_fixed_optical_entry
#include "optical_fixed.c"
#undef main
#pragma pop_macro("main")
#include "ods_vrr_guard.h"

static unsigned phase_frames(unsigned phase) { return phase==1 ? 720 : 360; }
static unsigned target_total(unsigned frame)
{
    unsigned step=(frame-1)%720;
    unsigned triangle=step<=360 ? step : 720-step;
    return 1960+26*triangle/360;
}
static uint64_t target_period_ns(unsigned frame)
{
    return (uint64_t)target_total(frame)*1220*1000000000u/143180000u;
}
static bool preamble_lit(unsigned frame) { return frame>=120 && frame<240; }

static int prop(int fd,uint32_t obj,uint32_t type,const char *name,uint32_t *id,uint64_t *value)
{
    drmModeObjectProperties *ps=drmModeObjectGetProperties(fd,obj,type);
    if (!ps) return -1;
    int found=-1;
    for (uint32_t i=0;i<ps->count_props;i++) {
        drmModePropertyPtr p=drmModeGetProperty(fd,ps->props[i]);
        if (p && !strcmp(p->name,name)) { *id=p->prop_id; *value=ps->prop_values[i]; found=0; }
        if (p) drmModeFreeProperty(p);
    }
    drmModeFreeObjectProperties(ps);
    return found;
}
static int request_vrr(int fd,uint32_t crtc,uint32_t property,bool enabled)
{
    drmModeAtomicReq *r=drmModeAtomicAlloc();
    if (!r) return -1;
    int result=drmModeAtomicAddProperty(r,crtc,property,enabled)<0 ? -1 : 0;
    if (!result) result=drmModeAtomicCommit(fd,r,DRM_MODE_ATOMIC_TEST_ONLY,NULL);
    if (!result) result=drmModeAtomicCommit(fd,r,0,NULL);
    drmModeAtomicFree(r);
    return result;
}
static int opt_in(void)
{
    FILE *f=fopen("/sys/module/amdgpu/parameters/ods_vrr_59_60","r");
    if (!f) return -1;
    int c=fgetc(f); fclose(f);
    if (c=='Y' || c=='1') return 1;
    if (c=='N' || c=='0') return 0;
    return -1;
}
static int sleep_until(uint64_t deadline)
{
    uint64_t wake=deadline>300000 ? deadline-300000 : deadline;
    struct timespec t={.tv_sec=wake/1000000000u,.tv_nsec=wake%1000000000u};
    int e;
    do { e=clock_nanosleep(CLOCK_MONOTONIC,TIMER_ABSTIME,&t,NULL); }
    while (e==EINTR && !stopped);
    if (e && e!=EINTR) { errno=e; return -1; }
    while (!stopped && now_ns()<deadline) {}
    return 0;
}
static int present(int fd,uint32_t crtc,struct buffer b[2],int phase,
                   unsigned frame,unsigned ordinal,bool lit,uint64_t deadline)
{
    struct event e={.pending=true};
    uint64_t submitted=now_ns();
    if (drmModePageFlip(fd,crtc,b[lit?1:0].fb,DRM_MODE_PAGE_FLIP_EVENT,&e) || wait_flip(fd,&e)) return -1;
    printf("{\"event\":\"flip\",\"phase\":%d,\"frame\":%u,\"ordinal\":%u,\"marker_lit\":%s,\"target_total\":%u,\"deadline_ns\":%llu,\"submitted_ns\":%llu,\"event_ns\":%llu,\"sequence\":%u}\n",
           phase,frame,ordinal,lit?"true":"false",phase<0?1956:target_total(frame),
           (unsigned long long)deadline,(unsigned long long)submitted,(unsigned long long)e.time_ns,e.sequence);
    return 0;
}

int main(int argc,char **argv)
{
    if (argc==2 && !strcmp(argv[1],"--preview")) return preview();
    bool experiment=argc==3 && !strcmp(argv[1],"--experiment");
    bool control=argc==3 && !strcmp(argv[1],"--control");
    if (argc!=3 || (!experiment && !control && strcmp(argv[1],"--check"))) {
        fprintf(stderr,"Usage: %s --preview | --check|--control|--experiment /dev/dri/cardN\n",argv[0]); return 2;
    }
    bool run=experiment||control,changed=false,vrr_requested=false;
    int result=1,fd=-1,enabled=opt_in();
    drmModeRes *res=NULL;
    drmModeConnector *sink=NULL;
    drmModeCrtc *saved=NULL;
    struct buffer b[2]={0};
    uint32_t vrr_prop=0,id=0;
    uint64_t value=0,capability=0;
    setvbuf(stdout,NULL,_IOLBF,0);
    fd=open(argv[2],(run?O_RDWR:O_RDONLY)|O_CLOEXEC);
    if (fd<0 || drmSetClientCap(fd,DRM_CLIENT_CAP_ATOMIC,1)) goto done;
    res=drmModeGetResources(fd);
    if (!res || res->count_connectors>32) goto done;
    for (int i=0;i<res->count_connectors;i++) {
        drmModeConnector *c=drmModeGetConnectorCurrent(fd,res->connectors[i]);
        if (!c) goto done;
        if (c->connection==DRM_MODE_CONNECTED) {
            if (sink || c->connector_type!=DRM_MODE_CONNECTOR_eDP) { drmModeFreeConnector(c); goto done; }
            sink=c;
        } else drmModeFreeConnector(c);
    }
    if (!sink || prop(fd,sink->connector_id,DRM_MODE_OBJECT_CONNECTOR,"EDID",&id,&value)) goto done;
    drmModePropertyBlobPtr edid=drmModeGetPropertyBlob(fd,value);
    bool identity=edid && ods_vrr_identity(true,true,edid->data,edid->length);
    if (edid) drmModeFreePropertyBlob(edid);
    if (!identity || prop(fd,sink->connector_id,DRM_MODE_OBJECT_CONNECTOR,"vrr_capable",&id,&capability)) goto done;
    if (enabled<0 || capability!=(unsigned)enabled || (experiment && enabled!=1) || (control && enabled!=0)) goto done;
    drmModeEncoder *enc=drmModeGetEncoder(fd,sink->encoder_id);
    if (!enc) goto done;
    saved=drmModeGetCrtc(fd,enc->crtc_id); drmModeFreeEncoder(enc);
    if (!saved || !saved->mode_valid || !saved->buffer_id || saved->x || saved->y || !native_mode(&saved->mode)) goto done;
    if (prop(fd,saved->crtc_id,DRM_MODE_OBJECT_CRTC,"VRR_ENABLED",&vrr_prop,&value) || value) goto done;
    if (drmGetCap(fd,DRM_CAP_TIMESTAMP_MONOTONIC,&value) || value!=1) goto done;
    printf("{\"event\":\"preflight\",\"program\":\"optical-ab-v1\",\"native_mode_verified\":true,\"vrr_capable\":%llu,\"opt_in\":%s,\"experiment\":%s}\n",
           (unsigned long long)capability,enabled?"true":"false",experiment?"true":"false");
    if (!run) { result=0; goto done; }
    if (!drmIsMaster(fd)) { fprintf(stderr,"DRM master unavailable; refusing takeover.\n"); goto done; }
    struct sigaction sa={.sa_handler=stop}; sigemptyset(&sa.sa_mask);
    sigaction(SIGINT,&sa,NULL); sigaction(SIGTERM,&sa,NULL); sigaction(SIGHUP,&sa,NULL);
    for (unsigned i=0;i<2;i++) { if (create_buffer(fd,&b[i])) goto done; optical(&b[i],i!=0); }
    if (drmModeSetCrtc(fd,saved->crtc_id,b[0].fb,0,0,&sink->connector_id,1,&saved->mode)) goto done;
    changed=true;
    uint64_t all_start=now_ns(),start=all_start;
    unsigned ordinal=0;
    printf("{\"event\":\"phase\",\"phase\":-1,\"vrr_requested\":false,\"frames\":360}\n");
    for (unsigned frame=0;frame<360 && !stopped;frame++,ordinal++) {
        if (now_ns()-start>8000000000ULL || present(fd,saved->crtc_id,b,-1,frame,ordinal,preamble_lit(frame),0)) goto done;
    }
    for (unsigned phase=0;phase<3 && !stopped;phase++) {
        bool variable=experiment && phase==1;
        vrr_requested=variable;
        if (request_vrr(fd,saved->crtc_id,vrr_prop,variable)) goto done;
        unsigned frames=phase_frames(phase);
        printf("{\"event\":\"phase\",\"phase\":%u,\"vrr_requested\":%s,\"frames\":%u}\n",phase,variable?"true":"false",frames);
        start=now_ns(); uint64_t deadline=start+target_period_ns(1);
        for (unsigned frame=1;frame<=frames && !stopped;frame++,ordinal++) {
            uint64_t now=now_ns();
            if (now-start>(phase==1?16000000000ULL:8000000000ULL) || now-all_start>40000000000ULL) goto done;
            if (sleep_until(deadline)) goto done;
            if (stopped) break;
            if (present(fd,saved->crtc_id,b,(int)phase,frame,ordinal,frame%2,deadline)) goto done;
            deadline+=target_period_ns(frame+1);
        }
    }
    result=stopped?130:0;
done:
    if (fd>=0 && saved && vrr_prop && (changed || vrr_requested)) {
        if (request_vrr(fd,saved->crtc_id,vrr_prop,false)) result=3;
    }
    if (changed) {
        bool restored=!drmModeSetCrtc(fd,saved->crtc_id,saved->buffer_id,saved->x,saved->y,&sink->connector_id,1,&saved->mode);
        drmModeCrtc *check=drmModeGetCrtc(fd,saved->crtc_id);
        restored=restored && check && check->buffer_id==saved->buffer_id && check->mode_valid &&
                 native_mode(&check->mode) && !check->x && !check->y;
        if (check) drmModeFreeCrtc(check);
        restored=restored && !prop(fd,saved->crtc_id,DRM_MODE_OBJECT_CRTC,"VRR_ENABLED",&id,&value) && value==0;
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
    if (result==1) fprintf(stderr,"Optical A/B test failed, timed out or preflight refused.\n");
    return result;
}
