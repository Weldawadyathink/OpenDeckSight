"""Semantic reconstruction of the whole r04 BIOSIMG, not the signed container."""

from pathlib import Path
import subprocess
import tempfile

from .firmware import R04_SHA256, build_r04_ec_reproduction, sha256

SPLASH_GUID = "F0DA323C-43A4-48DB-AEFE-CB314F7F5F6E"
SPLASH_SHA256 = "c6dc2f60bf6db651de288df56caeb3af8c57176faa2f4f27f6224cdce958b2b0"


def patch_version(image):
    output = bytearray(image)
    for table in (0x6A8000, 0xEA8000):
        if output[table:table + 6] != b"$BVDT$" or output[table + 14:table + 24] != b"F7A0133\0\0\0":
            raise ValueError("unexpected BIOS version data table")
        output[table + 14:table + 24] = b"F7A0133 DS"
        # Fixed-width overwrite; the following original NUL remains terminator.
    return bytes(output)


def build_biosimg(stock, splash, uefireplace):
    """Generate EC/tables, update BVDT and rebuild the splash FFS resource.

    The only target-derived input is the identified artwork resource. No target
    firmware regions or binary deltas are fed into this reconstruction.
    """
    if sha256(splash) != SPLASH_SHA256:
        raise ValueError("unexpected r04 PNG resource hash")
    engine = Path(uefireplace).resolve(strict=True)
    image = patch_version(build_r04_ec_reproduction(stock))
    with tempfile.TemporaryDirectory(prefix="opendecksight-build-") as directory:
        root = Path(directory)
        (root / "input.bin").write_bytes(image)
        (root / "splash.png").write_bytes(splash)
        process = subprocess.run([str(engine), str(root / "input.bin"), SPLASH_GUID, "19",
                                  str(root / "splash.png"), "-o", str(root / "output.bin"), "-all"],
                                 capture_output=True, text=True, timeout=120)
        if process.returncode:
            raise RuntimeError(f"UEFIReplace failed: {process.stdout} {process.stderr}")
        result = (root / "output.bin").read_bytes()
        if sha256(result) != R04_SHA256:
            raise ValueError("reconstructed BIOSIMG is not byte-identical; check rebuild-engine version")
        return result, {"engine_sha256": sha256(engine.read_bytes()),
                        "engine_log": process.stdout + process.stderr}
