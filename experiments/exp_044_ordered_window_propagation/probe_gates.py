"""Read-only classification of the original posterior third-gate samples."""
from dataclasses import replace
import json
from pathlib import Path
from adc_research.calibration.fixed_pwl import correct_fixed
from adc_research.calibration.fixed_gated_lms import adaptive_lower_thresholds_scaled
from experiments.exp_032_online_lms_rtl.generate_vectors import _config


def main():
    root=Path('artifacts/runs/EXP_039/window_v1')
    cfg=_config()
    for case in json.loads((root/'summary.json').read_text())['cases']:
        name=case['name']
        rows=[json.loads(line) for line in (root/name/'analog_digital_records.jsonl').read_text().splitlines()]
        trajectory=json.loads((root/name/'all_products.json').read_text())['trajectory']
        active=zero_basis=sine_support=0
        for index,window in enumerate(trajectory):
            codes=tuple(window['coefficients_before']['stage2'])
            pwl=replace(cfg.cascade.stage2_pwl,coefficient_codes=codes)
            threshold=adaptive_lower_thresholds_scaled(codes,cfg.stage2_lms)[2]
            count=0
            for row in rows[index*120:(index+1)*120]:
                sample=row['sample']
                raw=sample['backend_centered_code']
                output=correct_fixed(8*raw,pwl).corrected_code_scaled-128*sample['stage2_dither_symbol']
                if abs(output)>=threshold:
                    active+=1
                    count+=1
                    zero_basis+=abs(raw)<=64
                if index>=128:
                    sine_support+=abs(raw)>64
            assert count==window['products']['stage2']['selected_gate_counts'][2]
        print(name,active,zero_basis,sine_support,flush=True)


if __name__=='__main__':
    main()
