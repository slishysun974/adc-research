# View the already verified eight-bank trace without re-running training.
set runroot [file normalize [file dirname [info script]]]
open_wave_database [file join $runroot sim waves tb_two_stage_adaptive_exact_candidate_a_behav.wdb]
create_wave_config eight_states
add_wave /tb_two_stage_adaptive_exact_candidate_a/clk
add_wave /tb_two_stage_adaptive_exact_candidate_a/reset
add_wave /tb_two_stage_adaptive_exact_candidate_a/valid_in
add_wave /tb_two_stage_adaptive_exact_candidate_a/valid_out
add_wave /tb_two_stage_adaptive_exact_candidate_a/final_code
add_wave /tb_two_stage_adaptive_exact_candidate_a/stage1_gate
add_wave /tb_two_stage_adaptive_exact_candidate_a/stage2_gate
foreach n {a10 a11 a12 a13 a20 a21 a22 a23} {add_wave /tb_two_stage_adaptive_exact_candidate_a/$n}
save_wave_config [file join $runroot sim waves eight_states.wcfg]
