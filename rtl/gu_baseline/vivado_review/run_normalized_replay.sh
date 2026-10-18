#!/usr/bin/env bash
# Run a separately frozen normalized bundle. Never modify the physical export.
set -euo pipefail
adc_replay=$(realpath "${1:?normalized replay bundle}")
adc_settings=$(realpath "${2:?Vivado2022.1 settings64.sh}")
adc_mode=${3:-pilot}
[[ "$adc_mode" == pilot || "$adc_mode" == full ]] || exit 2
adc_checker="$adc_replay/tools/normalized_replay.py"
python3 "$adc_checker" verify "$adc_replay"
# Logs, simulator working files and certificates belong to one attempt only.
[[ -z $(find "$adc_replay/logs" -mindepth 1 -print -quit) ]]
[[ ! -e "$adc_replay/design/xsim.dir" && ! -e "$adc_replay/evidence_origin.json" ]]
set +u
source "$adc_settings"
set -u
[[ $(vivado -version 2>&1) == *"Vivado v2022.1"* ]]
cd "$adc_replay/design"
check() { python3 "$adc_checker" check-stage "$adc_replay" "$1"; }
timeout --kill-after=10s 600s xvlog --sv -work normalized_timing tb_staged_cost.sv routed.v > ../logs/timing_compile.log 2>&1
check compile
timeout --kill-after=10s 600s xelab normalized_timing.tb_multicycle_cost normalized_timing.glbl \
  -L simprims_ver -L secureip -s normalized_timing_sim -debug typical -mt 2 \
  -maxdelay -transport_int_delays -pulse_r 0 -pulse_int_r 0 -pulse_e 0 -pulse_int_e 0 \
  > ../logs/timing_elaborate.log 2>&1
check elaborate
timeout --kill-after=10s 600s xsim normalized_timing_sim -tclbatch run_staged.tcl \
  -testplusarg VECTORS=../online.txt -testplusarg PILOT -log ../logs/timing_pilot.log \
  > ../logs/timing_pilot_console.log 2>&1
check pilot
adc_rc=0
timeout --kill-after=10s 600s xsim normalized_timing_sim -tclbatch run_staged.tcl \
  -testplusarg VECTORS=../row221_negative.txt -testplusarg PILOT -log ../logs/timing_pilot_negative.log \
  > ../logs/timing_pilot_negative_console.log 2>&1 || adc_rc=$?
[[ $adc_rc -eq 0 || $adc_rc -eq 1 ]]
check pilot_negative
if [[ "$adc_mode" == pilot ]]; then
  python3 "$adc_checker" validate "$adc_replay" --pilot-only
  echo NORMALIZED_SDF_PILOT_CONTROLS_PASS
  exit 0
fi
timeout --kill-after=10s 3600s xsim normalized_timing_sim -tclbatch run_staged.tcl \
  -testplusarg VECTORS=../online.txt -log ../logs/timing_full.log \
  > ../logs/timing_full_console.log 2>&1
check full
adc_rc=0
timeout --kill-after=10s 600s xsim normalized_timing_sim -tclbatch run_staged.tcl \
  -testplusarg VECTORS=../negative.txt -log ../logs/timing_negative.log \
  > ../logs/timing_negative_console.log 2>&1 || adc_rc=$?
[[ $adc_rc -eq 0 || $adc_rc -eq 1 ]]
check negative
python3 "$adc_checker" validate "$adc_replay"
echo NORMALIZED_SDF_FULL_CONTROLS_PASS
