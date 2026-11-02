#!/usr/bin/env python3
"""Inspect a real catalog plan; --install explicitly opts into a system installation."""

import argparse
import json
from pathlib import Path
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'src'))
from package_install import PackageInstaller


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--app', choices=('tuxpaint', 'kturtle'), default='tuxpaint')
    parser.add_argument('--install', action='store_true', help='Actually install the selected catalog app; use a disposable desktop. System authorization is not bypassed.')
    args = parser.parse_args()
    catalog = json.loads((ROOT / 'src' / 'recommendations.json').read_text(encoding='utf-8'))
    with tempfile.TemporaryDirectory(prefix='cozy-packagekit-smoke-') as temporary:
        manager = PackageInstaller(Path(temporary) / 'job.json')
        manager.prepare(args.app, catalog)
        manager.worker.join()
        state = manager.snapshot()
        print(json.dumps({key: value for key, value in state.items() if key != 'confirmationToken'}, indent=2), flush=True)
        if state['status'] == 'error':
            return 1
        if args.install and state['status'] == 'ready':
            print('Explicitly requested real installation; waiting for system authorization.', flush=True)
            manager.start(state['jobId'], state['confirmationToken'])
            last = None
            while manager.worker.is_alive():
                state = manager.snapshot()
                current = (state['status'], state.get('phase'), state.get('percent'))
                if current != last:
                    print(json.dumps(current), flush=True)
                    last = current
                manager.worker.join(1)
            state = manager.snapshot()
            print(json.dumps(state, indent=2), flush=True)
            return 0 if state['status'] == 'complete' else 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
