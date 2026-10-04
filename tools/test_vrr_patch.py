#!/usr/bin/env python3
"""Exercise the actual patched timing functions locally with UBSan; no device I/O."""
import hashlib
import json
from pathlib import Path
import re
import subprocess
from prepare_vrr_patch import ROOT, FILES, BASE, transform
from test_vrr_kernel import FUNCTIONS, extract_function, SOURCE, HEADER

entries = json.loads((ROOT/'research/vrr-kernel-sources.json').read_text())['sources']
hashes = {e['path']:e['sha256'] for e in entries}
original = {}
for name in [*FILES, HEADER]:
    data=(ROOT/'artifacts/vrr/kernel-source'/name).read_bytes()
    assert hashlib.sha256(data).hexdigest()==hashes[name], name
    original[name]=data.decode()
modified=transform(original)
source=modified[SOURCE]; header=original[HEADER]
stubs=(ROOT/'tests/fixtures/vrr_kernel_stubs.h').read_text()
stubs=stubs.replace('struct core_freesync; /* Selected arithmetic never dereferences this pointer. */',
                    'struct core_freesync { struct dc *dc; };')
stubs=stubs.replace('uint32_t v_total_min, v_total_max;',
                    'uint32_t v_total_min, v_total_max, v_total_mid, v_total_mid_frame_num;')
stubs=stubs.replace('struct dc {', 'struct dc {\n    struct dc_context *ctx;')
stubs=stubs.replace('struct dc_stream_state {', 'struct dc_stream_state {\n    bool ods_vrr_lab;')
definitions=header[header.index('// Access structures'):header.index('struct mod_freesync *mod_freesync_create')]
extra='''
#include <string.h>
struct dc_plane_state { struct { unsigned prev_update_time_in_us; } time; };
static unsigned stub_calls;
static void apply_below_the_range(struct core_freesync *a, const struct dc_stream_state *b, unsigned c, struct mod_vrr_params *d) { (void)a;(void)b;(void)c;(void)d;stub_calls++; }
static void determine_flip_interval_workaround_req(struct mod_vrr_params *a, unsigned b) { (void)a;(void)b;stub_calls++; }
static unsigned long long dm_get_timestamp(struct dc_context *a) { (void)a;stub_calls++;return 1000000; }
static unsigned long long dm_get_elapse_time_in_ns(struct dc_context *a, unsigned long long b, unsigned long long c) { (void)a;(void)c;stub_calls++;return b; }
static unsigned calc_v_total_from_duration(const struct dc_stream_state *a, struct mod_vrr_params *b, unsigned c) { (void)a;(void)b;(void)c;stub_calls++;return 1956; }
static void update_v_total_for_static_ramp(struct core_freesync *a, const struct dc_stream_state *b, struct mod_vrr_params *c) { (void)a;(void)b;(void)c;stub_calls++; }
'''
constants='\n'.join(re.findall(r'^#define (?:MIN_REFRESH_RANGE|BTR_MAX_MARGIN|FIXED_REFRESH_\w+)[^\n]*',source,re.M))
functions='\n\n'.join(extract_function(source,n) for n in [*FUNCTIONS,'mod_freesync_handle_preflip','mod_freesync_handle_v_update'])
unit=source[:source.index('#include')]+header[:header.index('#ifndef')]+stubs+definitions+extra+constants+'\n'+modified[BASE+'dc/ods_vrr_guard.h']+'\n'+functions+'\n'+(ROOT/'tests/fixtures/vrr_patch_cases.c').read_text()
build=ROOT/'.tools/vrr-patch-tests';build.mkdir(exist_ok=True)
(build/'test.c').write_text(unit)
subprocess.run(['cc','-std=c11','-Wall','-Wextra','-Werror','-fsanitize=undefined','-fno-sanitize-recover=all',str(build/'test.c'),'-o',str(build/'test')],check=True)
subprocess.run([str(build/'test')],check=True)
