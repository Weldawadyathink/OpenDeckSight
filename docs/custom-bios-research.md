# Custom Steam Deck BIOS projects and signing paths

Research snapshot: 2026-10-03. Online sources were read as data; no third-party
installer, bypass, flasher or firmware executable was run. Source revisions,
download hashes and retrieval failures are in the
[source manifest](../research/reports/custom-bios-sources.json). Full downloaded
sources remain in ignored `artifacts/online-signing-research/`.

Custom Steam Deck firmware exists. The evidence supports several different
installation mechanisms, not a general rule that every self-signed BIOS is
accepted. The strongest new local finding is that Valve's stock F7A0133 already
contains the exact QA certificate used to verify DeckSight r04.

## Other projects

| Project | What the primary source establishes | Signing implication |
| --- | --- | --- |
| [DeckHD BiosMaker](https://github.com/DeckHD/BiosMaker/tree/81c9f6863c9512fbbdcbb5c7a299badf1e54a328) | Public code patches the raw BIOS for the replacement panel. Its README explicitly leaves creation of a valid `.fd` to the user or suggests an external programmer. | An open patcher is not necessarily an open signing pipeline. DeckHD's distributed `.fd` files are a separate deliverable. |
| [SD-APCB-Tool](https://github.com/djanice1980/SD-APCB-Tool/tree/ac3e93aedc86acf3c7902ea904addb328e251a18) | RAM/display modification tool; its README describes self-signing combined with a SecureFlash certificate-injection vulnerability, and calls end-to-end flashing experimental. | The proposed route changes the trusted certificate; it does not establish acceptance of arbitrary keys under the original policy. |
| [sdbios-rebuild](https://github.com/syberphunk/sdbios-rebuild/tree/63bae8e933053f03a4f09e05f3f4ba6936962f54) | A public repacker/signing script plus an NVRAM certificate setter. | A candidate bypass workflow with important unresolved correctness issues below. |
| [Smokeless UMAF](https://github.com/DavidS95/Smokeless_UMAF/blob/c003b126cab6e29b1d72d061d59cea9e721a6910/README.md) | Loads a replacement firmware settings interface from USB without flashing a new BIOS image. | Access to hidden settings is not evidence about accepting custom firmware signatures. |

Christopher Stanton also announced prebuilt F7A0133/F7G0114 modifications on
July 27, 2026, including DeckHD, DeckSight and RAM variants, with ordinary
`h2offt` installation instructions. His [indexed homepage](https://www.stanto.com/)
exposes the article; its [permalink](https://www.stanto.com/steam-deck/unlocking-the-steam-deck-bios-secure-boot-options-higher-tdp-and-amd-cbs-pbs-for-ram-tweaking-with-a-flash/)
returned HTTP 500 during this investigation. This is evidence of another
author-published custom release, not verification of its binaries, signing key
or production process. No such release was downloaded or tested here.

## Reported tests and conflicting claims

The SD-APCB [changelog](https://github.com/djanice1980/SD-APCB-Tool/blob/ac3e93aedc86acf3c7902ea904addb328e251a18/CHANGELOG.md)
retracts an earlier claim that arbitrary self-signed certificates work. It
reports an OLED experiment in which stock firmware passed, while an unknown
signer and a QA certificate paired with the wrong private key failed. This is
author-reported evidence on another model/version, not a reproduced LCD test.
Its assertion that DeckHD possesses a particular private-key file does not
establish who operates that key.

Treat the same document's format analysis cautiously: its descriptions of
IFLASH flag bytes and an unknown BIOSCER hash conflict with our independently
verified [length fields](container-reconstruction.md) and
[RSA signature](signing.md). A useful test report does not make every inferred
implementation detail correct.

The [DeckHD issue discussion](https://github.com/DeckHD/BiosMaker/issues/4)
contains an initial success claim followed by a signature-related failure
report and acknowledgement. Later posts report successful certificate-bypass
flashes, while another disputes the workflow's completeness; a further report
says the flash did not produce a working display. These are conflicting
observations, not a reproducible acceptance test with verified before/after
flash contents.

## What the certificate-injection vulnerability does

Insyde's [SA-2025002](https://www.insyde.com/security-pledge/sa-2025002/), published
June 10, 2025, confirms CVE-2025-4275: improper validation of UEFI variable
attributes can allow an untrusted certificate to be used. Fixed Insyde firmware
versions are listed; these are not Linux kernel version numbers.

The discoverer's [Hydroph0bia part 1](https://coderush.me/hydroph0bia-part1/)
explains that firmware passes an update certificate through
`SecureFlashCertData`, with `SecureFlashSetupMode` as a trigger. Vulnerable code
can consume substituted variables and accept code signed by the substituted
key. Signature mathematics still applies; the source of trust has changed.

[Part 2](https://coderush.me/hydroph0bia-part2/) separates launching signed UEFI
code from completing a firmware update: the investigated update path deletes
ordinary certificate variables, requiring additional early-driver and variable
protection work. [Part 3](https://coderush.me/hydroph0bia-part3/) examines fixes
that remove shadowed variables and restrict later writes. Neither proves the
patch status or exact behavior of the pinned Steam Deck firmware.

Static review of the pinned sdbios-rebuild
[signer](https://github.com/syberphunk/sdbios-rebuild/blob/63bae8e933053f03a4f09e05f3f4ba6936962f54/build-fd-bios/sign_bios_preserve_header.py)
shows that each run generates a fresh key/certificate, preserves a supplied
metadata slice and constructs one new outer signature. It neither exports that
certificate as an ESL nor regenerates BIOSCER over the changed BIOSIMG. Its
[setter](https://github.com/syberphunk/sdbios-rebuild/blob/63bae8e933053f03a4f09e05f3f4ba6936962f54/bypass-cert-check/set_nvram_variables.sh)
instead reads a separate prebuilt ESL. Therefore the documented pairing does
not establish that the injected certificate matches the fresh signing key, or
that every signature check succeeds. This is a source-level finding, not a
live failure reproduction. The scripts are not adopted as an installation path.

## Independently verified: the QA certificate is in stock Valve firmware

Input: the already pinned stock F7A0133 BIOSIMG, SHA-256
`b77eb694c5af0d125bbca0a018ee18a2ad54409211b454e38f9bb545a62f7f64`.

Both firmware halves contain a raw certificate resource under FFS GUID
`9F4F421C-CE02-42C1-92FB-CF26C52B9526`. Its 1,636-byte body consists of two
bounded [EFI signature lists](https://uefi.org/specs/UEFI/2.10/32_Secure_Boot_and_Driver_Signing.html#signature-database),
containing:

| Certificate | DER bytes | Offset in raw section | SHA-256 |
| --- | --- | --- | --- |
| `CN=QA Certificate.` | 785 | `0x2c` | `f14700fcca6aed9c5d33f356e3f8a3413beda76dacaa1324b00e3d0a05446b18` |
| `CN=Jupiter` | 763 | `0x369` | `eb2abdf3e150dba4b69987ffe9f2b5b947889ffceaf2bcaf8f252e44ef9cad77` |

The QA DER bytes match the certificate already verified against all three
DeckSight r04 signatures. The same two certificates occur in the stock image's
factory-default `db` records alongside Microsoft certificates. These are
defaults in a public firmware file, not a reading of any device's active `db`.
The certificate resource's GUID also occurs in both copies of `BdsDxe` and
`SecureFlashDxe`; these byte occurrences are not yet a traced execution path.

The deterministic [certificate inventory](../research/reports/stock-certificate-inventory.json)
records paths, hashes, list boundaries and module GUID offsets without
including the extracted payloads. Reproduce it after the UEFI extraction in
[reproduce.md](reproduce.md):

```sh
python3 tools/inspect_stock_certificates.py artifacts/uefi/stock.bin.dump > artifacts/stock-certificate-inventory.json
```

**Inference:** DeckSight's use of a key already represented in Valve's firmware
is a much stronger explanation than unrestricted acceptance of self-signed
images. The exact verification call path, active trust state and identity of
the person/service holding the QA private key remain unresolved.

## Effect on the open implementation

Exact r04 reproduction continues to reuse the original signatures. New firmware
content would need access to an accepted signer, a validated way to authorize a
new key, or a separately validated programming route. Public bypass research is
a concrete lead, not proof that the signing obstacle is already solved.

Next offline work can trace the certificate-resource consumers and compare
Valve's variable-handling code with the published vulnerability/fix analysis.
No live certificate substitution, flash attempt or device modification is
authorized by this research record.
