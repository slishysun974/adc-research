"""Classify original high-gate samples by direct digital PWL sensitivity."""
from dataclasses import replace
from fractions import Fraction as F
import json
from pathlib import Path
import sys

from adc_research.calibration.fixed_pwl import correct_fixed
from adc_research.calibration.fixed_gated_lms import adaptive_lower_thresholds_scaled
from experiments.exp_032_online_lms_rtl.generate_vectors import _config
from experiments.exp_042_correlation_roots.run import digest,write

ROOT=Path(__file__).resolve().parents[2]


def main(source,output):
    manifest=json.loads((output/'summary.json').read_text())
    for name,expected in manifest['source_evidence_sha256'].items():
        assert digest(ROOT/name)==expected,name
    cfg=_config()
    cases=[]
    for case in manifest['cases']:
        name=case['name']
        path=source/name/'analog_digital_records.jsonl'
        golden=source/name/'all_products.json'
        rows=[json.loads(line) for line in path.read_text().splitlines()]
        trajectory=json.loads(golden.read_text())['trajectory']
        active=zero_basis=sine_support=equal_zero_basis=0
        product_zero=product_nonzero=0
        requested_sum=0
        factor=cfg.stage2_lms.step_sizes[2]*(1 << cfg.stage2_lms.accumulator_fractional_bits)/64
        first_witness=None
        by_window=[]
        for index,window in enumerate(trajectory):
            codes=tuple(window['coefficients_before']['stage2'])
            pwl=replace(cfg.cascade.stage2_pwl,coefficient_codes=codes)
            threshold=adaptive_lower_thresholds_scaled(codes,cfg.stage2_lms)[2]
            count=without=sz=sn=0
            for row in rows[index*120:(index+1)*120]:
                sample=row['sample']
                raw=sample['backend_centered_code']
                dither=128*sample['stage2_dither_symbol']
                learning_output=correct_fixed(8*raw,pwl).corrected_code_scaled-dither
                if abs(learning_output)>=threshold:
                    active+=1
                    count+=1
                    if abs(raw)<=64:
                        zero_basis+=1
                        equal_zero_basis+=abs(learning_output)==threshold
                        without+=1
                        sz+=dither*learning_output
                        if first_witness is None:
                            first_witness={'conversion':row['conversion_id'],'raw_code':raw,
                                'dither_scaled':dither,'learning_output_scaled':learning_output,
                                'third_threshold_scaled':threshold,'coefficient_codes':codes,
                                'third_basis_code':0}
                    else:
                        sn+=dither*learning_output
                if index>=128:
                    sine_support+=abs(raw)>64
            assert count==window['products']['stage2']['selected_gate_counts'][2]
            assert sz+sn==window['products']['stage2']['selected_product_sums'][2]
            requested=window['products']['stage2']['requested_deltas'][2]
            assert requested==window['products']['stage2']['applied_deltas'][2]
            requested_sum+=requested
            product_zero+=sz
            product_nonzero+=sn
            by_window.append({'window':index,'third_gate_count':count,'zero_third_basis_count':without,
                              'zero_basis_product_sum_q6':sz,'nonzero_basis_product_sum_q6':sn})
        zero_delta=-factor*product_zero
        nonzero_delta=-factor*product_nonzero
        rounding_residual=F(requested_sum)-zero_delta-nonzero_delta
        assert abs(rounding_residual)<=80
        cases.append({'name':name,'third_gate_conversions':active,'gated_zero_third_basis_conversions':zero_basis,
                      'zero_basis_gate_equality_conversions':equal_zero_basis,
                      'third_slice_support_conversions_sine':sine_support,
                      'zero_basis_product_sum_q6':product_zero,'nonzero_basis_product_sum_q6':product_nonzero,
                      'zero_basis_unrounded_q22_update':zero_delta,
                      'nonzero_basis_unrounded_q22_update':nonzero_delta,
                      'actual_third_accumulator_change_q22':requested_sum,
                      'window_rounding_residual_q22':rounding_residual,
                      'first_zero_basis_witness':first_witness,'windows':by_window,
                      'raw_sha256':digest(path),'golden_sha256':digest(golden)})
    write(output/'gate_support.json',{'scope':'original eight-state chronological Gu trajectory; direct raw PWL sensitivity only',
          'direct_sensitivity_definition':'psi3=sign(raw)*min(max(abs(raw)-64,0),32)',
          'interpretation':'gate open does not require nonzero own digital basis; not a proof of an incorrect update direction',
          'cases':cases,'source_script_sha256':digest(Path(__file__))})
    for name,expected in manifest['source_evidence_sha256'].items():
        assert digest(ROOT/name)==expected,name
    for case in cases:
        print(case['name'],case['third_gate_conversions'],case['gated_zero_third_basis_conversions'],flush=True)


if __name__=='__main__':
    main(Path(sys.argv[1]).resolve(),Path(sys.argv[2]).resolve())
