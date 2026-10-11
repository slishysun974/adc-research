# Existing candidate RTL. Run from an ASCII writable directory with snapshots.
set runroot [file normalize [file dirname [info script]]]
cd $runroot
file mkdir logs
puts "REVIEW_VERSION=[version -short]"
puts "REVIEW_PARTS=[get_parts -quiet xc7a100tcsg324-1]"
if {[catch {create_project gu_review [file join $runroot project] -part xc7a100tcsg324-1} msg]} {
    puts "REVIEW_CREATE_ERROR=$msg"
    puts $::errorInfo
    error $msg
}
set_property target_language Verilog [current_project]
set_property simulator_language Mixed [current_project]
set src [file join $runroot sources]
set design_files [list [file join $src fixed_pwl_candidate_a.sv] [file join $src two_stage_fixed_candidate_a.sv] \
    [file join $src fixed_gated_lms_exact_candidate_a.sv] [file join $src two_stage_adaptive_exact_candidate_a.sv] \
    [file join $src cost_top.sv]]
add_files -norecurse $design_files
import_files -force
set_property top gu_online_cost_top [get_filesets sources_1]
add_files -fileset sim_1 -norecurse [list [file join $src tb_exact_online.sv] [file join $src tb_review_cost.sv] \
    [file join $src tb_review_bank.sv] [file join $src tb_exact_arithmetic.sv] [file join $src fixed_gated_lms_candidate_a.sv] [file join $src gated_product_candidate_a.sv]]
import_files -fileset sim_1 -force
set_property xsim.elaborate.debug_level all [get_filesets sim_1]
set_property xsim.simulate.runtime 0ns [get_filesets sim_1]
set vectors [file join $runroot vectors online.txt]
set_property -dict [list xsim.simulate.xsim.more_options "-testplusarg VECTORS=$vectors"] [get_filesets sim_1]
update_compile_order -fileset sources_1
update_compile_order -fileset sim_1

proc simulate_review {top mode label runroot} {
    if {$mode eq "behavioral"} {
        set simdir [file join $runroot project gu_review.sim sim_1 behav xsim]
        set vector_path ../../../../../vectors/online.txt
    } else {
        set simdir [file join $runroot project gu_review.sim sim_1 synth func xsim]
        set vector_path ../../../../../../vectors/online.txt
    }
    # The frozen historical bench uses a 128-byte plusarg buffer.
    set_property -dict [list xsim.simulate.xsim.more_options "-testplusarg VECTORS=$vector_path"] [get_filesets sim_1]
    set_property top $top [get_filesets sim_1]
    if {$mode eq "behavioral"} {launch_simulation -mode behavioral} else {launch_simulation -mode post-synthesis -type functional}
    log_wave [get_objects /$top/*]
    open_vcd [file join $runroot sim ${label}.vcd]
    log_vcd [get_objects /$top/*]
    run all
    close_vcd
    close_sim
    set logfile [file join $simdir simulate.log]
    file copy -force $logfile [file join $runroot logs ${label}_simulate.log]
    set lf [open $logfile r]
    set contents [read $lf]
    close $lf
    if {[string match "*Fatal:*" $contents] || ![regexp {PASS|passed} $contents]} {
        error "simulation $label failed or has no PASS marker; see $logfile"
    }
    puts "REVIEW_SIM_FINISHED=$label"
}
simulate_review tb_exact_arithmetic behavioral arithmetic $runroot
simulate_review tb_review_bank behavioral bank $runroot
simulate_review tb_two_stage_adaptive_exact_candidate_a behavioral online $runroot
simulate_review tb_review_cost behavioral cost_rtl $runroot

set constraint_file [file join $runroot review.xdc]
set cf [open $constraint_file w]
puts $cf {create_clock -name review_clk -period 10.000 [get_ports clk]}
puts $cf {set_input_delay -clock review_clk 1.000 [get_ports {reset valid_in stage1_symbol[*] stage2_symbol[*] backend_raw_code[*] stage1_dither_positive stage2_dither_positive}]}
puts $cf {set_output_delay -clock review_clk 1.000 [get_ports {valid_out final_code[*]}]}
puts $cf {set_load 1.000 [get_ports {valid_out final_code[*]}]}
close $cf
add_files -fileset constrs_1 $constraint_file
import_files -fileset constrs_1 -force
set_property STEPS.SYNTH_DESIGN.ARGS.FLATTEN_HIERARCHY none [get_runs synth_1]
launch_runs synth_1 -jobs 2
wait_on_run synth_1
if {![string match "*Complete*" [get_property STATUS [get_runs synth_1]]]} {error "synthesis did not complete"}
open_run synth_1
write_checkpoint [file join $runroot checkpoints gu_review_synth.dcp]
write_verilog -mode funcsim [file join $runroot netlists gu_review_funcsim.v]
write_edif [file join $runroot netlists gu_review.edf]
report_utilization -hierarchical -file [file join $runroot reports utilization_hierarchical.rpt]
report_utilization -file [file join $runroot reports utilization.rpt]
report_timing_summary -report_unconstrained -max_paths 10 -file [file join $runroot reports timing_synth.rpt]
report_timing -max_paths 3 -path_type full -file [file join $runroot reports critical_paths.rpt]
check_timing -verbose -file [file join $runroot reports check_timing.rpt]
report_methodology -file [file join $runroot reports methodology.rpt]
report_drc -file [file join $runroot reports drc_synth.rpt]
simulate_review tb_review_cost post-synthesis cost_netlist $runroot
set_property -dict [list xsim.simulate.xsim.more_options {-testplusarg VECTORS=../../../../../vectors/negative.txt}] [get_filesets sim_1]
launch_simulation -mode behavioral
run all
close_sim
set logfile [file join $runroot project gu_review.sim sim_1 behav xsim simulate.log]
file copy -force $logfile [file join $runroot logs negative_simulate.log]
set lf [open $logfile r]
set contents [read $lf]
close $lf
if {![string match "*Fatal: cost output mismatch pass=0 row=0*" $contents] || [string match "*REVIEW_COST_PASS*" $contents]} {
    error "negative control did not reject the corrupted reference"
}
puts "REVIEW_NEGATIVE_CONTROL_PASS"
set_property -dict [list xsim.simulate.xsim.more_options {-testplusarg VECTORS=../../../../../vectors/online.txt}] [get_filesets sim_1]
set_property top tb_review_cost [get_filesets sim_1]
write_project_tcl -no_copy_sources [file join $runroot recreate_project.tcl]
set result [open [file join $runroot tool_complete.txt] w]
puts $result "Vivado [version -short]; part xc7a100tcsg324-1; synthesis and simulations returned"
close $result
close_project
exit
