#!/usr/bin/env bash
set -euo pipefail
set +u
source /opt/Xilinx/Vivado/2022.1/settings64.sh
set -u
cd "$1/netlists"
tag=${2:-routed}
mkdir -p ../logs
bench=../sources/tb_multicycle_cost.sv
if [[ -f ../testsources/tb_multicycle_cost.sv ]]; then bench=../testsources/tb_multicycle_cost.sv; fi
xvlog --sv "$bench" routed.v > "../logs/${tag}_compile.log" 2>&1
# Required interconnect/pulse options for timing simulation (AMD UG900).
xelab tb_multicycle_cost glbl -L simprims_ver -L secureip -s "${tag}_sim" -debug typical -mt 2 \
    -maxdelay -transport_int_delays -pulse_r 0 -pulse_int_r 0 -pulse_e 0 -pulse_int_e 0 \
    > "../logs/${tag}_elaborate.log" 2>&1
if grep -Ei 'warning:|error:|fatal:' "../logs/${tag}_compile.log" "../logs/${tag}_elaborate.log"; then exit 1; fi
grep -q 'SDF backannotation was successful.*routed\.sdf' "../logs/${tag}_elaborate.log"
# Reject clock-model/timing errors during a short pilot before a long replay.
cat > "${tag}.tcl" <<EOF
run 1us
set f [open ../logs/${tag}_simulate.log r]
set contents [read \$f]
close \$f
if {[regexp -nocase {timing violation|fatal:|warning:|error:} \$contents]} { puts "SDF_PILOT_FAILED"; quit }
run all
quit
EOF
xsim "${tag}_sim" -tclbatch "${tag}.tcl" -testplusarg VECTORS=../online.txt -wdb "${tag}_positive.wdb" -log "../logs/${tag}_simulate.log" > "../logs/${tag}_console.log" 2>&1
cat "../logs/${tag}_console.log"
grep -q 'MULTICYCLE_COST_PASS vectors=8263 replay=128 reset_phases=38' "../logs/${tag}_simulate.log"
if grep -Ei 'fatal:|timing violation|warning:|error:|\$setuphold|\$recrem' "../logs/${tag}_simulate.log"; then exit 1; fi
xsim "${tag}_sim" -tclbatch "${tag}.tcl" -testplusarg VECTORS=../negative.txt -wdb "${tag}_negative.wdb" -log "../logs/${tag}_negative.log" > "../logs/${tag}_negative_console.log" 2>&1 || true
grep -q 'cost mismatch pass=0 row=0' "../logs/${tag}_negative.log"
if grep -q 'MULTICYCLE_COST_PASS' "../logs/${tag}_negative.log"; then exit 1; fi
echo MULTICYCLE_ROUTED_NEGATIVE_PASS
