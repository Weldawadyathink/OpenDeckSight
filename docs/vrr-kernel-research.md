# Offline AMD VRR source investigation

Research date: 2026-10-04. This work compiles selected public AMD source
functions into a local userspace test executable. It neither boots a kernel
nor exercises a display, bridge, panel or sensor.

## Source identity and limits

The previously observed kernel release was `7.2.3-ogc3.1.fc44.x86_64`.
The public OGC tag `v7.2.3-ogc3` resolves to commit
`151eb3adafae8820f349a4454c1f1e8d5fc991a4`. This is a candidate source matching
that release family. The distribution's exact source RPM, packaging patches,
configuration and built module have **not** been matched to it. Do not call
this a test of the installed kernel.

Public downloads and their hashes are recorded in
[the source manifest](../research/vrr-kernel-sources.json). Complete downloaded
files remain in ignored `artifacts/vrr/kernel-source/`.
[OGC source tag](https://github.com/OpenGamingCollective/linux/tree/v7.2.3-ogc3)

## Two independent range checks

The candidate source retains the discovery obstacles found in the upstream
reference: `amdgpu_dm_update_freesync_caps()` requires the DP/eDP receiver's
`allow_invalid_MSA_timing_param`, then checks for a frequency span **greater
than 10 Hz**. Neither is satisfied by the existing DeckSight advertisement.
[Capability discovery](https://github.com/OpenGamingCollective/linux/blob/151eb3adafae8820f349a4454c1f1e8d5fc991a4/drivers/gpu/drm/amd/display/amdgpu_dm/amdgpu_dm.c#L14016)

A separate check exists in `mod_freesync_build_vrr_params()`. It rounds the
effective limits to whole Hz and requires a span **at least 10 Hz** for
`VRR_STATE_ACTIVE_VARIABLE`. A smaller range falls through to
`VRR_STATE_INACTIVE` with both vertical totals equal to the nominal total.
The `supported` flag can remain true. Thus a successful discovery override
and a true capability property would not make the proposed narrow test run.
[Timing parameter construction](https://github.com/OpenGamingCollective/linux/blob/151eb3adafae8820f349a4454c1f1e8d5fc991a4/drivers/gpu/drm/amd/display/modules/freesync/freesync.c#L985)

The slightly different comparisons matter: a synthetic 50–60 Hz request passes
the timing builder but fails ordinary DP discovery. It is a unit-test boundary
case, not a suggested display mode. Do not widen the physical experiment to
satisfy either heuristic.

## Executed local tests

[The harness](../tools/test_vrr_kernel.py) verifies source hashes, extracts seven
unchanged function definitions and the real FreeSync data structures, and
compiles them with minimal local data stubs. It preserves the AMD license
notices. No register access, device file, kernel interface, remote command or
display operation is present in the executable.

The source functions run twice: once with the original `MIN_REFRESH_RANGE=10`,
and once with **only that constant changed to 1 in the local harness**. This
second run isolates the next behavior; it is not a proposed global kernel
patch. Connector discovery, interrupts, flip scheduling, register writes and
the physical transport are outside this harness.

All **18 cases passed** with compiler warnings treated as errors and undefined
behavior sanitization enabled. Inputs use the public r04 EDID's nominal timing
(143.18 MHz, 1220 × 1956 total, 8-line vertical front porch). Requested frequency
ranges, stream range fields and GPU bounds are synthetic fixtures, not live
settings or verified hardware limits.
[Machine-readable results](../research/reports/vrr-kernel-unit-tests.json)

| Case | Observed source-function result |
| --- | --- |
| Original code, 59–60 Hz after assumed discovery | Supported flag true, state inactive, totals 1956 / 1956 |
| Harness threshold control, 59–60 Hz | State variable, totals 1957 / 1989 |
| Unsupported request, inactive request, or zero-width range | Equal totals; no variable range |
| Six consecutive 17,000 µs submissions in the threshold control | Fixed fallback activates; totals become 1957 / 1957 |
| Thirty subsequent 16,807 µs submissions, approximately 59.5 Hz | Fixed fallback remains active |
| Eleven subsequent 16,000 µs submissions | Fixed fallback exits; unequal totals return |
| Clean start followed by 16,807 µs submissions | Unequal totals remain |
| Missing stream range fields during rounding | 59 Hz target gives total 1990, below the intended frequency floor |
| Artificial GPU maximum total of 1980 | Builder clamps the range to that synthetic limit |

## Late-frame fallback can hide an otherwise working experiment

For a 59–60 Hz range, below-the-range frame multiplication (BTR/LFC) is disabled
because the maximum is less than twice the minimum. The preflip path therefore
uses `apply_fixed_refresh()`. Its exit policy requires submissions faster than
approximately `minimum + 1 Hz`, for more than ten qualifying samples. With a
one-Hz-wide test range, normal in-range submissions do not satisfy this exit
condition after fixed fallback has engaged.

The submission timestamps are **not** measured panel refresh intervals. The
16,000 µs recovery case does not demonstrate or request 62.5 Hz panel scanout;
it supplies timestamps to a source function. Runtime scheduling and resets
remain to be tested independently. A future scoped experiment must either
adapt this policy or deliberately reset and verify the VRR state after stalls.
[Fixed fallback policy](https://github.com/OpenGamingCollective/linux/blob/151eb3adafae8820f349a4454c1f1e8d5fc991a4/drivers/gpu/drm/amd/display/modules/freesync/freesync.c#L454)

Checking only the `variable` state is also insufficient: that state remained
set while the fallback flag was true and the two totals were equal.

## Quantization and range propagation

At the fixture's fixed pixel clock, a scan line lasts about 8.521 µs. The source
function's bounded rounding produces these endpoints:

| Vertical total | Vertical front porch if other timing stays fixed | Calculated refresh | Calculated frame interval |
| --- | --- | --- | --- |
| 1956, nominal EDID | 8 lines | 60.000335 Hz | 16,666.574 µs |
| 1957, upper-frequency endpoint | 9 lines | 59.969676 Hz | 16,675.094 µs |
| 1989, lower-frequency endpoint | 41 lines | 59.004855 Hz | 16,947.758 µs |

The endpoint difference is about **272.664 µs**, rather than the ideal
282.486 µs difference between exact 59 and 60 Hz. A future stimulus and optical
analysis must use the generated totals, not just integer rate labels.

`mod_freesync_calc_v_total_from_refresh()` chooses its rounding direction using
`stream->timing.min_refresh_in_uhz` and `max_refresh_in_uhz`, separately from the
requested configuration. With both fields zero, the same 59 Hz request rounds
to 1990 lines, or about 58.975204 Hz. A quirk must propagate consistent bounds
and validate the final totals. The harness has not established how those fields
are populated in the complete distribution build.

These calculations establish neither bridge behavior nor panel tolerance.
They are constraints for designing a future experiment.

## What a scoped diagnostic implementation still needs

1. Match the distribution source/package/configuration to the installed build,
   or explicitly choose and validate a separate diagnostic kernel baseline.
2. Gate the experiment on an explicit opt-in, internal eDP connector and full
   released EDID identity. Leave unrelated displays on the ordinary path.
3. Override discovery and the timing builder's range check only for that
   experiment. Keep the minimum and maximum bounds consistent through stream
   construction. Review late-frame fallback and desktop/passive-VRR behavior.
4. Record effective VRR state, fallback state, calculated totals and successful
   application of those totals. `get_freesync_config_for_crtc()` sets source
   MSA handling; `dc_stream_adjust_vmin_vmax()` applies timing adjustments and
   can defer or fail. Computed totals alone are not proof of register state.
5. Prepare the controlled presentation program, fixed-refresh control, temporary
   boot environment and recovery procedure before requesting an active test.

The candidate tree contains the expected DCN 3.01 register-programming path:
`dcn301_init.c` selects `dcn10_set_drr()`, and `optc301_set_drr()` programs minimum
and maximum vertical totals and manual trigger behavior. This is evidence that
the source has a variable-timing mechanism, not a measurement of this device or
of the bridge output. No MMIO was accessed.
[DCN 3.01 timing generator](https://github.com/OpenGamingCollective/linux/blob/151eb3adafae8820f349a4454c1f1e8d5fc991a4/drivers/gpu/drm/amd/display/dc/optc/dcn301/dcn301_optc.c#L47)

The subsequent [visual experiment checkpoint](vrr-visual-experiment.md) builds
a scoped replacement AMD module against the distribution's prepared headers,
retaining the existing kernel. It covers the narrow-range/fallback regressions
and has booted with its override disabled. Experimental VRR remains untested on
hardware and subject to the concrete approval requirements in [AGENTS.md](../AGENTS.md).

## Reproduce locally

```sh
python3 -B tools/test_vrr_kernel.py --fetch --output artifacts/vrr/kernel-unit-tests.json
```

This fetches only the two pinned public source files needed by the harness if
missing, checks their hashes, and compiles/runs on the development host. A C11
compiler with undefined-behavior sanitizer support is required. Generated C
and executables stay in ignored `.tools/vrr-kernel-tests/`. The optional output
path is local; the command has no device target.
