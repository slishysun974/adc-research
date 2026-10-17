# 100 MHz interface contract. No board pin assignment is implied.
create_clock -name calibration_clk -period 10.000 [get_ports clk]
set data_inputs [get_ports {reset valid_in stage1_symbol[*] stage2_symbol[*] backend_raw_code[*] stage1_dither_positive stage2_dither_positive}]
set data_outputs [get_ports {ready_in done_out valid_out final_code[*]}]
set_input_delay -clock calibration_clk -max 1.000 $data_inputs
set_input_delay -clock calibration_clk -min 0.200 $data_inputs
set_output_delay -clock calibration_clk -max 1.000 $data_outputs
set_output_delay -clock calibration_clk -min 0.200 $data_outputs
set_load 1.000 $data_outputs
set_property IOSTANDARD LVCMOS33 [get_ports *]
# Explicit output electrical choice for the 1 pF demonstration load.
set_property SLEW FAST $data_outputs
set_property DRIVE 12 $data_outputs

# Applied after synthesis by build_multicycle.tcl. There are deliberately no
# false paths or whole-clock exceptions. See the timing contract in REPRODUCE.
