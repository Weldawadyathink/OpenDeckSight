#!/bin/bash
set -euo pipefail
export PYTHONDONTWRITEBYTECODE=1
test "$(gcc -dumpfullversion)" = 16.2.1
mkdir -p /work/devel /work/linux /out
cd /work/devel
rpm2cpio /inputs/kernel-devel.rpm | cpio -idm --quiet
# Python extraction also works where GNU tar's newer syscalls are unavailable.
python3 - <<'PY'
import tarfile
from pathlib import Path
with tarfile.open('/inputs/linux-151eb3a.tar.gz') as archive:
    members=[]
    for item in archive:
        parts=Path(item.name).parts
        if len(parts)>1:
            item.name=str(Path(*parts[1:])); members.append(item)
    archive.extractall('/work/linux',members=members,filter='data')
PY
python3 -B /src/tools/prepare_vrr_patch.py --source-root /work/linux --patch-output /out/applied.patch --apply
KBUILD=/work/devel/usr/src/kernels/7.2.3-ogc3.1.fc44.x86_64
# AMD trace headers use paths relative to the prepared kernel's include tree.
mv "$KBUILD/drivers/gpu/drm/amd" /work/devel/amd-metadata
ln -s /work/linux/drivers/gpu/drm/amd "$KBUILD/drivers/gpu/drm/amd"
make -C "$KBUILD" M=/work/linux/drivers/gpu/drm/amd/amdgpu -j6 modules
strip --strip-debug -o /out/amdgpu.ko /work/linux/drivers/gpu/drm/amd/amdgpu/amdgpu.ko
cc -std=c11 -O2 -Wall -Wextra -Werror $(pkg-config --cflags libdrm) \
    /src/lab/vrr/visual_ab.c -o /out/ods-visual-ab $(pkg-config --libs libdrm)
cc -std=c11 -O1 -g -Wall -Wextra -Werror -fsanitize=address,undefined \
    $(pkg-config --cflags libdrm) /src/lab/vrr/visual_ab.c \
    -o /work/preview-checked $(pkg-config --libs libdrm)
/work/preview-checked --preview > /out/preview.ppm
modinfo -F vermagic /out/amdgpu.ko > /out/vermagic.txt
gcc --version > /out/compiler.txt
rpm -qa | sort > /out/build-packages.txt
echo 'Driver and visual stimulus built; no physical device contacted.'
