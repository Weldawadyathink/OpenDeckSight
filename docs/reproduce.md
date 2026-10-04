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

## Build the complete r04 BIOSIMG

After the UEFI extraction above, extract the identified artwork and use the
hash-pinned reconstruction engine (the packaged 0.28.0 macOS tool is x86-64):

```sh
python3 tools/fetch_artifacts.py --include-tools
mkdir -p .tools/uefireplace
unzip -o artifacts/downloads/UEFIReplace-0.28.0-mac.zip -d .tools/uefireplace
python3 tools/extract_splash.py artifacts/uefi/r04.bin.dump artifacts/r04-splash.png
python3 -m opendecksight build-biosimg artifacts/uefi/stock.bin artifacts/r04-rebuilt.bin --splash artifacts/r04-splash.png --uefireplace .tools/uefireplace/UEFIReplace
```

It checks the stock input, artwork resource and entire output hash. No copy of
the reference BIOSIMG is used by the builder. The output matches all 16 MiB of
r04, but is not a signed `.fd` updater package. See
[full reconstruction](full-reconstruction.md) for semantic limitations.

## Verify cryptographic layers

Build the pinned osslsigncode source locally, then check the existing release:

```sh
tar -xzf artifacts/downloads/osslsigncode-2.14.tar.gz -C .tools
cmake -S .tools/osslsigncode-2.14 -B .tools/osslsigncode-build -DCMAKE_BUILD_TYPE=Release
cmake --build .tools/osslsigncode-build
python3 tools/verify_signatures.py artifacts/extracted/r04/bios/F7A0133_DeckSight_signed_r04.fd --osslsigncode .tools/osslsigncode-build/osslsigncode
```

The research host additionally set `-DOPENSSL_ROOT_DIR=/opt/homebrew/opt/openssl@3`
for CMake. The verifier explicitly anchors trust to the certificate extracted
from the artifact; it does not establish Valve trust or updater acceptance.

## Read-only SSH collection

When authorized, stream the collector without installing or writing remote files:

```sh
python3 tools/collect_ssh.py user@host --output artifacts/device-report.json
```

It uses existing trusted SSH host keys, batch authentication and `python3 -B -`.
The output is written locally only. Keep raw device reports out of Git.

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
