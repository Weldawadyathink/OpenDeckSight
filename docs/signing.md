# Signing, signer identity and installation

The byte-identical r04 `.fd` produced by `build-fd` needs no new signing step.
It contains the release's original signatures over the same reconstructed
content. A different BIOS payload is a separate case: its
existing signatures would no longer match, and the accepted signing/update
mechanism still needs investigation.

## What a signature establishes

A signer calculates a cryptographic digest of the covered content and signs
it with a private key. A verifier uses the corresponding public key to check
the signature against a freshly calculated digest. The public key is carried
in a certificate; it can verify signatures but cannot create new ones. Firmware
contents remain readable: signing does not encrypt the BIOS.

The r04 file has three layers, all checked offline:

| Layer | Signed content |
| --- | --- |
| BIOSCER | SHA-256 of the complete 16 MiB BIOSIMG, signed with RSA PKCS#1 v1.5 |
| Inner Authenticode | Covered portions of the embedded driver, including its firmware records |
| Outer Authenticode | Covered portions of the outer update container, including the inner image |

Authenticode omits designated signature/checksum metadata from its hash; it is
not a naive hash of the entire signed file. See
[Microsoft's description](https://learn.microsoft.com/en-us/windows/win32/debug/pe-format#appendix-a-calculating-authenticode-pe-image-hash).
Changing BIOSIMG content invalidates the old BIOSCER and both enclosing PE
signatures. Regenerating additive EC or PE checksums cannot repair that.

## What we know about the signer

The Valve-supplied F7A0133 file carries a certificate named `CN=Jupiter`.
DeckSight r04 instead carries `CN=QA Certificate.` as both subject and issuer.
Its public key verifies all three r04 signatures. The QA certificate's own
self-signature was also checked successfully with OpenSSL's `-check_ss_sig`.

QA certificate SHA-256 fingerprint:

`F14700FCCA6AED9C5D33F356E3F8A3413BEDA76DACAA1324B00E3D0A05446B18`

The file proves that its signatures were generated using the corresponding
private key, directly or through a signing service. It does **not** identify
the person or organization operating that key. We have not established whether
the developer signs locally, uses a partner or uses a signing service. The
generic QA label is not proof of ownership, Valve endorsement, Insyde ownership
or a publicly available signing key. No private key has been recovered.

Subsequent offline inspection found this **exact QA certificate already present
in Valve's stock F7A0133**, beside `CN=Jupiter`, in a firmware certificate
resource and factory-default `db` records. This supports a specific existing
trust relationship; it does not identify the private-key operator. See the
[custom BIOS research](custom-bios-research.md) for the measured locations,
other projects' signing methods and evidence limits.

## Valid signature versus accepted signer

There are two independent checks:

1. Does this signature match the content and public key?
2. Does this update path authorize that key/content for this device?

Our signature checks establish the first. They explicitly use the certificate
inside the artifact as a verification anchor, rather than proving it belongs
to an independently trusted authority. The Deck's updater/firmware policy must
be analyzed separately; the presence of an embedded self-signed certificate
does not mean arbitrary self-signed firmware will be accepted.

Public projects describe ways to substitute a new trusted certificate on
vulnerable Insyde firmware. That changes the trust configuration; it is not
ordinary acceptance of any signer. These methods have not been validated here,
and public implementations and success reports require careful review.

The [public installer](https://github.com/ShadeTechnik/DeckSight-Public/blob/2baab5bb4366e419bfad68beda5910a8fd2e8e32/install.sh)
passes its existing `.fd` to the system's `h2offt`. It has no end-user signing
step. Enforcement of signature layers and trust anchors by the update path
has not been established by a live test.

## Consequences for OpenDeckSight

| Output | New signing step needed? |
| --- | --- |
| Original released r04 `.fd` | No; signatures are already included |
| Byte-identical reconstructed r04 `.fd` | No; the original signatures still match |
| BIOS with a changed timing, panel command, logo or Valve baseline | Existing signatures do not suffice; an accepted signing method or another verified update path is needed |

Given identical input bytes and the same update conditions, the original r04
file and our reconstructed file are indistinguishable to signature checking.
That establishes no additional signing obstacle for the reconstruction; it is
not a promise that an untested flash will succeed on a device.

For new content, generating a private/public key pair would make
signing mathematically possible, but would not automatically authorize that key
to update the firmware. Determining an accepted method is the remaining work.
No installer, updater, trust-store change or firmware write was performed to
answer these questions.
