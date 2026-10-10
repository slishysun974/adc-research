#!/usr/bin/env bash
# Scalar serialization of the same Yosys JSON graph, without arithmetic edits.
set -euo pipefail
out="${1:-artifacts/runs/EXP_035/exact_v1/scalar/online}"
project_root="$(pwd -P)"
case "$(realpath -m -- "$out")" in
  "$project_root"/artifacts/runs/EXP_035/*) ;;
  *) printf '%s\n' 'Output escaped EXP_035' >&2; exit 1 ;;
esac
rows="${2:-128}"
seconds="${3:-600}"
reset_rows="${4:-128}"
[[ "$rows" =~ ^[1-9][0-9]*$ && "$seconds" =~ ^[1-9][0-9]*$ && "$reset_rows" =~ ^[1-9][0-9]*$ ]] || exit 1
iverilog -g2012 -Wall -s tb_gu_cost_top \
    -P tb_gu_cost_top.ONLINE=1 -P tb_gu_cost_top.FIRST_PASS_LIMIT="$rows" \
    -P tb_gu_cost_top.RESET_PASS_LIMIT="$reset_rows" \
    -o "$out/gates_tb.vvp" "$out/gates.v" \
    artifacts/tooling/yowasp/yowasp_yosys/share/simcells.v \
    experiments/exp_034_generic_synthesis/tb_cost_tops.sv \
    > "$out/gate_compile.log" 2>&1
set +e
timeout --signal=TERM --kill-after=5s "${seconds}s" vvp -v -N \
    "$out/gates_tb.vvp" +VECTORS=artifacts/runs/EXP_032/candidate_a_q22/vectors.txt \
    > "$out/gate_simulation.log" 2>&1
result=$?
set -e
printf '%s\n' "$result" > "$out/gate_exit_status.txt"
tail -25 "$out/gate_simulation.log"
exit "$result"
