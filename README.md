# OpenDeckSight

Open implementation and reproducible reverse engineering of the software needed
for a DeckSight replacement display in an LCD Steam Deck.

**Status: the complete 16 MiB r04 BIOSIMG now reproduces byte-for-byte** from
Valve F7A0133 using generated EC changes, a version-string update and a structural
UEFI logo replacement. The signed `.fd` wrapper is not yet rebuilt, and several
vendor-specific panel command meanings remain unresolved. A matching hash is
not being presented as complete reverse engineering. See the
[full reconstruction record](docs/full-reconstruction.md).

The underlying Valve/Insyde/AMD firmware remains binary-only. The owner's Deck
has been inspected read-only over SSH; no runtime brightness writes, service
changes or firmware flashing have occurred. Potentially dangerous device actions
require explicit human confirmation.

## Findings and evidence

- [Research index](docs/README.md)
- [BIOS changes and exact offsets](docs/bios.md)
- [Decoded panel initialization and unresolved semantics](docs/panel-init.md)
- [EC instruction traces and delay-counter findings](docs/ec-interpreter.md)
- [Brightness protocol](docs/brightness.md)
- [Artifact provenance](research/artifacts.json)
- [Hardware validation plan](docs/hardware-validation.md)
- [Reproduction commands](docs/reproduce.md)
- [Existing open Gamescope integration](third_party/gamescope/README.md)

## Offline tools

Python 3.10 or newer; no third-party Python packages are needed. Run from this
repository (or install the CLI with `python3 -m pip install .`).

```sh
python3 -m opendecksight inspect path/to/F7A0133_DeckSight_signed_r04.fd
python3 -m opendecksight extract path/to/F7A0133_sign.fd artifacts/stock.bin
python3 -m opendecksight diff artifacts/stock.bin path/to/DeckSight.fd
python3 -m opendecksight edid ../DeckSight-Public/edid/decksight_edid.bin
python3 -m opendecksight build-ec artifacts/stock.bin artifacts/r04-ec-research.bin
python3 -m unittest discover -s tests -v
```

## Brightness replacement and device inventory

```sh
# Works on this computer; prints packets and performs no MMIO.
python3 -m opendecksight brightness --raw 32768 --max 65535

# Run these from a checkout on the Steam Deck, without sudo.
python3 -m opendecksight collect deck-report.json
python3 -m opendecksight brightness --watch
```

The open brightness implementation includes the recovered EC transport,
backlight discovery, retry-on-failure and suspend-gap reapplication. Hardware
access requires `--apply-mmio`, root, Linux x86-64, Valve/Jupiter/F7A DMI and a
valid DSO:5001 EDID. It refuses to run alongside the proprietary brightness
process. This is implemented but **has not been hardware tested**. See the
[runtime instructions](docs/brightness.md#running-the-replacement).

`build-ec` accepts only the exact recorded stock BIOSIMG hash. Its output retains
the stock UEFI modules and logo and reproduces the released EC changes, including
the unexplained second-bank byte-order anomaly. It is an **unsigned research
image**, not an installable `.fd` release. There is no flashing command.

`build-biosimg` additionally updates the version strings and rebuilds the UEFI
splash resource. It verifies that the complete output matches r04's BIOSIMG.
The resource extraction and build commands are in [reproduce.md](docs/reproduce.md).

Downloaded firmware, extracted modules and local analysis tools are ignored by
Git. The repository contains implementation source, measured interface data,
provenance and reports; it does not vendor the complete proprietary firmware.

## Scope

Implement the DeckSight-specific software openly, explain every known firmware
change, and validate the result on the owner's LCD Steam Deck running Bazzite.
Replacing all of the Steam Deck's proprietary platform and peripheral firmware
would be a separate, much larger effort. Touchscreen firmware source and a public
firmware payload have not been located in the supplied artifacts.

The repository's MIT license covers original OpenDeckSight code. Upstream
artifacts retain their own licenses; see [provenance](docs/provenance.md).
