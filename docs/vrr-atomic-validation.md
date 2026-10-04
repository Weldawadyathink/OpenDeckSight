# VRR request validation on the USB baseline

On 2026-10-04, the running USB kernel accepted an atomic **TEST_ONLY** request
for `VRR_ENABLED = 1` even though the internal connector advertised
`vrr_capable = 0`. The request was not applied. This establishes a useful
negative control: successful request validation is not evidence that variable
timing is being generated or passed through the bridge.

## Physical result

The kernel was `7.2.3-ogc3.1.fc44.x86_64`. The collector required the exact
public r04 EDID and the already-active native mode: 143.18 MHz pixel clock,
1080 × 1920 active pixels, and 1220 × 1956 totals with the released sync timing.

| TEST_ONLY request | Result | Checked live KMS state |
| --- | --- | --- |
| `VRR_ENABLED = 0` | Accepted | Unchanged |
| `VRR_ENABLED = 1` | Accepted | Unchanged |
| `VRR_ENABLED = 2`, invalid boolean control | Rejected with `EINVAL` | Unchanged |

After each request, the collector re-read the connector binding and capability,
CRTC active/mode/VRR properties, and the complete mode blob. These are software
readbacks, not hardware-register or optical measurements. The live VRR property
remained disabled. The invalid-value control confirms that rejection is
observable through this test path; it does not test the display's tolerance.
The [anonymous report](../research/reports/vrr-atomic-validation.json) records
the results and the executed source hashes.

Linux documents `VRR_ENABLED` as a hint, and lack of sink support need not cause
a failure. The observed acceptance is consistent with that contract. It does
not show how an applying commit would behave, nor prove that ANX7580 can or
cannot forward variable timing.
[DRM CRTC properties](https://cdn.kernel.org/doc/html/latest/gpu/drm-kms.html#standard-crtc-properties)

## Diagnostic boundary and reproduction

The [collector](../opendecksight/vrr_dry_run.py) opens the primary DRM node and
requires DRM master; it does not take ownership away from another client or
stop a compositor. It enables the atomic client capability on its own file
descriptor, then constructs single-property requests. Every submission has
exactly `DRM_MODE_ATOMIC_TEST_ONLY` (`0x0100`). There is no applying-commit
option, modeset permission, page flip, custom timing, AUX access or MMIO access.

The public UAPI defines TEST_ONLY as validation without applying the update.
The inspected core ioctl implementation selects `drm_atomic_check_only()` for
this flag instead of either commit function. These source files are pinned and
hashed in the [source manifest](../research/vrr-kernel-sources.json); as with
the earlier arithmetic harness, the candidate OGC source has not been matched
to the distribution's exact build inputs.
[Atomic flags](https://github.com/OpenGamingCollective/linux/blob/151eb3adafae8820f349a4454c1f1e8d5fc991a4/include/uapi/drm/drm_mode.h),
[atomic ioctl](https://github.com/OpenGamingCollective/linux/blob/151eb3adafae8820f349a4454c1f1e8d5fc991a4/drivers/gpu/drm/drm_atomic_uapi.c)

In an authorized USB-lab session, with its current SSH host key already verified:

```sh
python3 -B tools/test_vrr_atomic.py root@<lab-address> \
  --known-hosts artifacts/usb-lab/known_hosts \
  --output artifacts/usb-lab/vrr-atomic-test-only.json
```

The output path must be new. The wrapper streams Python with bytecode writes
disabled; it does not install files on the target. Raw reports remain ignored.
Six local tests cover TEST_ONLY-only submission, error paths without an
applying retry, bounded request values and the exact native-timing guard.
Together with the existing VRR/DPCD tests, all 15 cases passed.

## What can proceed before optical sensors

The [fixed-refresh control](vrr-fixed-refresh-control.md) has already verified
native presentation and GPU event collection. This test adds validation of the
VRR request interface and demonstrates why a successful ioctl alone would be
an inadequate success criterion.

The subsequent [visual experiment checkpoint](vrr-visual-experiment.md) built the
narrowly scoped driver change and stimulus, with discovery, independent range,
timing-bound and fallback guards. Its disabled-override baseline has booted and
run the native control. A separately approved physical A/B/A experiment then
produced variable GPU event intervals in its guarded window, with no reported
visual anomalies, and restored the disabled baseline. Neither development nor
this source-side observation required optical sensors. Optical measurements
must still establish whether the bridge and panel follow the source.
