# Reproduce the investigation

All commands below are offline or download/read data. None executes a firmware
payload or installer, accesses device MMIO, or flashes hardware.

## Fetch, inspect and compare

```sh
python3 tools/fetch_artifacts.py
python3 tools/reproduce.py > artifacts/ec-reproduction.json
python3 -m opendecksight inspect artifacts/extracted/r04/bios/F7A0133_DeckSight_signed_r04.fd
python3 tools/inspect_container.py artifacts/extracted/stock/usr/share/jupiter_bios/F7A0133_sign.fd
python3 tools/inspect_container.py artifacts/extracted/r04/bios/F7A0133_DeckSight_signed_r04.fd
```

The fetcher verifies exact size and SHA-256 from `research/artifacts.json`, and
extracts only the explicitly named BIOS and brightness data files. It refuses
to replace an existing mismatched file. It needs a `tar` with zstd support for
the Valve package. The built-in macOS `tar` worked on the research machine.
`inspect_container.py` also needs `openssl`; it extracts certificate metadata,
not cryptographic signature verification.

`reproduce.py` rejects unknown hashes, constructs r04 EC regions from the stock
BIOS, compares both entire 128 KiB regions, and checks that bytes outside the EC
regions have not changed. It emits a report and returns nonzero on mismatch.
The checked-in reference is [ec-reproduction.json](../research/reports/ec-reproduction.json).

## Compressed UEFI comparison

For the exact reference method, download the pinned macOS UEFIExtract A75:

```sh
python3 tools/fetch_artifacts.py --include-tools
mkdir -p .tools/uefiextract artifacts/uefi
unzip -o artifacts/downloads/UEFIExtract-A75.zip -d .tools/uefiextract
python3 -m opendecksight extract artifacts/extracted/stock/usr/share/jupiter_bios/F7A0133_sign.fd artifacts/uefi/stock.bin
python3 -m opendecksight extract artifacts/extracted/r04/bios/F7A0133_DeckSight_signed_r04.fd artifacts/uefi/r04.bin
.tools/uefiextract/UEFIExtract artifacts/uefi/stock.bin all
.tools/uefiextract/UEFIExtract artifacts/uefi/r04.bin all
python3 tools/compare_uefi.py artifacts/uefi/stock.bin.dump artifacts/uefi/r04.bin.dump
```

The `extract` command refuses to overwrite existing outputs. On other hosts,
obtain/build UEFIExtract from LongSoft's source; tool-version-dependent directory
names may differ. Retain parser warnings. The checked-in report records 2,454
identical leaves, 9 changed leaves and 2 added padding leaves. Changed leaves
are the two splash sections, padding and free space. That is parser coverage,
not a proof about every possible embedded executable.

## Tests

```sh
python3 -m unittest discover -s tests -v
lua tools/check_gamescope.lua
python3 tools/reproduce.py > artifacts/verified-reproduction.json
```

Unit tests cover untrusted file bounds, EDID integrity, BIOS hash rejection,
brightness scaling, mailbox write order, busy/timeout behavior and retries after
failed resume refreshes. The Lua fixture validates registration and 41 timing
requests without pretending to be a real Gamescope runtime. The separate
artifact check establishes byte-for-byte correspondence with the pinned release.
