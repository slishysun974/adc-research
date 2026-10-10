module gu_online_cost_top (
    input wire clk, reset, valid_in,
    input wire signed [3:0] stage1_symbol, stage2_symbol,
    input wire [7:0] backend_raw_code,
    input wire stage1_dither_positive, stage2_dither_positive,
    output wire valid_out,
    output wire [11:0] final_code
);
    two_stage_adaptive_exact_candidate_a calibration (
        .clk(clk), .reset(reset), .valid_in(valid_in),
        .stage1_symbol(stage1_symbol), .stage2_symbol(stage2_symbol),
        .backend_raw_code(backend_raw_code),
        .stage1_dither_positive(stage1_dither_positive),
        .stage2_dither_positive(stage2_dither_positive),
        .valid_out(valid_out), .final_code(final_code)
    );
endmodule

