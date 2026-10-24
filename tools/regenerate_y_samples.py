#!/usr/bin/env python3
"""Generate all 10-second Y listening samples, parallelized by source.

Independent workers write separate manifests; merge only after all succeed.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
FAMILIES = {'hybrid': ('make_hybrid_y_samples.py', 'hybrid_y_samples'),
            'monitor': ('make_monitor_y_samples.py', 'monitor_y_samples')}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--workers', type=int, default=6)
    parser.add_argument('--resume', action='store_true', help='resume an interrupted run with unchanged code')
    args = parser.parse_args()
    env = dict(os.environ, OPENBLAS_NUM_THREADS='1', OMP_NUM_THREADS='1')
    with tempfile.TemporaryDirectory(prefix='gracefm-') as tmp:
        jobs = []
        for family, (script, stem) in FAMILIES.items():
            destination = ROOT / 'docs/results' / (stem + '.json')
            previous = json.loads(destination.read_text()) if args.resume and destination.exists() else None
            for source in ('demo', 'fishin', 'vibeace'):
                part = Path(tmp) / (stem + '_' + source + '.json')
                if previous:
                    report = dict(previous)
                    report['sources'] = {k: v for k, v in previous['sources'].items() if k == source}
                    report['samples'] = [r for r in previous['samples'] if r['source'] == source]
                    part.write_text(json.dumps(report))
                jobs.append((script, source, part))
        def run(job):
            script, source, part = job
            command = [sys.executable, str(ROOT / 'tools' / script), '--sources', source,
                       '--json', str(part), '--resume']
            subprocess.run(command, cwd=ROOT, env=env, check=True)
        with ThreadPoolExecutor(max_workers=args.workers) as executor:
            list(executor.map(run, jobs))
        for family, (_, stem) in FAMILIES.items():
            combined = None
            for source in ('demo', 'fishin', 'vibeace'):
                report = json.loads((Path(tmp) / (stem + '_' + source + '.json')).read_text())
                if combined is None:
                    combined = dict(report, sources={}, samples=[])
                    if 'profiles' in report: combined['profiles'] = {}
                combined['sources'].update(report['sources'])
                combined['samples'].extend(report['samples'])
                if 'profiles' in report: combined['profiles'].update(report['profiles'])
            destination = ROOT / 'docs/results' / (stem + '.json')
            destination.write_text(json.dumps(combined, ensure_ascii=False, indent=2, allow_nan=False) + '\n')
            print(destination, len(combined['samples']), 'samples', flush=True)


if __name__ == '__main__':
    main()
