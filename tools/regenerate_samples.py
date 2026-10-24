#!/usr/bin/env python3
"""Rebuild current 10-second listening audio, measurements and indexes.

Run from any directory with the project's evaluation dependencies installed.
The three initial tasks use up to ten processes in total.
"""
from concurrent.futures import ThreadPoolExecutor
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]


def run(arguments):
    env = dict(os.environ, OPENBLAS_NUM_THREADS='1', OMP_NUM_THREADS='1')
    subprocess.run([sys.executable, '-u', str(ROOT/'tools'/arguments[0]), *arguments[1:]],
                   cwd=ROOT, env=env, check=True)


def main():
    with ThreadPoolExecutor(max_workers=3) as executor:
        list(executor.map(run, [('make_samples.py', '--workers', '3'),
                                ('regenerate_y_samples.py',),
                                ('make_hires_y_probe.py',)]))
    with ThreadPoolExecutor(max_workers=2) as executor:
        list(executor.map(run, [('eval_m700hy_radius_precision.py',),
                                ('make_secondary_monitor_samples.py',)]))
    run(('sample_catalog.py',))


if __name__ == '__main__':
    main()
