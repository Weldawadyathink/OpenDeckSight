#!/usr/bin/env python3
"""Stream the bounded TEST_ONLY VRR diagnostic; no remote files or real commit."""

import argparse
import json
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]


def program():
    lines = ['import sys, types, json', 'sys.dont_write_bytecode = True',
             "package = types.ModuleType('opendecksight'); package.__path__ = []",
             "sys.modules['opendecksight'] = package"]
    for name in ('dpcd', 'vrr', 'vrr_dry_run'):
        full = 'opendecksight.' + name
        source = (ROOT / 'opendecksight' / (name + '.py')).read_text()
        lines += [f'module = types.ModuleType({full!r})',
                  "module.__package__ = 'opendecksight'",
                  f'sys.modules[{full!r}] = module',
                  f'exec(compile({source!r}, "<streamed-{name}>", "exec"), module.__dict__)']
    lines += ["print(json.dumps(sys.modules['opendecksight.vrr_dry_run'].collect(), indent=2))"]
    return '\n'.join(lines) + '\n'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('target', help='user@host of the already-running USB lab')
    parser.add_argument('--known-hosts', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True, help='new LOCAL raw report')
    args = parser.parse_args()
    if args.target.startswith('-') or any(c.isspace() for c in args.target):
        parser.error('invalid SSH target')
    if args.output.exists():
        parser.error('local output already exists')
    try:
        result = subprocess.run(
            ['ssh', '-o', 'BatchMode=yes', '-o', 'StrictHostKeyChecking=yes',
             '-o', 'UpdateHostKeys=no', '-o', 'UserKnownHostsFile=' + str(args.known_hosts),
             '-o', 'ConnectTimeout=10', args.target, 'python3 -B -'],
            input=program(), capture_output=True, text=True, timeout=60, check=True)
        data = json.loads(result.stdout)
        with args.output.open('x') as output:
            json.dump(data, output, indent=2)
            output.write('\n')
        print('Saved local TEST_ONLY report: ' + str(args.output))
    except (OSError, ValueError, subprocess.SubprocessError) as error:
        detail = error.stderr if isinstance(error, subprocess.CalledProcessError) else str(error)
        parser.exit(1, f'error: {detail}\n')


if __name__ == '__main__':
    main()
