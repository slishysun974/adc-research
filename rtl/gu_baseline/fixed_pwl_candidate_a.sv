// Four-slice fixed PWL correction for one Gu candidate stage.
// Q3 signed input, unsigned Q1.10 coefficients, Q3 signed output.
// The rounding and negative-full-scale rules match fixed_pwl.correct_fixed
// with nearest_even, after_coefficient_sum, and extend_last_slice.
// This module does not infer silicon widths, saturation, or coefficient timing.
module fixed_pwl_candidate_a #(
    parameter integer SLICE_WIDTH_Q3 = 1024
) (
    input  logic               valid_in,
    input  logic signed [15:0] raw_q3,
    input  logic        [10:0] coefficient0_q10,
    input  logic        [10:0] coefficient1_q10,
    input  logic        [10:0] coefficient2_q10,
    input  logic        [10:0] coefficient3_q10,
    output logic               valid_out,
    output logic        [1:0]  slice_index,
    output logic signed [16:0] corrected_q3
);
    localparam integer FULL_SCALE_Q3 = 4 * SLICE_WIDTH_Q3;

    logic signed [31:0] raw_wide;
    logic        [31:0] magnitude_q3;
    logic        [31:0] local_q3;
    logic        [10:0] selected_coefficient_q10;
    logic        [12:0] preceding_coefficient_sum_q10;
    logic        [31:0] product_wide;
    logic        [31:0] offset_wide;
    logic        [31:0] corrected_magnitude_q3;
    logic signed [31:0] corrected_wide;

    function [31:0] round_nearest_even_q10;
        input [31:0] wide;
        reg [31:0] quotient;
        reg [9:0] remainder;
        begin
            quotient = wide >> 10;
            remainder = wide[9:0];
            if ((remainder > 10'd512) ||
                ((remainder == 10'd512) && quotient[0]))
                round_nearest_even_q10 = quotient + 32'd1;
            else
                round_nearest_even_q10 = quotient;
        end
    endfunction

    // Icarus 10.3 accepts always @* for this pure combinational block.
    always @* begin
        raw_wide = {{16{raw_q3[15]}}, raw_q3};
        if (raw_wide < 0)
            magnitude_q3 = -raw_wide;
        else
            magnitude_q3 = raw_wide;

        valid_out = valid_in &&
            (raw_wide >= -FULL_SCALE_Q3) &&
            (raw_wide < FULL_SCALE_Q3);
        slice_index = 2'd0;
        local_q3 = 32'd0;
        selected_coefficient_q10 = 11'd0;
        preceding_coefficient_sum_q10 = 13'd0;
        product_wide = 32'd0;
        offset_wide = 32'd0;
        corrected_magnitude_q3 = 32'd0;
        corrected_wide = 32'sd0;
        corrected_q3 = 17'sd0;

        if (valid_out) begin
            if (magnitude_q3 < SLICE_WIDTH_Q3) begin
                slice_index = 2'd0;
                local_q3 = magnitude_q3;
                selected_coefficient_q10 = coefficient0_q10;
            end else if (magnitude_q3 < 2 * SLICE_WIDTH_Q3) begin
                slice_index = 2'd1;
                local_q3 = magnitude_q3 - SLICE_WIDTH_Q3;
                selected_coefficient_q10 = coefficient1_q10;
                preceding_coefficient_sum_q10 = {2'b00, coefficient0_q10};
            end else if (magnitude_q3 < 3 * SLICE_WIDTH_Q3) begin
                slice_index = 2'd2;
                local_q3 = magnitude_q3 - 2 * SLICE_WIDTH_Q3;
                selected_coefficient_q10 = coefficient2_q10;
                preceding_coefficient_sum_q10 =
                    {2'b00, coefficient0_q10} +
                    {2'b00, coefficient1_q10};
            end else begin
                // Includes raw_q3 == -FULL_SCALE_Q3: local_q3 == width.
                slice_index = 2'd3;
                local_q3 = magnitude_q3 - 3 * SLICE_WIDTH_Q3;
                selected_coefficient_q10 = coefficient3_q10;
                preceding_coefficient_sum_q10 =
                    {2'b00, coefficient0_q10} +
                    {2'b00, coefficient1_q10} +
                    {2'b00, coefficient2_q10};
            end

            product_wide = local_q3 * selected_coefficient_q10;
            offset_wide = SLICE_WIDTH_Q3 * preceding_coefficient_sum_q10;
            corrected_magnitude_q3 =
                round_nearest_even_q10(offset_wide) +
                round_nearest_even_q10(product_wide);
            if (raw_wide < 0)
                corrected_wide = -$signed(corrected_magnitude_q3);
            else
                corrected_wide = $signed(corrected_magnitude_q3);
            corrected_q3 = corrected_wide[16:0];
        end
    end
endmodule
