# Open a real Vivado GUI schematic before exporting each view.
set runroot [file normalize [file dirname [info script]]]
cd $runroot
open_project [file join $runroot project gu_review.xpr]
open_run synth_1
start_gui
foreach {label pattern} {digital_top calibration/* correction calibration/correction/* stage1_update calibration/stage1_bank stage2_update calibration/stage2_bank stage2_pwl calibration/correction/stage2_pwl} {
    set objects [get_cells -quiet $pattern]
    if {[llength $objects] == 0} {puts "REVIEW_SCHEMATIC_MISSING=$pattern";continue}
    show_schematic $objects -name $label
    write_schematic -name $label -format pdf -orientation landscape [file join $runroot schematics ${label}.pdf]
    write_schematic -name $label -format svg [file join $runroot schematics ${label}.svg]
    puts "REVIEW_SCHEMATIC_EXPORTED=$label"
}
# Also provide operator-level RTL views for discussion before FPGA mapping.
close_design
synth_design -rtl -name rtl_review -top gu_online_cost_top -part xc7a100tcsg324-1
foreach {label pattern} {rtl_top calibration/* rtl_correction calibration/correction/*} {
    set objects [get_cells -quiet $pattern]
    show_schematic $objects -name $label
    write_schematic -name $label -format pdf -orientation landscape [file join $runroot schematics ${label}.pdf]
    write_schematic -name $label -format svg [file join $runroot schematics ${label}.svg]
}
# Leave the project and GUI available for the user to inspect.
