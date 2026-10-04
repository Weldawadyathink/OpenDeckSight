# Full-image reconstruction target and current result

The target is a semantic patch program: starting with the Valve-provided BIOS
binary, apply understood DeckSight modifications and reproduce the released
image exactly. This is not permission to flash or modify the owner's device.

## Verified: entire 16 MiB BIOSIMG is byte-identical

`build-biosimg` now performs three named operations:

1. Generate the r04 EDID and bridge timing/initialization tables, patch the
   identified 8051 instructions, and regenerate EC checksums in both banks.
2. Update the version strings in both `$BVDT$` tables from `F7A0133` to
   `F7A0133 DS`, preserving table size and NUL termination.
3. Replace the raw PNG section under UEFI file GUID
   `F0DA323C-43A4-48DB-AEFE-CB314F7F5F6E` in both firmware halves, and let
   UEFIReplace 0.28.0 reconstruct the containing files and compressed volumes.

The only release-derived resource input is the identified 71,735-byte PNG
artwork (1920×1080); its SHA-256 is
`c6dc2f60bf6db651de288df56caeb3af8c57176faa2f4f27f6224cdce958b2b0`.
That is an image asset, not executable firmware or a binary-diff overlay.
Valve's original splash is a 17,550-byte 1280×720 PNG.

The enclosing GUID-defined sections use LZMA with a 16 MiB dictionary. Their
decompressed content grows from 19,624,064 to 19,677,312 bytes. UEFIReplace
handles FFS lengths/checksums, alignment/padding, enclosing volume size and
recompression. Its deterministic reconstruction produces exactly the original
release's compression and layout; no post-build correction bytes are applied.

Whole output SHA-256, identical to r04 BIOSIMG:

`5ef3e6e8ddf84fb36c6368156ef67adfd0a92ad362a460fc264c748d653b3549`

This accounts for every changed BIOSIMG byte structurally. It does **not** mean
every vendor-specific panel command is understood; see [panel-init.md](panel-init.md).

## Not yet reconstructed: signed `.fd` container

The `.fd` also includes unchanged executable code, nested IFLASH records,
header/extent/checksum metadata, a BIOSCER signature, and two PE signatures.
All three cryptographic layers have now been checked offline:

- `BIOSCER` is a 256-byte RSA PKCS#1 v1.5 signature. Recovering its DigestInfo
  with the included QA public key gives SHA-256 of the complete r04 BIOSIMG.
- The embedded DRV_IMG has a valid Authenticode signature with SHA-256 digest
  `e501c292c68cdb00db13312457bccadab89049795ba26a69396d1c0c68363908`.
- The outer PE has a valid Authenticode signature with SHA-256 digest
  `0631718dc53a56cb62cbc3892127399f28255819651f037467ab3fece701c58e`.

The verification explicitly trusts the certificate extracted from the artifact
as an anchor. It establishes signature mathematics and matching content, **not
Valve trust or the firmware updater's acceptance policy**. No signing timestamp
is present. The QA private key has not been provided or recovered.

A faithfully reconstructed identical input could reuse its existing valid
signatures, but that would be signature reuse, not an open signer for new
firmware. The project has not implemented that as a shortcut. IFLASH extent
fields and nested PE repacking must be explained before claiming a full `.fd`
reconstruction. Unknown header bytes will not be patched merely to match hashes.

## Acceptance criteria remaining

- Explain the proprietary commands, extra brightness parameters and unusual
  tear/compression sequence, beyond correctly decoding their packets.
- Identify physical EC-copy selection. The table loader, byte ordering,
  display-selection branch and delay arithmetic are now traced offline in
  [ec-interpreter.md](ec-interpreter.md); live activation remains unverified.
- Explain and regenerate nested IFLASH/PE metadata, including signatures or an
  explicit, verified signature-reuse boundary for exact historical reproduction.
- Test functionality only after the owner approves concrete device operations.

Exact historical reproduction and the ability to sign arbitrary future builds
are separate capabilities. The latter needs an appropriate signing authority
or a different update mechanism, neither of which is silently assumed here.
