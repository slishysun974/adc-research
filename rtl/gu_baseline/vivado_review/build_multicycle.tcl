# Usage: vivado -mode batch -source build_multicycle.tcl -tclargs RUN_DIRECTORY
set runroot [file normalize [lindex $argv 0]]
cd $runroot
file mkdir reports checkpoints netlists
set manifest_file [open [file join $runroot manifest.json] r]
set manifest_text [read $manifest_file]
close $manifest_file
if {![regexp {"part": "([^"]+)"} $manifest_text -> part]} {error "missing frozen part"}
puts "MULTICYCLE_TOOL=[version -short]"
create_project -in_memory -part $part
set_property target_language Verilog [current_project]
foreach name {fixed_pwl_candidate_a.sv two_stage_fixed_candidate_a.sv fixed_gated_lms_exact_candidate_a.sv two_stage_multicycle_candidate_a.sv multicycle_cost_top.sv} {
    read_verilog -sv [file join $runroot sources $name]
}
read_xdc [file join $runroot sources multicycle.xdc]
synth_design -top gu_multicycle_cost_top -part $part -flatten_hierarchy full -max_dsp 0
set output_registers [get_cells -hier -filter {IS_SEQUENTIAL && (NAME =~ engine/final_code_reg* || NAME =~ engine/valid_out_reg* || NAME =~ engine/done_out_reg*)}]
set_property IOB TRUE $output_registers

# Only held sample/state -> E16 pending-data registers may use 16 cycles.
# Numerator/divider/bank writeback, all control and external IO stay one-cycle.
set samples [get_cells -hier -filter {IS_SEQUENTIAL && NAME =~ engine/sample_*_reg*}]
set banks [get_cells -hier -filter {IS_SEQUENTIAL && NAME =~ engine/stage*_bank/accumulator*_q22_reg*}]
set results [get_cells -hier -filter {IS_SEQUENTIAL && (NAME =~ engine/pending_learning*_reg* || NAME =~ engine/pending_gate*_reg* || NAME =~ engine/pending_code_reg* || NAME =~ engine/pending_valid_reg*)}]
if {[llength $samples] != 18 || [llength $banks] != 184 || [llength $results] != 53} {
    error "Unexpected MCP scope: samples=[llength $samples], banks=[llength $banks], results=[llength $results]"
}
set sources [concat $samples $banks]
set destinations $results
set_multicycle_path 16 -setup -from $sources -to $destinations
set_multicycle_path 15 -hold -from $sources -to $destinations
puts "MULTICYCLE_SCOPE samples=[llength $samples] banks=[llength $banks] results=[llength $results]"
report_exceptions -file reports/exceptions.rpt
report_clocks -file reports/clocks.rpt
report_timing_summary -report_unconstrained -file reports/timing_synth.rpt
report_timing -max_paths 5 -file reports/critical_synth.rpt
write_checkpoint checkpoints/synth.dcp
opt_design
place_design
phys_opt_design
route_design
phys_opt_design -hold_fix
report_route_status -file reports/route_status.rpt
report_timing_summary -report_unconstrained -max_paths 10 -file reports/timing_routed.rpt
report_timing -delay_type max -max_paths 5 -file reports/critical_setup.rpt
report_timing -delay_type min -max_paths 5 -file reports/critical_hold.rpt
report_utilization -file reports/utilization.rpt
check_timing -verbose -file reports/check_timing.rpt
report_methodology -file reports/methodology.rpt
report_drc -file reports/drc.rpt
write_checkpoint checkpoints/routed.dcp
write_verilog -mode timesim -sdf_anno true netlists/routed.v
write_sdf netlists/routed.sdf
set setup [get_property SLACK [get_timing_paths -delay_type max -max_paths 1]]
set hold [get_property SLACK [get_timing_paths -delay_type min -max_paths 1]]
set out [open timing_result.json w]
puts $out "{\"tool\":\"[version -short]\",\"part\":\"$part\",\"period_ns\":10,\"compute_cycles\":16,\"latency_cycles\":39,\"initiation_interval_cycles\":40,\"wns_ns\":$setup,\"whs_ns\":$hold}"
close $out
if {$setup < 0 || $hold < 0} {error "Routed timing failed: setup=$setup hold=$hold"}
puts "MULTICYCLE_ROUTED_TIMING_PASS setup=$setup hold=$hold"
exit
