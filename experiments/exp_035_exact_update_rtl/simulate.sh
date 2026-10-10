#!/usr/bin/env bash
# Existing WSL Icarus, restricted to ADC experiment outputs.
set -euo pipefail
out="${1:-artifacts/runs/EXP_035/exact_v1}"
project_root="$(pwd -P)"
case "$(realpath -m -- "$out")" in
  "$project_root"/artifacts/runs/EXP_035/*) ;;
  *) printf '%s\n' 'Output escaped EXP_035' >&2; exit 1 ;;
esac
mkdir -p "$out/rtl"
sources=(rtl/gu_baseline/gated_product_candidate_a.sv
         rtl/gu_baseline/fixed_pwl_candidate_a.sv
         rtl/gu_baseline/two_stage_fixed_candidate_a.sv
         rtl/gu_baseline/fixed_gated_lms_candidate_a.sv
         rtl/gu_baseline/two_stage_adaptive_candidate_a.sv
         rtl/gu_baseline/fixed_gated_lms_exact_candidate_a.sv
         rtl/gu_baseline/two_stage_adaptive_exact_candidate_a.sv)
iverilog -g2012 -Wall -s tb_exact_arithmetic -o "$out/rtl/arithmetic.vvp" \
    "${sources[@]}" experiments/exp_035_exact_update_rtl/tb_exact_arithmetic.sv \
    > "$out/rtl/arithmetic_compile.log" 2>&1
vvp -N "$out/rtl/arithmetic.vvp" | tee "$out/rtl/arithmetic.log"
iverilog -g2012 -Wall -s tb_two_stage_adaptive_exact_candidate_a -o "$out/rtl/online.vvp" \
    "${sources[@]}" experiments/exp_035_exact_update_rtl/tb_exact_online.sv \
    > "$out/rtl/online_compile.log" 2>&1
vvp -N "$out/rtl/online.vvp" +VECTORS=artifacts/runs/EXP_032/candidate_a_q22/vectors.txt \
    | tee "$out/rtl/online.log"
iverilog -g2012 -Wall -s tb_gu_cost_top -P tb_gu_cost_top.ONLINE=1 \
    -o "$out/rtl/cost.vvp" "${sources[@]}" experiments/exp_035_exact_update_rtl/cost_top.sv \
    experiments/exp_034_generic_synthesis/tb_cost_tops.sv > "$out/rtl/cost_compile.log" 2>&1
vvp -N "$out/rtl/cost.vvp" +VECTORS=artifacts/runs/EXP_032/candidate_a_q22/vectors.txt \
    | tee "$out/rtl/cost.log"
