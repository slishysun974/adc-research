# Run in the Vivado Tcl console after opening the packaged project.
set runroot [file normalize [file dirname [info script]]]
close_design
reset_run synth_1
launch_runs synth_1 -jobs 2
wait_on_run synth_1
open_run synth_1
file mkdir [file join $runroot reports rechecked]
report_utilization -file [file join $runroot reports rechecked utilization.rpt]
report_timing_summary -report_unconstrained -max_paths 10 -file [file join $runroot reports rechecked timing_synth.rpt]
check_timing -verbose -file [file join $runroot reports rechecked check_timing.rpt]
write_verilog -mode funcsim [file join $runroot netlists gu_review_rechecked_funcsim.v]
set reg [get_cells -hier -filter {NAME == calibration/stage2_bank/accumulator0_q22_reg[0]}]
set dpin [get_pins -of_objects $reg -filter {REF_PIN_NAME == D}]
set cone [get_cells -of_objects [all_fanin -flat -levels 3 -to $dpin]]
show_schematic [concat $reg $cone] -name accumulator0_local
write_schematic -name accumulator0_local -format svg [file join $runroot schematics accumulator0_local.svg]
write_schematic -name accumulator0_local -format pdf [file join $runroot schematics accumulator0_local.pdf]
set missing {}
foreach f [get_files -all] {
    if {![file exists [get_property NAME $f]]} {lappend missing [get_property NAME $f]}
}
set out [open [file join $runroot project_paths_verified.txt] w]
puts $out "Project opened after relocation. Source/constraint files: [llength [get_files -all]]. Missing: $missing"
puts $out "Local logic cells: [llength $cone]. Target state bit: $reg"
close $out
if {[llength $missing]} {error "packaged project has missing files"}
help open_wave_database
help save_wave_config
