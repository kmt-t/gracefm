#!/usr/bin/env python3
"""Create current M700H + SUB100-48K dual-carrier monitoring examples."""
import json
import os
from pathlib import Path
import sys
import numpy as np
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from gracefm import channel,wavio
from gracefm.profiles import PROFILES
from make_monitor_y_samples import input_audio
from make_hybrid_y_samples import sha256,atomic_json
from eval_hybrid import score
from sample_names import sample_name


def main():
    audio=input_audio('demo',10)
    reference,fs=wavio.read(ROOT/'samples/monitor/demo__48k__reference.flac')
    assert fs==48000 and audio.shape==reference.shape
    report={'power_main':0.75,'power_secondary':0.25,'seed':1,
            'main_profile_signature':repr(PROFILES['M700H']),
            'secondary_profile_signature':repr(PROFILES['SUB100-48K']),'samples':[]}
    for cn0 in (80,75,70,65):
        output,stats,link=channel.link(audio,'M700H',cn0,sub='SUB100-48K',power_main=0.75,seed=1)
        assert np.all(np.isfinite(output))
        path=ROOT/'samples/monitor'/sample_name('demo',48000,'M700H',f'awgn{cn0}',sub='SUB100-48K')
        wavio.write_flac24(path,output,fs)
        stored,_=wavio.read(path)
        measurements=score(reference,stored,PROFILES['M700H'],stats)
        measurements['secondary_crc_fail_percent']=100*stats['B']['crc_fail']/stats['B']['frames']
        report['samples'].append(dict(file=path.name,sha256=sha256(path),link=link,measurements=measurements))
        atomic_json(str(ROOT/'docs/results/secondary_monitor_samples.json'),report)
        print(path.name,'finished',flush=True)


if __name__=='__main__':main()
