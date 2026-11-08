# GraceFM hardening plan

This document separates verified offline behavior from claims that require hardware evidence. It is a roadmap, not a claim that RF or real-time acceptance has already passed.

## Ten hardening stages

1. **Protocol contract and compatibility**
   - Freeze bitstream fixtures for every registered profile and both Haar/LeGall formats.
   - Record the source revision, profile-matrix hash, symbol count, CRC vectors, and expected decoded PCM hashes.
   - Require cross-implementation fixtures to be consumed by GraceFM-Ultra's Rust tests.
2. **Audio quality**
   - Expand objective and listening evaluations beyond the current small material set.
   - Report ViSQOL, waveform SNR, loudness-aligned error, spectral error, and confidence intervals separately.
   - Preserve per-material results; never promote aggregate averages alone.
3. **Channel robustness**
   - Sweep AWGN, Rayleigh/Rician fading, Doppler, multipath delay spread, burst loss, impulsive noise, and adjacent-channel interference.
   - Publish BLER and quality-vs-C/N0 curves with confidence intervals and seeds.
4. **Acquisition and synchronization**
   - Design and validate carrier-frequency, sample-clock, timing, phase, and frame-boundary acquisition.
   - Explicitly label existing synchronized simulations as ideal synchronization experiments.
5. **Security and replay protection**
   - Treat AES-CTR as confidentiality only. CRC is not authentication.
   - Before encrypted deployment, add a reviewed authenticated-encryption construction with per-stream nonce uniqueness, key rotation, replay-window policy, and downgrade handling.
   - Do not reuse a nonce with the same key. Add tamper, replay, wraparound, and restart tests.
6. **Streaming and latency**
   - Define bounded streaming APIs, queue limits, backpressure, timestamps, and end-of-stream behavior.
   - Measure algorithmic, buffering, device, and end-to-end latency separately on target hardware.
7. **DSP performance**
   - Benchmark representative profiles on target CPU/FPGA; profile before introducing SIMD or fixed-point changes.
   - Keep scalar reference outputs as golden vectors for optimized kernels.
8. **Fault containment**
   - Fuzz frame parsing, profile selection, malformed lengths, truncation, and random soft-input arrays.
   - Bound allocations and reject unsupported formats explicitly.
9. **Reproducible validation**
   - Pin evaluation environments and record tool versions, seeds, source hashes, and input hashes.
   - Make generated profile tables and sample catalogs check-only CI gates.
10. **Hardware and operational readiness**
    - Build a conducted-RF test plan, then over-the-air tests only within applicable spectrum rules.
    - Validate ADC clipping, oscillator drift, AGC, multipath, temperature, long runs, and recovery after signal loss.
    - Publish a device compatibility matrix and a clear list of unverified features.

## Acceptance gates

- Every protocol/profile change passes the Python test suite and generated-table checks.
- Every frame-format change has golden vectors and a matching Ultra compatibility update.
- Security claims distinguish encryption, integrity, authenticity, and replay resistance.
- Every performance claim names hardware, profile, channel model, measurement method, and percentile.
- No document describes a synchronized offline simulation as a real receiver measurement.

## Immediate priorities

P0: protocol fixtures shared with Ultra; security boundary documentation; end-to-end sync/acquisition test design.

P1: deterministic channel sweeps and BLER confidence intervals; streaming interface design; fuzzing.

P2: target-hardware benchmarks, SIMD experiments, and RF field validation.
