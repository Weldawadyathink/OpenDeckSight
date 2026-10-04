"""Recovery menu never needs rewriting when a research bundle is installed."""
from pathlib import Path
import sys

sys.path.insert(0, '/src')
from opendecksight.lab_update import BASE_ARGS, env_bytes

esp = Path('/work/esp')
config = """set timeout=8
set default=baseline
if [ -f /boot/ods.env ]; then
    load_env --file /boot/ods.env ods_default
    if [ "$ods_default" = "research-a" -a -f /boot/slots/research-a/entry.cfg ]; then
        set default=research-a
    fi
    if [ "$ods_default" = "research-b" -a -f /boot/slots/research-b/entry.cfg ]; then
        set default=research-b
    fi
fi
"""
config += ("menuentry 'OpenDeckSight recovery baseline' --id baseline {\n"
           f"    linux /boot/vmlinuz {BASE_ARGS} ods.slot=baseline\n"
           "    initrd /boot/initramfs.img\n}\n")
for slot in ['research-a', 'research-b']:
    config += f'if [ -f /boot/slots/{slot}/entry.cfg ]; then\n    source /boot/slots/{slot}/entry.cfg\nfi\n'
(esp / 'boot/grub/grub.cfg').write_text(config)
(esp / 'boot/ods.env').write_bytes(env_bytes('baseline'))
(esp / 'ODS-UPDATE-V1').write_text('Explicit USB-only research updates; baseline is preserved.\n')
