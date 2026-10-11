"""Create an isolated width-only candidate; never edit frozen RTL."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil

HERE=Path(__file__).resolve().parent

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('baseline',type=Path)
    parser.add_argument('output',type=Path)
    args=parser.parse_args()
    if args.output.exists(): raise SystemExit('Choose a fresh trial directory')
    args.output.mkdir(parents=True)
    for name in ('sources','vectors'): shutil.copytree(args.baseline/name,args.output/name)
    for name in ('manifest.json','review_protocol.json'): shutil.copy2(args.baseline/name,args.output/name)
    for name in ('reports','netlists','checkpoints','schematics','logs','sim'): (args.output/name).mkdir()
    original=(args.output/'sources/fixed_pwl_candidate_a.sv').read_text()
    candidate=original.replace('    logic signed [31:0] raw_wide;',
        '    localparam integer LOCAL_BITS = $clog2(SLICE_WIDTH_Q3 + 1);\n'
        '    localparam integer OFFSET_BITS = $clog2(SLICE_WIDTH_Q3) + 13;\n'
        '    logic signed [31:0] raw_wide;')
    for old,new in (
        ('logic        [31:0] local_q3;','logic [LOCAL_BITS-1:0] local_q3;'),
        ('logic        [31:0] product_wide;','logic [LOCAL_BITS+10:0] product_wide;'),
        ('logic        [31:0] offset_wide;','logic [OFFSET_BITS-1:0] offset_wide;')):
        assert candidate.count(old)==1,old
        candidate=candidate.replace(old,new)
    (args.output/'sources/fixed_pwl_candidate_a.sv').write_text(candidate)
    (args.output/'sources/pwl_reference_review.sv').write_text(original.replace('module fixed_pwl_candidate_a #(','module fixed_pwl_reference_review #('))
    shutil.copy2(HERE/'tb_review_pwl_equivalence.sv',args.output/'sources')
    build=(HERE/'build.tcl').read_text()
    anchor='proc simulate_review {top mode label runroot} {'
    preflight='''add_files -fileset sim_1 -norecurse [list [file join $src pwl_reference_review.sv] [file join $src tb_review_pwl_equivalence.sv]]
import_files -fileset sim_1 -force
update_compile_order -fileset sim_1
set_property top tb_review_pwl_equivalence [get_filesets sim_1]
launch_simulation -mode behavioral
run all
close_sim
set eqlog [file join $runroot project gu_review.sim sim_1 behav xsim simulate.log]
file copy $eqlog [file join $runroot logs pwl_equivalence_simulate.log]
set f [open $eqlog r];set eqtext [read $f];close $f
if {[string match "*Fatal:*" $eqtext] || ![string match "*REVIEW_PWL_WIDTH_EQUIVALENCE_PASS checks=1581056*" $eqtext]} {error "Width-only candidate equivalence preflight failed"}
'''
    assert build.count(anchor)==1
    (args.output/'build.tcl').write_text(build.replace(anchor,preflight+'\n'+anchor))
    (args.output/'width_trial.json').write_text(json.dumps({
        'change':'local input, product and offset widths in PWL only; flatten_hierarchy=none; all original state, timing and arithmetic rules retained',
        'baseline_sha256':hashlib.sha256((args.baseline/'sources/fixed_pwl_candidate_a.sv').read_bytes()).hexdigest(),
        'candidate_sha256':hashlib.sha256((args.output/'sources/fixed_pwl_candidate_a.sv').read_bytes()).hexdigest(),
        'domain':'SLICE_WIDTH_Q3=256 or 1024, all signed16 raw inputs, valid=0/1, coefficient unsigned11',
        'bounds':{'local':'0 <= local <= W in the valid branch; requires clog2(W+1) bits',
            'product':'local * C <= W*2047; (clog2(W+1)+11) bits suffice',
            'offset':'preceding sum <= 3*2047=6141; W*sum fits log2(W)+13 bits for these two power-of-two widths'},
        'equivalence_scope':'six coefficient tuples across all signed16 inputs and both valid values, both stages, plus4096 deterministic random cases; bound derivation covers truncation safety, finite test is not full formal equivalence',
        'expected_equivalence_checks':1581056
    },indent=2))
    print(args.output)

if __name__=='__main__': main()
