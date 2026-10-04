#!/usr/bin/env python3
"""Generate/apply a local, hash-pinned AMD display diagnostic patch. No device I/O."""
import argparse
import difflib
import hashlib
import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
BASE = 'drivers/gpu/drm/amd/display/'
FILES = [BASE + s for s in ('amdgpu_dm/amdgpu_dm.c', 'dc/dc_stream.h',
                           'dc/core/dc.c', 'modules/freesync/freesync.c')]


def once(text, old, new):
    if text.count(old) != 1:
        raise ValueError('patch anchor is missing or ambiguous: ' + old[:100])
    return text.replace(old, new, 1)


def function(text, name, edit):
    pattern = r'^(?:static )?(?:void|bool) ' + re.escape(name) + r'\([^;{}]*\)\n\{.*?^\}'
    match = re.search(pattern, text, re.M | re.S)
    if not match:
        raise ValueError('function not found: ' + name)
    return text[:match.start()] + edit(match.group()) + text[match.end():]


def transform(original):
    output = dict(original)
    output[BASE + 'dc/ods_vrr_guard.h'] = (ROOT / 'lab/vrr/ods_vrr_guard.h').read_text()
    name = BASE + 'dc/dc_stream.h'
    output[name] = once(output[name], '\tbool ignore_msa_timing_param;',
                       '\t/* Explicit opt-in, exact r04 native-timing experiment only. */\n'
                       '\tbool ods_vrr_lab;\n\tbool ignore_msa_timing_param;')
    name = BASE + 'amdgpu_dm/amdgpu_dm.c'
    text = output[name]
    insert = '''#include "ods_vrr_guard.h"

/* Never enabled by default; changing this option requires a driver reload/boot.
 * The lab image uses a reboot, never a live driver unload. No panel limits claimed.
 */
static bool ods_vrr_59_60;
module_param_named(ods_vrr_59_60, ods_vrr_59_60, bool, 0444);
MODULE_PARM_DESC(ods_vrr_59_60, "Experimental exact DeckSight r04 59-60 Hz override (default off)");

static bool ods_vrr_sink(struct drm_connector *connector, const struct drm_edid *drm_edid)
{
	const struct edid *edid = drm_edid ? drm_edid_raw(drm_edid) : NULL;

	/* drm_edid_raw returns the validated allocation; extension count is guarded. */
	return ods_vrr_identity(ods_vrr_59_60,
		connector->connector_type == DRM_MODE_CONNECTOR_eDP,
		(const unsigned char *)edid, edid && edid->extensions == 1 ? 256 : 0);
}

'''
    text = once(text, '/* Maximum backlight level. */', insert + '/* Maximum backlight level. */')

    def caps(s):
        s = once(s, '\t/* Some eDP panels only have the refresh rate range info in DisplayID */', '''	/* Source-side experiment only. Do not modify sink registers or EDID. */
	if (ods_vrr_sink(connector, drm_edid)) {
		amdgpu_dm_connector->min_vfreq = 59;
		amdgpu_dm_connector->max_vfreq = 60;
		freesync_capable = true;
		drm_info(connector->dev, "ODS_VRR: opt-in r04 source override 59-60 Hz; sink support unknown\\n");
		goto update;
	}

	/* Some eDP panels only have the refresh rate range info in DisplayID */''')
        s = once(s, 'dm_con_state->freesync_on_desktop_capable = freesync_capable;',
                 'dm_con_state->freesync_on_desktop_capable =\n'
                 '\t\t\tfreesync_capable && !ods_vrr_sink(connector, drm_edid);')
        return once(s, 'drm_connector_set_passive_vrr_capable_property(connector, freesync_capable);',
                    'drm_connector_set_passive_vrr_capable_property(connector,\n'
                    '\t\t\tfreesync_capable && !ods_vrr_sink(connector, drm_edid));')
    text = function(text, 'amdgpu_dm_update_freesync_caps', caps)

    def config(s):
        s = once(s, '\tbool fs_vid_mode = false;', '\tbool fs_vid_mode = false;\n\tbool ods_target;')
        s = once(s, '\tnew_crtc_state->vrr_supported = new_con_state->freesync_capable &&', '''	ods_target = ods_vrr_sink(new_con_state->base.connector, aconnector->drm_edid);
	new_crtc_state->stream->ods_vrr_lab = ods_target &&
		ods_vrr_native(mode->clock, mode->hdisplay, mode->hsync_start,
			mode->hsync_end, mode->htotal, mode->hskew, mode->vdisplay,
			mode->vsync_start, mode->vsync_end, mode->vtotal, mode->vscan, mode->flags);
	if (ods_target && !new_crtc_state->stream->ods_vrr_lab) {
		new_crtc_state->vrr_supported = false;
		new_crtc_state->stream->ignore_msa_timing_param = false;
		new_crtc_state->stream->freesync_on_desktop = false;
		config.state = VRR_STATE_UNSUPPORTED;
		goto out;
	}
	if (new_crtc_state->stream->ods_vrr_lab) {
		new_crtc_state->stream->timing.min_refresh_in_uhz = 59000000;
		new_crtc_state->stream->timing.max_refresh_in_uhz = 60000000;
	}

	new_crtc_state->vrr_supported = new_con_state->freesync_capable &&''')
        s = once(s, 'fs_vid_mode = new_crtc_state->freesync_config.state == VRR_STATE_ACTIVE_FIXED;',
                 'fs_vid_mode = !ods_target &&\n'
                 '\t\t\tnew_crtc_state->freesync_config.state == VRR_STATE_ACTIVE_FIXED;')
        s = once(s, 'config.vsif_supported = true;\n\t\tconfig.btr = true;',
                 'config.vsif_supported = !ods_target;\n\t\tconfig.btr = !ods_target;')
        return once(s, 'if (new_con_state->freesync_on_desktop_capable)',
                    'if (!ods_target && new_con_state->freesync_on_desktop_capable)')
    text = function(text, 'get_freesync_config_for_crtc', config)
    output[name] = text

    name = BASE + 'modules/freesync/freesync.c'
    text = once(output[name], '#include "mod_freesync.h"',
                '#include "mod_freesync.h"\n#include "ods_vrr_guard.h"')
    def build(s):
        s = once(s, 'refresh_range >= MIN_REFRESH_RANGE)',
                 '(refresh_range >= MIN_REFRESH_RANGE ||\n'
                 '\t\t\t (stream->ods_vrr_lab && min_refresh_in_uhz == 59000000 &&\n'
                 '\t\t\t  max_refresh_in_uhz == 60000000)))')
        return once(s, '\tin_out_vrr->adjust.allow_otg_v_count_halt =', '''	if (stream->ods_vrr_lab) {
		in_out_vrr->adjust.v_total_mid = 0;
		in_out_vrr->adjust.v_total_mid_frame_num = 0;
	}
	in_out_vrr->adjust.allow_otg_v_count_halt =''')
    text = function(text, 'mod_freesync_build_vrr_params', build)
    def skip_fallback(s):
        return once(s, '\tcore_freesync = MOD_FREESYNC_TO_CORE(mod_freesync);', '''	/* Diagnostic keeps only the bounded variable window or native fixed mode.
	 * No LFC, fixed fallback, or flip-interval workaround may alter its totals.
	 * Missing a deadline therefore yields a max-duration refresh, not a new range.
	 */
	if (stream->ods_vrr_lab)
		return;

	core_freesync = MOD_FREESYNC_TO_CORE(mod_freesync);''')
    text = function(text, 'mod_freesync_handle_preflip', skip_fallback)
    text = function(text, 'mod_freesync_handle_v_update', skip_fallback)
    output[name] = text

    name = BASE + 'dc/core/dc.c'
    text = once(output[name], '#include "dc.h"', '#include "dc.h"\n#include "ods_vrr_guard.h"')
    def adjust(s):
        s = once(s, '\tint i;', '''	int i;
	bool ods_changed = stream->ods_vrr_lab &&
		(stream->adjust.v_total_min != adjust->v_total_min ||
		 stream->adjust.v_total_max != adjust->v_total_max ||
		 stream->adjust.timing_adjust_pending);

	if (stream->ods_vrr_lab &&
	    !ods_vrr_adjust_allowed(adjust->v_total_min, adjust->v_total_max,
		adjust->v_total_mid, adjust->v_total_mid_frame_num,
		adjust->allow_otg_v_count_halt)) {
		pr_err_ratelimited("ODS_VRR: REJECT totals min=%u max=%u mid=%u halt=%d\\n",
			adjust->v_total_min, adjust->v_total_max, adjust->v_total_mid,
			adjust->allow_otg_v_count_halt);
		return false;
	}''')
        s = once(s, '\t\t\tstream->adjust.timing_adjust_pending = true;',
                 '\t\t\tif (stream->ods_vrr_lab)\n'
                 '\t\t\t\tpr_info_ratelimited("ODS_VRR: DEFER timing update\\n");\n'
                 '\t\t\tstream->adjust.timing_adjust_pending = true;')
        s = once(s, '\t\t\tstream->adjust.timing_adjust_pending = false;',
                 '\t\t\tstream->adjust.timing_adjust_pending = false;\n'
                 '\t\t\tif (ods_changed)\n'
                 '\t\t\t\tpr_info("ODS_VRR: set_drr invoked min=%u max=%u\\n",\n'
                 '\t\t\t\t\tadjust->v_total_min, adjust->v_total_max);')
        return once(s, '\n\treturn false;\n}',
                    '\n\tif (stream->ods_vrr_lab)\n'
                    '\t\tpr_err_ratelimited("ODS_VRR: FAIL no timing-generator pipe\\n");\n'
                    '\treturn false;\n}')
    output[name] = function(text, 'dc_stream_adjust_vmin_vmax', adjust)
    return output


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--source-root', type=Path, required=True)
    p.add_argument('--patch-output', type=Path, required=True)
    p.add_argument('--apply', action='store_true', help='modify only the supplied local source tree')
    a = p.parse_args()
    entries = json.loads((ROOT / 'research/vrr-kernel-sources.json').read_text())['sources']
    hashes = {e['path']: e['sha256'] for e in entries}
    original = {}
    for name in FILES:
        data = (a.source_root / name).read_bytes()
        if hashlib.sha256(data).hexdigest() != hashes[name]:
            raise ValueError('source hash mismatch: ' + name)
        original[name] = data.decode()
    modified = transform(original)
    patch = ''.join(''.join(difflib.unified_diff(original.get(n, '').splitlines(True), s.splitlines(True),
                                               fromfile='a/' + n if n in original else '/dev/null',
                                               tofile='b/' + n)) for n, s in modified.items())
    a.patch_output.write_text(patch)
    if a.apply:
        for name, source in modified.items():
            (a.source_root / name).write_text(source)
    print('Prepared bounded diagnostic patch; no device contacted.')


if __name__ == '__main__':
    main()
