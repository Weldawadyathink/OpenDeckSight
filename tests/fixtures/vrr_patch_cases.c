/* Tests actual patched builder/preflip/vupdate functions, plus portable guards. */
static struct mod_vrr_params build_test(struct dc_stream_state *s, bool lab,
                                      enum mod_vrr_state state, unsigned lo, unsigned hi)
{
    struct core_freesync module = {.dc=s->ctx->dc};
    struct mod_freesync_config c = {.state=state, .btr=false,
        .min_refresh_in_uhz=lo, .max_refresh_in_uhz=hi};
    struct mod_vrr_params r = {0};
    s->ods_vrr_lab=lab;
    s->timing.min_refresh_in_uhz=lo;
    s->timing.max_refresh_in_uhz=hi;
    mod_freesync_build_vrr_params((struct mod_freesync *)&module,s,&c,&r);
    return r;
}
static bool allowed(const struct mod_vrr_params *r)
{
    return ods_vrr_adjust_allowed(r->adjust.v_total_min,r->adjust.v_total_max,
        r->adjust.v_total_mid,r->adjust.v_total_mid_frame_num,r->adjust.allow_otg_v_count_halt);
}
int main(void)
{
    unsigned char edid[256];
    memcpy(edid,ods_r04_edid,256);
    assert(ods_vrr_identity(true,true,edid,256));
    assert(!ods_vrr_identity(false,true,edid,256));
    assert(!ods_vrr_identity(true,false,edid,256));
    assert(!ods_vrr_identity(true,true,NULL,256));
    assert(!ods_vrr_identity(true,true,edid,255));
    assert(!ods_vrr_identity(true,true,edid,257));
    for(unsigned i=0;i<256;i++) {
        edid[i]^=1; assert(!ods_vrr_identity(true,true,edid,256)); edid[i]^=1;
    }
    unsigned mode[]={143180,1080,1112,1120,1220,0,1920,1928,1930,1956,0,5};
#define MODE_OK ods_vrr_native(mode[0],mode[1],mode[2],mode[3],mode[4],mode[5],mode[6],mode[7],mode[8],mode[9],mode[10],mode[11])
    assert(MODE_OK);
    for(unsigned i=0;i<12;i++) { mode[i]++; assert(!MODE_OK); mode[i]--; }
    for(unsigned lo=1950;lo<=2000;lo++) for(unsigned hi=1950;hi<=2000;hi++) {
        assert(ods_vrr_adjust_allowed(lo,hi,0,0,false)==
               ((lo==1956 && hi==1956)||(lo==1957 && hi==1989)));
        assert(!ods_vrr_adjust_allowed(lo,hi,0,0,true));
        assert(!ods_vrr_adjust_allowed(lo,hi,1956,1,false));
    }
    assert(!ods_vrr_adjust_allowed(1957,1989,0,1,false));

    struct dc dc={.caps={.max_v_total=4095}};
    struct dc_context context={.dc=&dc};
    dc.ctx=&context;
    struct dc_stream_state s={.ctx=&context,
        .timing={.pix_clk_100hz=1431800,.h_total=1220,.v_total=1956,.v_front_porch=8}};
    struct mod_vrr_params r=build_test(&s,false,VRR_STATE_ACTIVE_VARIABLE,59000000,60000000);
    assert(r.state==VRR_STATE_INACTIVE && r.adjust.v_total_min==1956 && allowed(&r));
    r=build_test(&s,true,VRR_STATE_ACTIVE_VARIABLE,59000000,60000000);
    assert(r.state==VRR_STATE_ACTIVE_VARIABLE && r.adjust.v_total_min==1957 &&
           r.adjust.v_total_max==1989 && allowed(&r) && !r.fixed.fixed_active && !r.btr.btr_enabled);
    struct core_freesync module={.dc=&dc};
    struct dc_plane_state plane={0};
    for(unsigned i=0;i<200;i++) {
        /* Late timestamps previously caused sticky fallback; no diagnostic fallback now. */
        mod_freesync_handle_preflip((struct mod_freesync *)&module,&plane,&s,17000+i*16807,&r);
        mod_freesync_handle_v_update((struct mod_freesync *)&module,&s,&r);
        assert(r.adjust.v_total_min==1957 && r.adjust.v_total_max==1989 &&
               !r.fixed.fixed_active && allowed(&r) && stub_calls==0);
    }
    r=build_test(&s,true,VRR_STATE_INACTIVE,59000000,60000000);
    mod_freesync_handle_v_update((struct mod_freesync *)&module,&s,&r);
    assert(r.adjust.v_total_min==1956 && r.adjust.v_total_max==1956 && allowed(&r));
    r=build_test(&s,true,VRR_STATE_UNSUPPORTED,59000000,60000000);
    assert(!r.supported && r.adjust.v_total_min==1956 && allowed(&r));
    r=build_test(&s,true,VRR_STATE_ACTIVE_VARIABLE,58000000,60000000);
    assert(r.state==VRR_STATE_INACTIVE && allowed(&r));
    r=build_test(&s,true,VRR_STATE_ACTIVE_VARIABLE,59000000,60000000);
    s.timing.min_refresh_in_uhz=0; s.timing.max_refresh_in_uhz=0;
    r.adjust.v_total_max=mod_freesync_calc_v_total_from_refresh(&s,59000000);
    assert(r.adjust.v_total_max==1990 && !allowed(&r));
    r=build_test(&s,false,VRR_STATE_ACTIVE_VARIABLE,49000000,60000000);
    assert(r.state==VRR_STATE_ACTIVE_VARIABLE && r.adjust.v_total_max>1989);
    mod_freesync_handle_preflip((struct mod_freesync *)&module,&plane,&s,17000,&r);
    assert(stub_calls>0); /* Unrelated streams still run the normal callback path. */
    puts("{\"identity_mutations\":256,\"timing_mutations\":12,\"total_pairs\":2601,\"late_frame_cycles\":200,\"range\":[1957,1989],\"passed\":true}");
    return 0;
}
