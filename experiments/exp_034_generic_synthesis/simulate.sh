#!/usr/bin/env bash
# Existing WSL Icarus; every explicit output remains in the ADC workspace.
set -euo pipefail
out="${1:-artifacts/runs/EXP_034/generic_staged_v1}"
case "$out" in
  artifacts/runs/EXP_034/*) ;;
  *) printf '%s\n' 'Output must stay under artifacts/runs/EXP_034/' >&2; exit 1 ;;
esac
project_root="$(pwd -P)"
case "$(realpath -m -- "$out")" in
  "$project_root"/artifacts/runs/EXP_034/*) ;;
  *) printf '%s\n' 'Resolved output escaped the ADC experiment directory' >&2; exit 1 ;;
esac
tb=experiments/exp_034_generic_synthesis/tb_cost_tops.sv
gate_rows="${3:-128}"
[[ "$gate_rows" =~ ^[1-9][0-9]*$ ]] || exit 1
phase="${4:-both}"
case "$phase" in both|rtl|gate) ;; *) exit 1 ;; esac
for top in ${2:-frozen online}; do
    case "$top" in frozen|online) ;; *) exit 1 ;; esac
    if [[ "$top" == online ]]; then
        online=1
        gate_limit="$gate_rows"
        vectors=artifacts/runs/EXP_032/candidate_a_q22/vectors.txt
    else
        online=0
        gate_limit=1000000
        vectors=artifacts/runs/EXP_031/candidate_a_default_dither/vectors.txt
    fi
    if [[ ! -f "$vectors" ]]; then
        printf 'Missing existing Python vectors: %s\n' "$vectors" >&2
        exit 1
    fi
    if [[ "$phase" != gate ]]; then
    iverilog -g2012 -Wall -s tb_gu_cost_top -P tb_gu_cost_top.ONLINE="$online" \
        -o "$out/$top/rtl_tb.vvp" \
        rtl/gu_baseline/gated_product_candidate_a.sv \
        rtl/gu_baseline/fixed_pwl_candidate_a.sv \
        rtl/gu_baseline/two_stage_fixed_candidate_a.sv \
        rtl/gu_baseline/fixed_gated_lms_candidate_a.sv \
        rtl/gu_baseline/two_stage_adaptive_candidate_a.sv \
        experiments/exp_034_generic_synthesis/cost_tops.sv "$tb" \
        2>&1 | tee "$out/$top/rtl_compile.log"
    vvp -N "$out/$top/rtl_tb.vvp" "+VECTORS=$vectors" | tee "$out/$top/rtl_simulation.log"
    fi
    if [[ "$phase" == rtl ]]; then continue; fi
    iverilog -g2012 -Wall -s tb_gu_cost_top -P tb_gu_cost_top.ONLINE="$online" \
        -P tb_gu_cost_top.FIRST_PASS_LIMIT="$gate_limit" \
        -o "$out/$top/gates_tb.vvp" "$out/$top/gates.v" "$tb" \
        2>&1 | tee "$out/$top/gate_compile.log"
    vvp -N "$out/$top/gates_tb.vvp" "+VECTORS=$vectors" | tee "$out/$top/gate_simulation.log"
done
