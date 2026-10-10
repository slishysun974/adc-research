// Cost-measurement boundaries only. Algorithms and candidate arithmetic are
// unchanged. Both tops expose only valid_out and the final 12-bit code.
// Frozen coefficients are runtime inputs, not tied-off constants or storage.
module gu_frozen_cost_top (
    input wire valid_in,
    input wire signed [3:0] stage1_symbol, stage2_symbol,
    input wire [7:0] backend_raw_code,
    input wire stage1_dither_positive, stage2_dither_positive,
    input wire [10:0] stage1_coefficient0_q10, stage1_coefficient1_q10,
    input wire [10:0] stage1_coefficient2_q10, stage1_coefficient3_q10,
    input wire [10:0] stage2_coefficient0_q10, stage2_coefficient1_q10,
    input wire [10:0] stage2_coefficient2_q10, stage2_coefficient3_q10,
    output wire valid_out,
    output wire [11:0] final_code
);
    two_stage_fixed_candidate_a correction (
        .valid_in(valid_in),
        .stage1_symbol(stage1_symbol), .stage2_symbol(stage2_symbol),
        .backend_raw_code(backend_raw_code),
        .stage1_dither_positive(stage1_dither_positive),
        .stage2_dither_positive(stage2_dither_positive),
        .stage1_coefficient0_q10(stage1_coefficient0_q10),
        .stage1_coefficient1_q10(stage1_coefficient1_q10),
        .stage1_coefficient2_q10(stage1_coefficient2_q10),
        .stage1_coefficient3_q10(stage1_coefficient3_q10),
        .stage2_coefficient0_q10(stage2_coefficient0_q10),
        .stage2_coefficient1_q10(stage2_coefficient1_q10),
        .stage2_coefficient2_q10(stage2_coefficient2_q10),
        .stage2_coefficient3_q10(stage2_coefficient3_q10),
        .valid_out(valid_out), .final_code(final_code)
    );
endmodule

module gu_online_cost_top (
    input wire clk, reset, valid_in,
    input wire signed [3:0] stage1_symbol, stage2_symbol,
    input wire [7:0] backend_raw_code,
    input wire stage1_dither_positive, stage2_dither_positive,
    output wire valid_out,
    output wire [11:0] final_code
);
    two_stage_adaptive_candidate_a calibration (
        .clk(clk), .reset(reset), .valid_in(valid_in),
        .stage1_symbol(stage1_symbol), .stage2_symbol(stage2_symbol),
        .backend_raw_code(backend_raw_code),
        .stage1_dither_positive(stage1_dither_positive),
        .stage2_dither_positive(stage2_dither_positive),
        .valid_out(valid_out), .final_code(final_code)
    );
endmodule
