"""The listening comparison must preserve exactly the configured basic layer."""
import copy
from pathlib import Path
import sys
import numpy as np
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from gracefm.codec import encode_block, offset_of
from gracefm.profiles import PROFILES
from tools.eval.base_layer_sample import BaseLayerDecoder,base_layer_audio


def test_erasing_extension_retains_basic_layer():
    p=PROFILES['M700']
    decoder=BaseLayerDecoder(p)
    bd=encode_block(np.random.default_rng(18).normal(0,0.05,(64,2)),p)
    layout=decoder.layout
    def probs(block):
        return np.array([((int(block.mant[ch][k][j])+offset_of((p.bits_m if ch=='M' else p.bits_s)[k],p,ch,k))>>pos)&1
                         for ch,k,j,pos in layout.coef_items],float)
    changed=copy.deepcopy(bd)
    for ch,k,j,pos in layout.coef_items[layout.n_base_bits:]:
        offset=offset_of((p.bits_m if ch=='M' else p.bits_s)[k],p,ch,k)
        changed.mant[ch][k][j]=((int(changed.mant[ch][k][j])+offset)^(1<<pos))-offset
    a=decoder.soft_coeffs(bd,probs(bd))[0]
    b=decoder.soft_coeffs(changed,probs(changed))[0]
    for ch in ('M','S'):
        for x,y in zip(a[ch],b[ch]):np.testing.assert_array_equal(x,y)


def test_noiseless_base_layer_audio_is_valid():
    x=np.random.default_rng(6).normal(0,0.05,(128,2))
    y=base_layer_audio(x,PROFILES['M700'])
    assert y.shape==x.shape and np.isfinite(y).all()


if __name__=='__main__':
    test_erasing_extension_retains_basic_layer()
    test_noiseless_base_layer_audio_is_valid()
    print('2 basic-layer sample tests passed')
