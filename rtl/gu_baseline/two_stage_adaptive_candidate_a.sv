// Digital five-field candidate: one conversion and one simultaneous LMS
// update for each stage per clock. No four-way extraction is modeled.
module two_stage_adaptive_candidate_a (
    input  logic               clk,
    input  logic               reset,
    input  logic               valid_in,
    input  logic signed [3:0]  stage1_symbol,
    input  logic signed [3:0]  stage2_symbol,
    input  logic        [7:0]  backend_raw_code,
    input  logic               stage1_dither_positive,
    input  logic               stage2_dither_positive,
    output logic               valid_out,
    output logic        [11:0] final_code,
    output logic        [3:0]  stage1_gate,
    output logic        [3:0]  stage2_gate,
    output logic signed [15:0] stage1_learning_q3,
    output logic signed [15:0] stage2_learning_q3,
    output logic        [22:0] stage1_accumulator0_q22,
    output logic        [22:0] stage1_accumulator1_q22,
    output logic        [22:0] stage1_accumulator2_q22,
    output logic        [22:0] stage1_accumulator3_q22,
    output logic        [22:0] stage2_accumulator0_q22,
    output logic        [22:0] stage2_accumulator1_q22,
    output logic        [22:0] stage2_accumulator2_q22,
    output logic        [22:0] stage2_accumulator3_q22
);
    logic [10:0] stage1_coefficient0_q10, stage1_coefficient1_q10;
    logic [10:0] stage1_coefficient2_q10, stage1_coefficient3_q10;
    logic [10:0] stage2_coefficient0_q10, stage2_coefficient1_q10;
    logic [10:0] stage2_coefficient2_q10, stage2_coefficient3_q10;
    logic signed [16:0] stage1_corrected_q3, stage2_corrected_q3;
    logic signed [15:0] unused_stage1_raw_q3;
    logic [15:0] unused_clipped_output_q3;
    logic unused_saturated_low, unused_saturated_high;
    logic signed [31:0] stage1_learning_wide, stage2_learning_wide;

    two_stage_fixed_candidate_a correction (
        .valid_in(valid_in),
        .stage1_symbol(stage1_symbol),
        .stage2_symbol(stage2_symbol),
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
        .valid_out(valid_out),
        .stage2_corrected_q3(stage2_corrected_q3),
        .stage1_raw_q3(unused_stage1_raw_q3),
        .stage1_corrected_q3(stage1_corrected_q3),
        .clipped_output_q3(unused_clipped_output_q3),
        .final_code(final_code),
        .saturated_low(unused_saturated_low),
        .saturated_high(unused_saturated_high)
    );

    always @* begin
        stage1_learning_wide = $signed(stage1_corrected_q3) -
            (stage1_dither_positive ? 32'sd512 : -32'sd512);
        stage2_learning_wide = $signed(stage2_corrected_q3) -
            (stage2_dither_positive ? 32'sd128 : -32'sd128);
        stage1_learning_q3 = stage1_learning_wide[15:0];
        stage2_learning_q3 = stage2_learning_wide[15:0];
    end

    fixed_gated_lms_candidate_a #(
        .SLICE_WIDTH_Q3(1024), .DELTA_DENOMINATOR(4000)
    ) stage1_bank (
        .clk(clk), .reset(reset), .valid_in(valid_out),
        .learning_output_q3(stage1_learning_q3),
        .dither_copy_q3(stage1_dither_positive ? 16'sd512 : -16'sd512),
        .gate(stage1_gate),
        .coefficient0_q10(stage1_coefficient0_q10),
        .coefficient1_q10(stage1_coefficient1_q10),
        .coefficient2_q10(stage1_coefficient2_q10),
        .coefficient3_q10(stage1_coefficient3_q10),
        .accumulator0_q22(stage1_accumulator0_q22),
        .accumulator1_q22(stage1_accumulator1_q22),
        .accumulator2_q22(stage1_accumulator2_q22),
        .accumulator3_q22(stage1_accumulator3_q22)
    );
    fixed_gated_lms_candidate_a #(
        .SLICE_WIDTH_Q3(256), .DELTA_DENOMINATOR(250)
    ) stage2_bank (
        .clk(clk), .reset(reset), .valid_in(valid_out),
        .learning_output_q3(stage2_learning_q3),
        .dither_copy_q3(stage2_dither_positive ? 16'sd128 : -16'sd128),
        .gate(stage2_gate),
        .coefficient0_q10(stage2_coefficient0_q10),
        .coefficient1_q10(stage2_coefficient1_q10),
        .coefficient2_q10(stage2_coefficient2_q10),
        .coefficient3_q10(stage2_coefficient3_q10),
        .accumulator0_q22(stage2_accumulator0_q22),
        .accumulator1_q22(stage2_accumulator1_q22),
        .accumulator2_q22(stage2_accumulator2_q22),
        .accumulator3_q22(stage2_accumulator3_q22)
    );
endmodule
