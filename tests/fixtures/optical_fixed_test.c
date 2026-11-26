/* Host-only rendering/sequence checks; no DRM device is opened. */
#define main optical_program_entry
#include "../../lab/vrr/optical_fixed.c"
#undef main
#include <assert.h>

int main(void)
{
    struct buffer b={.pitch=1080*4+64,.size=(1080*4+64)*1920};
    b.pixels=malloc(b.size);
    assert(b.pixels);
    for (unsigned lit=0;lit<2;lit++) {
        memset(b.pixels,0xaa,b.size);
        optical(&b,lit);
        unsigned target=0;
        for (unsigned y=0;y<1920;y++) {
            uint32_t *row=(uint32_t *)((uint8_t *)b.pixels+y*b.pitch);
            for (unsigned x=0;x<1080;x++) {
                if (row[x]==0x808080) target++;
                assert(row[x]==0x101010 || row[x]==0x505050 || (lit && row[x]==0x808080));
            }
            for (unsigned x=1080*4;x<b.pitch;x++)
                assert(((uint8_t *)b.pixels)[y*b.pitch+x]==0xaa);
        }
        assert(target==(lit?160u*160u:0u));
        assert(((uint32_t *)((uint8_t *)b.pixels+960*b.pitch))[540]==(lit?0x808080u:0x101010u));
    }
    free(b.pixels);
    assert(!marker(0) && !marker(119) && marker(120) && marker(239));
    assert(!marker(240) && !marker(359) && !marker(960) && !marker(1079));
    unsigned transitions=0;
    for (unsigned i=1;i<1080;i++) transitions+=marker(i)!=marker(i-1);
    assert(transitions==542);
    puts("Centered marker, framebuffer padding and fixed-refresh optical sequence verified.");
    return 0;
}
