-- Load the unmodified upstream profile against a small API fixture.
-- This checks its registration and timing requests, not real Gamescope behavior.
gamescope = {
    config = { known_displays = {} },
    eotf = { gamma22 = "gamma22" },
    modegen = {
        set_resolution = function(mode, width, height)
            mode.width, mode.height = width, height
        end,
        set_h_timings = function(mode, fp, sync, bp)
            mode.htotal = mode.width + fp + sync + bp
        end,
        set_v_timings = function(mode, fp, sync, bp)
            mode.vtotal = mode.height + fp + sync + bp
        end,
        calc_max_clock = function(mode, refresh)
            return mode.htotal * mode.vtotal * refresh / 1000
        end,
        calc_vrefresh = function(mode)
            return mode.clock * 1000 / (mode.htotal * mode.vtotal)
        end,
    },
}
debug = function(message) end
dofile(arg[1] or "third_party/gamescope/DeckSight.lua")
local profile = gamescope.config.known_displays.decksight
assert(profile.matches({vendor = "DSO", product = 0x5001}) == 5000)
assert(profile.matches({vendor = "VLV", product = 0x5001}) == -1)
assert(profile.matches({vendor = "DSO", product = 0x5002}) == -1)
assert(#profile.dynamic_refresh_rates == 41)
for index, refresh in ipairs(profile.dynamic_refresh_rates) do
    assert(refresh == 39 + index)
    local mode = profile.dynamic_modegen({}, refresh)
    assert(mode.width == 1080 and mode.height == 1920)
    assert(mode.htotal == 1240 and mode.vtotal == 1998)
    assert(math.abs(mode.vrefresh - refresh) < 0.00001)
end
assert(profile.hdr.supported and profile.hdr.force_enabled)
print("Gamescope profile fixture passed: identity matching and 41 timing requests")
