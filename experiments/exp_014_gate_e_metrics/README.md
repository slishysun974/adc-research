# EXP-014: Gate E static and spectral metrics

This experiment validates the common code-density and coherent single-tone FFT
metrics used by the ADC platform. It compares three modes:

1. ideal static pipeline;
2. static PWL nonlinearity without correction;
3. the same PWL nonlinearity with known-coefficient floating correction.

The static test reports the corrected transfer both without dither and with an
exhaustive balance of the four dither-symbol pairs. These are separate operating
conditions: the balanced result does not replace or conceal missing codes in the
no-dither result.

The experiment uses a uniform full-range ramp for histogram DNL and
endpoint-referenced transition INL. Dynamic metrics use integer-cycle sine
records, a rectangular window, explicit fundamental bins, harmonics two through
five folded into the first Nyquist zone, and the full dc-to-Nyquist bandwidth.

The paper's measured results are used only as directional anchors. Absolute
agreement is excluded because this static model does not include circuit noise,
input-buffer distortion, sampling distortion, or complete SHA-less timing.

Run from the repository root with the project package available on
`PYTHONPATH`:

```powershell
$env:PYTHONPATH = "src"
python experiments/exp_014_gate_e_metrics/run.py --run-id <run-id>
```
