"""Shared, explicit names for reference and processed listening samples."""
import re


def reference_name(source, fs=32000):
    return f"{source}__{fs // 1000}k__reference.flac"


def sample_name(source, fs, profile, case='codec', *, sub=None, postfilter=True):
    config = profile + (f'+{sub}' if sub else '')
    case = re.sub(r'^awgn(\d+)$', r'awgn-cn0-\1dBHz', case)
    case = re.sub(r'^rayleigh(\d+)$', r'rayleigh-cn0-\1dBHz', case)
    case = re.sub(r'^main_minus10db(\d+)$', r'main-fade-10dB-cn0-\1dBHz', case)
    case = re.sub(r'^phase_only(\d+)$', r'phase-only-awgn-cn0-\1dBHz', case)
    if not postfilter:
        case += '-pf-off'
    return f'{source}__{fs // 1000}k__{config}__{case}.flac'
