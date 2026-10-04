/* Minimal userspace data scaffolding, not kernel ABI definitions or hardware emulation. */
#include <assert.h>
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
#include <stdio.h>

#define ASSERT(condition) assert(condition)
#define div_u64(n, d) ((uint64_t)(n) / (uint32_t)(d))
#define div64_u64(n, d) ((uint64_t)(n) / (uint64_t)(d))
#define MOD_FREESYNC_TO_CORE(ptr) ((struct core_freesync *)(void *)(ptr))

struct mod_freesync;
struct core_freesync; /* Selected arithmetic never dereferences this pointer. */
struct dc_crtc_timing_adjust {
    uint32_t v_total_min, v_total_max;
    bool allow_otg_v_count_halt;
};
struct dc {
    struct { uint32_t max_v_total; bool vtotal_limited_by_fp2; } caps;
};
struct dc_context { struct dc *dc; };
struct dc_stream_state {
    struct dc_context *ctx;
    struct {
        uint32_t pix_clk_100hz, h_total, v_total, v_front_porch;
        uint32_t min_refresh_in_uhz, max_refresh_in_uhz;
    } timing;
};
