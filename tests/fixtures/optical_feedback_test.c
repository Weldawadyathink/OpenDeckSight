/* Local scheduling/render checks only; no DRM device is opened. */
#define main ods_optical_feedback_entry
#include "../../lab/vrr/optical_feedback.c"
#undef main
#include <assert.h>

int main(void)
{
    unsigned counts[2]={0},changes=0;
    bool last=false;
    for (unsigned frame=0;frame<360;frame++) {
        bool lit=preamble_lit(frame); changes+=lit!=last; last=lit;
    }
    for (unsigned phase=0;phase<3;phase++) {
        for (unsigned frame=1;frame<=phase_frames(phase);frame++) {
            unsigned total=target_total(frame);
            assert(total==1964 || total==1980);
            assert(total>ODS_VRR_MIN_TOTAL && total<ODS_VRR_MAX_TOTAL);
            uint64_t previous=900000000000ULL;
            uint64_t deadline=feedback_deadline((int)phase,frame,previous);
            if (phase!=1 || frame==1) assert(deadline==0);
            else {
                assert(deadline==previous+target_period_ns(frame)-350000);
                assert(deadline>previous+16300000 && deadline<previous+16600000);
                /* A delayed event shifts the next deadline by the entire delay. */
                assert(feedback_deadline((int)phase,frame,previous+33350000)==deadline+33350000);
            }
            if (phase==1) counts[total==1980]++;
            bool lit=frame%2; changes+=lit!=last; last=lit;
        }
    }
    assert(counts[0]==360 && counts[1]==360 && changes==1442 && !last);
    printf("1442 transitions; 360 targets per plateau; event anchoring and unchanged range verified.\n");
    return 0;
}
