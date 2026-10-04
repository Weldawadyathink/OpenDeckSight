/* Host-only checks of the timing guard. No DRM device is opened. */
#define main fixed_present_main
#include "../../lab/usb/fixed_present.c"
#undef main
#include <assert.h>

int main(void) {
    drmModeModeInfo mode = {
        .clock = 143180, .hdisplay = 1080, .hsync_start = 1112,
        .hsync_end = 1120, .htotal = 1220, .vdisplay = 1920,
        .vsync_start = 1928, .vsync_end = 1930, .vtotal = 1956,
        .flags = DRM_MODE_FLAG_PHSYNC | DRM_MODE_FLAG_PVSYNC,
    };
    assert(native_mode(&mode));
    drmModeModeInfo candidate;
#define REJECT_CHANGE(field, value) do { \
        candidate = mode; candidate.field = (value); \
        assert(!native_mode(&candidate)); \
    } while (0)
    REJECT_CHANGE(clock, 190907); /* Higher fixed rate. */
    REJECT_CHANGE(clock, 143179); /* Even a small clock change is out of scope. */
    REJECT_CHANGE(vtotal, 1957);  /* Proposed VRR range endpoint must be rejected. */
    REJECT_CHANGE(vtotal, 1989);
    REJECT_CHANGE(hdisplay, 1280);
    REJECT_CHANGE(hsync_start, 1113);
    REJECT_CHANGE(hsync_end, 1121);
    REJECT_CHANGE(htotal, 1221);
    REJECT_CHANGE(hskew, 1);
    REJECT_CHANGE(vdisplay, 1921);
    REJECT_CHANGE(vsync_start, 1929);
    REJECT_CHANGE(vsync_end, 1931);
    REJECT_CHANGE(vscan, 2);
    REJECT_CHANGE(flags, mode.flags | DRM_MODE_FLAG_INTERLACE);
    REJECT_CHANGE(flags, mode.flags | DRM_MODE_FLAG_DBLSCAN);
    REJECT_CHANGE(flags, DRM_MODE_FLAG_NHSYNC | DRM_MODE_FLAG_NVSYNC);
    puts("Native-mode control and 16 timing-guard rejection cases passed.");
    return 0;
}
