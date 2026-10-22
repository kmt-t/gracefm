# GraceFM — SDR IC partner brief (draft)

## Proposed application

GraceFM is a digital audio codec and modem designed for low-delay VHF radio. The broadcast stereo profile (`B200H-A4`) uses M/S stereo, a 64-sample frame at 32 kHz, and a hierarchical 16-QAM main signal. A separate lower-rate signal (`S100`) can provide frequency diversity; it occupies **another RF channel**, not spare capacity inside the main channel.

| Design-model quantity | B200H-A4 main signal | S100 secondary signal |
|---|---:|---:|
| Audio payload | 536 kbit/s | 95 kbit/s |
| RF gross bit rate, including preamble | 716 kbit/s | 189 kbit/s |
| 99% occupied bandwidth | approximately 182 kHz | approximately 104 kHz |
| RF frequency | VHF design target | Several MHz away from the main signal |

The main-signal spectrum was calculated with RRC pulse shaping (roll-off 0.10); its simulated −30 dB width is approximately 197 kHz. The 4 ms broadcast transport-delay figure assumes zero processing time. These are **simulation/design results**, not measured RF or hardware results. The Python reference processes offline arrays; RF synchronization, equalization, and real-time FPGA operation remain to be demonstrated. Full conditions and measurements are in [`docs/SPEC.md`](../docs/SPEC.md) and [`docs/QUALITY_BENCHMARK.md`](../docs/QUALITY_BENCHMARK.md).

## Evaluation proposition

1. Make the Python encoder/decoder a bit-exact golden model for RTL test vectors.
2. Implement a synthesizable transmitter and receiver on an FPGA connected to a dual-channel VHF SDR transceiver.
3. Measure occupied bandwidth and out-of-band emissions, RF sensitivity, fading behavior, actual end-to-end latency, and FPGA logic/memory/power.
4. If those results support an application, discuss an evaluation license and then a production IP license with the IC or system supplier. Commercial RTL licensing rights must be established with its author before an offer is made.

## Candidate partners

These are **technical-fit candidates**, not confirmed buyers or expressions of interest.

| Candidate | Published fit | Appropriate first proposal |
|---|---|---|
| [Analog Devices ADRV9002 / AD-JUPITER-EBZ](https://www.analog.com/en/products/ADRV9002.html) | 30 MHz–6 GHz, dual TX/RX; the AD-JUPITER evaluation platform pairs ADRV9002 with a Zynq MPSoC | Evaluate GraceFM on its SDR platform and review measured RF performance. Its existing transceiver is not assumed to have space for GraceFM RTL. |
| [Lime Microsystems LMS7002M / LimeSDR](https://limemicro.com/silicon/lms7002m/) | 100 kHz–3.8 GHz, dual transceiver, SDR development boards | Demonstrate a two-frequency link and explore a reference design or future integration. |
| [NXP SAF360x](https://www.nxp.com/products/radio/digital-radio-and-processing-system-on-chip%3ASAF360X) | Digital-radio receiver SoC with multiple broadcast standards and dual-channel processing | Later-stage receiver integration discussion, after interoperable RF hardware is demonstrated. |

## Initial inquiry draft

**Subject:** Technical evaluation proposal: low-delay narrowband digital audio on your SDR platform

Hello,

We are developing GraceFM, a digital audio codec and modem for low-delay VHF radio. Its stereo main signal is designed around a 200 kHz RF channel, with an optional lower-rate diversity signal on a separate frequency. We can provide the reference implementation and simulation results for technical review under suitable evaluation terms; an FPGA implementation is planned.

We would like to assess the design on your SDR evaluation platform, including two-frequency operation, measured spectrum, receiver behavior under fading, and implementation cost. Would the appropriate applications or radio-platform team be interested in reviewing a short technical brief and discussing an evaluation setup?

Best regards,

[Name / organization]

## Source and status notes

- [GraceFM technical specification](../docs/SPEC.md) and [audio benchmark methodology](../docs/QUALITY_BENCHMARK.md).
- [ADI ADRV9002 product information](https://www.analog.com/en/products/ADRV9002.html), [Lime LMS7002M product information](https://limemicro.com/silicon/lms7002m/), and [NXP SAF360x product information](https://www.nxp.com/products/radio/digital-radio-and-processing-system-on-chip%3ASAF360X).
- The inquiry is a draft. No partner interest, RF measurement, RTL completion, or third-party patent clearance is represented here.
