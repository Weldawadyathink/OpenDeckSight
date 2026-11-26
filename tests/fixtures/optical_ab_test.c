/* Pure rendering/sequence checks; no DRM device is opened. */
#define main ods_optical_ab_entry
#include "../../lab/vrr/optical_ab.c"
#undef main
#include <assert.h>

int main(void)
{
    assert(phase_frames(0)==360 && phase_frames(1)==720 && phase_frames(2)==360);
    unsigned changes=0; bool last=false;
    for (unsigned frame=0;frame<360;frame++) {
        bool lit=preamble_lit(frame); changes+=lit!=last; last=lit;
        assert(lit==(frame>=120 && frame<240));
    }
    uint64_t duration=6000000000ULL;
    for (unsigned phase=0;phase<3;phase++) {
        for (unsigned frame=1;frame<=phase_frames(phase);frame++) {
            unsigned total=target_total(frame);
            assert(total>=1960 && total<=1986);
            assert(total>ODS_VRR_MIN_TOTAL && total<ODS_VRR_MAX_TOTAL);
            assert(target_period_ns(frame)>16666600 && target_period_ns(frame)<16948000);
            bool lit=frame%2; changes+=lit!=last; last=lit;
            duration+=target_period_ns(frame);
        }
    }
    assert(changes==1442 && !last);
    assert(duration>30000000000ULL && duration<31000000000ULL);
    struct buffer b={.pitch=1080*4+64,.size=(1080*4+64)*1920};
    b.pixels=malloc(b.size); assert(b.pixels);
    for (unsigned lit=0;lit<2;lit++) {
        memset(b.pixels,0xaa,b.size); optical(&b,lit);
        unsigned gray=0;
        for (unsigned y=0;y<1920;y++) {
            uint32_t *row=(uint32_t *)((uint8_t *)b.pixels+y*b.pitch);
            for (unsigned x=0;x<1080;x++) gray+=row[x]==0x808080;
            for (unsigned x=1080*4;x<b.pitch;x++) assert(((uint8_t *)b.pixels)[y*b.pitch+x]==0xaa);
        }
        assert(gray==(lit?25600u:0u));
        assert(((uint32_t *)((uint8_t *)b.pixels+960*b.pitch))[540]==(lit?0x808080u:0x101010u));
    }
    free(b.pixels);
    printf("1442 optical transitions; target duration %.6f s; unchanged centered marker.\n",duration/1e9);
    return 0;
}
