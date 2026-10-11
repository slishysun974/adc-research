# Open in Vivado's Tcl console, or batch with -tclargs batch.
set runroot [file normalize [file dirname [info script]]]
cd $runroot
if {[current_project -quiet] eq ""} {open_project [file join $runroot project gu_review.xpr]}
set stamp [clock format [clock seconds] -format %Y%m%d_%H%M%S]
set demo [file join $runroot logs demo_$stamp]
file mkdir $demo
set_property top tb_review_cost [get_filesets sim_1]
set_property xsim.simulate.runtime 0ns [get_filesets sim_1]
set_property -dict [list xsim.simulate.xsim.more_options {-testplusarg VECTORS=../../../../../vectors/online.txt}] [get_filesets sim_1]
launch_simulation -mode behavioral
log_wave [get_objects /tb_review_cost/*]
open_vcd [file join $demo cost.vcd]
log_vcd [get_objects /tb_review_cost/*]
run all
close_vcd
set lf [open [file join $runroot project gu_review.sim sim_1 behav xsim simulate.log] r]
set result [read $lf]
close $lf
file copy [file join $runroot project gu_review.sim sim_1 behav xsim simulate.log] [file join $demo simulate.log]
if {[string match "*Fatal:*" $result] || ![string match "*REVIEW_COST_PASS vectors=8391 idle_cycles=8391 reset_replay=128*" $result]} {
    error "Short demo failed: $demo"
}
puts "REVIEW_SHORT_DEMO_PASS=$demo"
if {[info exists argv] && [lindex $argv 0] eq "batch"} {close_sim;close_project;exit}
