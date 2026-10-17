#!/usr/bin/env bash
set -euo pipefail
cd "$1"
mkdir -p logs
iverilog -g2012 -s tb_multicycle -o multicycle.vvp sources/tb_multicycle.sv sources/two_stage_multicycle_candidate_a.sv sources/two_stage_fixed_candidate_a.sv sources/fixed_pwl_candidate_a.sv sources/fixed_gated_lms_exact_candidate_a.sv
vvp multicycle.vvp +VECTORS=online.txt > logs/multicycle.log 2>&1
cat logs/multicycle.log
grep -q 'MULTICYCLE_PASS vectors=8263 replay=128' logs/multicycle.log
if grep -q 'FATAL:' logs/multicycle.log; then exit 1; fi
# Icarus builds and wrappers can differ in how $fatal propagates process status.
vvp multicycle.vvp +VECTORS=negative.txt > logs/negative.log 2>&1 || true
if ! grep -q 'multicycle mismatch pass=0 row=0' logs/negative.log; then
    cat logs/negative.log; exit 1
fi
echo MULTICYCLE_NEGATIVE_PASS
iverilog -g2012 -s tb_two_stage_adaptive_exact_candidate_a -o original.vvp sources/tb_exact_online.sv sources/two_stage_adaptive_exact_candidate_a.sv sources/two_stage_fixed_candidate_a.sv sources/fixed_pwl_candidate_a.sv sources/fixed_gated_lms_exact_candidate_a.sv
vvp original.vvp +VECTORS=online.txt > logs/original_online.log 2>&1
cat logs/original_online.log
grep -q '8263 sequential oracle vectors passed' logs/original_online.log
if grep -q 'FATAL:' logs/original_online.log; then exit 1; fi
iverilog -g2012 -s tb_exact_arithmetic -o arithmetic.vvp sources/tb_exact_arithmetic.sv sources/fixed_gated_lms_exact_candidate_a.sv sources/fixed_gated_lms_candidate_a.sv sources/gated_product_candidate_a.sv
vvp arithmetic.vvp > logs/exact_arithmetic.log 2>&1
cat logs/exact_arithmetic.log
grep -q 'passed' logs/exact_arithmetic.log
if grep -q 'FATAL:' logs/exact_arithmetic.log; then exit 1; fi
