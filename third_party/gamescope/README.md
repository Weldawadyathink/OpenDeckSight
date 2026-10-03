# Existing open Gamescope integration

`DeckSight.lua` is copied **without changes** from ShadeTechnik/DeckSight-Public
at commit `2baab5bb4366e419bfad68beda5910a8fd2e8e32`:

https://github.com/ShadeTechnik/DeckSight-Public/blob/2baab5bb4366e419bfad68beda5910a8fd2e8e32/Gamescope/DeckSight.lua

The source repository supplies this component under GPL version 2; a copy is
at [licenses/GPL-2.0.txt](../../licenses/GPL-2.0.txt). It is not covered by
OpenDeckSight's MIT license. Attribution: ShadeTechnik and upstream contributors.
The r04 release's copy is identical. SHA-256:
`f47e4ee9dec2533e86fe784b339bff9bcbd0c2af38c9f157ffd04fb33b879bd7`.

There is already source for this component, so it does not need reconstruction.
It registers the panel, measured chromaticities, dynamic timings and HDR settings.
It does not implement hardware brightness or modify firmware.

Gamescope loads user scripts from `~/.config/gamescope/scripts/` in the supported
versions described by upstream. After reviewing the existing configuration,
place this file at `~/.config/gamescope/scripts/DeckSight.lua`. Keep only one
DeckSight registration script. Bazzite's active Gamescope version and profile
loading still need checking on the actual device.

The script advertises 40–80 Hz. That advertisement is not a guarantee of stable
panel initialization at every rate. See [BIOS findings](../../docs/bios.md).
