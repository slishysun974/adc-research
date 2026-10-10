// Frozen-coefficient Gu candidate digital cascade. Input symbols are the
// explicit candidate-A q=-4..4 words, not proven silicon bus encodings.
// Uses the default +/-64 and +/-16 code dither copies and Q3/Q1.10 PWL blocks.
// No online update, decimation, or clock timing is represented here.
module two_stage_fixed_candidate_a (
    input  logic               valid_in,
    input  logic signed [3:0]  stage1_symbol,
    input  logic signed [3:0]  stage2_symbol,
    input  logic        [7:0]  backend_raw_code,
    input  logic               stage1_dither_positive,
    input  logic               stage2_dither_positive,
    input  logic        [10:0] stage1_coefficient0_q10,
    input  logic        [10:0] stage1_coefficient1_q10,
    input  logic        [10:0] stage1_coefficient2_q10,
    input  logic        [10:0] stage1_coefficient3_q10,
    input  logic        [10:0] stage2_coefficient0_q10,
    input  logic        [10:0] stage2_coefficient1_q10,
    input  logic        [10:0] stage2_coefficient2_q10,
    input  logic        [10:0] stage2_coefficient3_q10,
    output logic               valid_out,
    output logic signed [16:0] stage2_corrected_q3,
    output logic signed [15:0] stage1_raw_q3,
    output logic signed [16:0] stage1_corrected_q3,
    output logic        [15:0] clipped_output_q3,
    output logic        [11:0] final_code,
    output logic               saturated_low,
    output logic               saturated_high
);
    logic signed [31:0] stage1_symbol_wide;
    logic signed [31:0] stage2_symbol_wide;
    logic signed [31:0] backend_centered_wide;
    logic signed [31:0] stage2_raw_wide;
    logic signed [31:0] stage1_raw_wide;
    logic signed [31:0] stage2_corrected_wide;
    logic signed [31:0] stage1_corrected_wide;
    logic signed [31:0] unclipped_output_wide;
    logic signed [31:0] stage1_dither_q3;
    logic signed [31:0] stage2_dither_q3;
    logic signed [15:0] stage2_raw_q3;
    logic stage2_valid;
    logic stage1_valid;
    logic symbols_valid;
    logic [1:0] unused_stage1_slice;
    logic [1:0] unused_stage2_slice;

    function [11:0] round_nearest_even_q3;
        input [15:0] code_q3;
        reg [15:0] quotient;
        reg [2:0] remainder;
        begin
            quotient = code_q3 >> 3;
            remainder = code_q3[2:0];
            if ((remainder > 3'd4) ||
                ((remainder == 3'd4) && quotient[0]))
                round_nearest_even_q3 = quotient[11:0] + 12'd1;
            else
                round_nearest_even_q3 = quotient[11:0];
        end
    endfunction

    fixed_pwl_candidate_a #(.SLICE_WIDTH_Q3(256)) stage2_pwl (
        .valid_in(valid_in && symbols_valid),
        .raw_q3(stage2_raw_q3),
        .coefficient0_q10(stage2_coefficient0_q10),
        .coefficient1_q10(stage2_coefficient1_q10),
        .coefficient2_q10(stage2_coefficient2_q10),
        .coefficient3_q10(stage2_coefficient3_q10),
        .valid_out(stage2_valid),
        .slice_index(unused_stage2_slice),
        .corrected_q3(stage2_corrected_q3)
    );
    fixed_pwl_candidate_a #(.SLICE_WIDTH_Q3(1024)) stage1_pwl (
        .valid_in(stage2_valid),
        .raw_q3(stage1_raw_q3),
        .coefficient0_q10(stage1_coefficient0_q10),
        .coefficient1_q10(stage1_coefficient1_q10),
        .coefficient2_q10(stage1_coefficient2_q10),
        .coefficient3_q10(stage1_coefficient3_q10),
        .valid_out(stage1_valid),
        .slice_index(unused_stage1_slice),
        .corrected_q3(stage1_corrected_q3)
    );

    always @* begin
        stage1_symbol_wide = {{28{stage1_symbol[3]}}, stage1_symbol};
        stage2_symbol_wide = {{28{stage2_symbol[3]}}, stage2_symbol};
        symbols_valid =
            (stage1_symbol_wide >= -32'sd4) &&
            (stage1_symbol_wide <= 32'sd4) &&
            (stage2_symbol_wide >= -32'sd4) &&
            (stage2_symbol_wide <= 32'sd4);

        backend_centered_wide = $signed({1'b0, backend_raw_code}) - 32'sd128;
        stage2_raw_wide = backend_centered_wide <<< 3;
        stage2_raw_q3 = stage2_raw_wide[15:0];
        stage1_dither_q3 = stage1_dither_positive ? 32'sd512 : -32'sd512;
        stage2_dither_q3 = stage2_dither_positive ? 32'sd128 : -32'sd128;
        stage2_corrected_wide =
            {{15{stage2_corrected_q3[16]}}, stage2_corrected_q3};
        stage1_raw_wide = (stage2_symbol_wide <<< 10) +
            stage2_corrected_wide - stage2_dither_q3;
        stage1_raw_q3 = stage1_raw_wide[15:0];
        stage1_corrected_wide =
            {{15{stage1_corrected_q3[16]}}, stage1_corrected_q3};
        unclipped_output_wide = (stage1_symbol_wide <<< 12) +
            stage1_corrected_wide - stage1_dither_q3 + 32'sd16384;

        valid_out = stage1_valid;
        clipped_output_q3 = 16'd0;
        final_code = 12'd0;
        saturated_low = 1'b0;
        saturated_high = 1'b0;
        if (valid_out) begin
            if (unclipped_output_wide < 0) begin
                saturated_low = 1'b1;
                clipped_output_q3 = 16'd0;
            end else if (unclipped_output_wide > 32'sd32760) begin
                saturated_high = 1'b1;
                clipped_output_q3 = 16'd32760;
            end else
                clipped_output_q3 = unclipped_output_wide[15:0];
            final_code = round_nearest_even_q3(clipped_output_q3);
        end
    end
endmodule
