/* Arithmetic only; these are synthetic range inputs, not panel capabilities. */
int main(void)
{
    struct dc_stream_state stream = {
        .timing = {.pix_clk_100hz = 1431800, .h_total = 1220,
                   .v_total = 1956, .v_front_porch = 8,
                   .min_refresh_in_uhz = 59000000, .max_refresh_in_uhz = 60000000},
    };
    assert(mod_freesync_calc_v_total_from_refresh(&stream,60000000)==1957);
    assert(mod_freesync_calc_v_total_from_refresh(&stream,59000000)==1989);
    stream.timing.min_refresh_in_uhz=58000000;
    assert(mod_freesync_calc_v_total_from_refresh(&stream,60000000)==1957);
    assert(mod_freesync_calc_v_total_from_refresh(&stream,58000000)==2023);
    printf("Pinned AMD arithmetic: 59-60 -> 1957/1989; 58-60 -> 1957/2023. No hardware test.\n");
    return 0;
}
