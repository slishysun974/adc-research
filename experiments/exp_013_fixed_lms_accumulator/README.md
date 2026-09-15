# EXP-013: Fixed-point LMS update accumulator

This experiment separates the 11-bit Q1.10 PWL coefficient interface reported
by Gu et al. from the internal accumulator used by the gated LMS update. It
holds the Q1.10 correction path, Q3 data path, balanced training set, shuffle
seed, and normalized step sizes fixed while sweeping accumulator fractional
resolutions of 10, 14, 18, 22, and 26 bits.

The accumulator format, update rounding, coefficient export rounding,
threshold rounding, and saturation placement are research assumptions. They
are not claimed as transistor-level or register-transfer-level details of the
published converter.

Run from the repository root with the project package available on
`PYTHONPATH`:

```powershell
$env:PYTHONPATH = "src"
python experiments/exp_013_fixed_lms_accumulator/run.py --run-id <run-id>
```
