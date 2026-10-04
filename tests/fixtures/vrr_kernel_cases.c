/* Exercise actual extracted AMD functions; fixture inputs are not approved modes. */
static const char *state_name(enum mod_vrr_state state)
{
    switch (state) {
    case VRR_STATE_UNSUPPORTED: return "unsupported";
    case VRR_STATE_DISABLED: return "disabled";
    case VRR_STATE_INACTIVE: return "inactive";
    case VRR_STATE_ACTIVE_VARIABLE: return "variable";
    case VRR_STATE_ACTIVE_FIXED: return "fixed";
    }
    return "invalid";
}

static void emit(const char *name, const struct mod_vrr_params *vrr, bool comma)
{
    printf("%s{\"case\":\"%s\",\"state\":\"%s\",\"supported\":%s,"
           "\"v_total_min\":%u,\"v_total_max\":%u,\"btr_enabled\":%s,"
           "\"fixed_fallback_active\":%s}", comma ? ",\n" : "", name,
           state_name(vrr->state), vrr->supported ? "true" : "false",
           vrr->adjust.v_total_min, vrr->adjust.v_total_max,
           vrr->btr.btr_enabled ? "true" : "false",
           vrr->fixed.fixed_active ? "true" : "false");
}

static struct mod_vrr_params build(struct dc_stream_state *stream,
                                  unsigned int min_hz, unsigned int max_hz,
                                  enum mod_vrr_state state)
{
    struct mod_freesync module = {0};
    struct mod_freesync_config config = {
        .state = state, .vsif_supported = true, .btr = true,
        .min_refresh_in_uhz = min_hz * 1000000,
        .max_refresh_in_uhz = max_hz * 1000000,
    };
    struct mod_vrr_params result = {0};
    stream->timing.min_refresh_in_uhz = config.min_refresh_in_uhz;
    stream->timing.max_refresh_in_uhz = config.max_refresh_in_uhz;
    mod_freesync_build_vrr_params(&module, stream, &config, &result);
    return result;
}

int main(void)
{
    struct dc dc = {.caps = {.max_v_total = 4095}}; /* Synthetic GPU bound. */
    struct dc_context context = {.dc = &dc};
    struct dc_stream_state stream = {
        .ctx = &context,
        .timing = {.pix_clk_100hz = 1431800, .h_total = 1220,
                   .v_total = 1956, .v_front_porch = 8},
    };
    struct mod_vrr_params result;
    printf("[\n");

    result = build(&stream, 59, 60, VRR_STATE_ACTIVE_VARIABLE);
    assert(result.supported);
    assert(!result.btr.btr_enabled);
    if (MIN_REFRESH_RANGE == 10) {
        assert(result.state == VRR_STATE_INACTIVE);
        assert(result.adjust.v_total_min == 1956 && result.adjust.v_total_max == 1956);
    } else {
        assert(result.state == VRR_STATE_ACTIVE_VARIABLE);
        assert(result.adjust.v_total_min == 1957 && result.adjust.v_total_max == 1989);
    }
    emit("59-60-after-discovery", &result, false);

    result = build(&stream, 50, 60, VRR_STATE_ACTIVE_VARIABLE);
    assert(result.state == VRR_STATE_ACTIVE_VARIABLE);
    assert(result.adjust.v_total_min < result.adjust.v_total_max);
    emit("50-60-builder-boundary-only", &result, true);

    result = build(&stream, 49, 60, VRR_STATE_ACTIVE_VARIABLE);
    assert(result.state == VRR_STATE_ACTIVE_VARIABLE);
    emit("49-60-positive-control", &result, true);

    result = build(&stream, 59, 60, VRR_STATE_UNSUPPORTED);
    assert(result.state == VRR_STATE_UNSUPPORTED && !result.supported);
    assert(result.adjust.v_total_min == 1956 && result.adjust.v_total_max == 1956);
    emit("unsupported-stays-fixed", &result, true);

    result = build(&stream, 59, 60, VRR_STATE_INACTIVE);
    assert(result.state == VRR_STATE_INACTIVE);
    assert(result.adjust.v_total_min == 1956 && result.adjust.v_total_max == 1956);
    emit("disabled-request-stays-fixed", &result, true);

    result = build(&stream, 60, 60, VRR_STATE_ACTIVE_VARIABLE);
    assert(result.state == VRR_STATE_INACTIVE);
    emit("zero-span-stays-fixed", &result, true);

    result = build(&stream, 59, 60, VRR_STATE_ACTIVE_VARIABLE);
    /* Only the threshold-control build reaches this active-variable path. */
    if (result.state == VRR_STATE_ACTIVE_VARIABLE) {
        for (int i = 0; i < 6; ++i)
            apply_fixed_refresh(NULL, &stream, 17000, &result);
        assert(result.fixed.fixed_active);
        assert(result.adjust.v_total_min == result.adjust.v_total_max);
        emit("six-slow-submissions-enter-fallback", &result, true);

        for (int i = 0; i < 30; ++i)
            apply_fixed_refresh(NULL, &stream, 16807, &result); /* About 59.5 Hz. */
        assert(result.fixed.fixed_active);
        emit("in-range-submissions-do-not-exit-fallback", &result, true);

        for (int i = 0; i < 11; ++i)
            apply_fixed_refresh(NULL, &stream, 16000, &result);
        assert(!result.fixed.fixed_active);
        assert(result.adjust.v_total_min < result.adjust.v_total_max);
        emit("faster-submissions-exit-fallback", &result, true);

        result = build(&stream, 59, 60, VRR_STATE_ACTIVE_VARIABLE);
        for (int i = 0; i < 30; ++i)
            apply_fixed_refresh(NULL, &stream, 16807, &result);
        assert(!result.fixed.fixed_active);
        assert(result.adjust.v_total_min < result.adjust.v_total_max);
        emit("clean-in-range-start-retains-variable-totals", &result, true);

        /* The rounding branch also depends on stream timing's range fields.
         * These are separate from mod_freesync_config's requested range. */
        stream.timing.min_refresh_in_uhz = 0;
        stream.timing.max_refresh_in_uhz = 0;
        result.adjust.v_total_min = mod_freesync_calc_v_total_from_refresh(&stream, 60000000);
        result.adjust.v_total_max = mod_freesync_calc_v_total_from_refresh(&stream, 59000000);
        assert(result.adjust.v_total_min == 1957 && result.adjust.v_total_max == 1990);
        emit("zero-stream-limits-round-59-hz-below-bound", &result, true);

        dc.caps.max_v_total = 1980; /* Artificially restricted hardware. */
        result = build(&stream, 59, 60, VRR_STATE_ACTIVE_VARIABLE);
        assert(result.adjust.v_total_max <= 1980);
        emit("synthetic-gpu-limit-clamps-range", &result, true);
    }
    printf("\n]\n");
    return 0;
}
