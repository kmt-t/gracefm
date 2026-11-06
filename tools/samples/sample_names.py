"""Shared, explicit names for reference and processed listening samples."""
import re


def reference_name(source, fs=32000):
    return f"{source}__{fs // 1000}k__reference.flac"


def sample_name(source, fs, profile, case='codec', *, sub=None):
    config = profile + (f'+{sub}' if sub else '')
    case = re.sub(r'^awgn(\d+)$', r'awgn-cn0-\1dBHz', case)
    return f'{source}__{fs // 1000}k__{config}__{case}.flac'
