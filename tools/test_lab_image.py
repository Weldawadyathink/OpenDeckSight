#!/usr/bin/env python3
"""Run the USB-image smoke test locally, without a physical USB or Deck."""
import argparse
from pathlib import Path
import subprocess

root = Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--output-dir', type=Path, default=root / 'artifacts/usb-lab')
args = parser.parse_args()
out = args.output_dir.resolve()
if not (out / 'opendecksight-lab.img').is_file():
    parser.error('Build the image first')
for configured in ['0', '1']:
    subprocess.run(['docker', 'run', '--rm', '--platform', 'linux/amd64',
                '--mount', f'type=bind,src={root},dst=/src,readonly',
                '--mount', f'type=bind,src={out},dst=/out',
                '-e', 'ODS_TEST_WIFI=' + configured,
                'opendecksight-lab-builder', '-c', 'python3 -B /src/lab/usb/smoke_test.py'], check=True)
