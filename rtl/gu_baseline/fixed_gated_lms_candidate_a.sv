// One conversion per clock, with the current Q1.10 coefficients used for
// correction and gating. The Q22 accumulators update at the rising edge;
// exported coefficients therefore take effect on the following conversion.
// This is a research timing candidate, not the published chip's decimator.
module fixed_gated_lms_candidate_a #(
    parameter integer SLICE_WIDTH_Q3 = 1024,
    parameter integer DELTA_DENOMINATOR = 4000
) (
    input  logic               clk,
    input  logic               reset,
    input  logic               valid_in,
    input  logic signed [15:0] learning_output_q3,
    input  logic signed [15:0] dither_copy_q3,
    output logic        [3:0]  gate,
    output logic        [10:0] coefficient0_q10,
    output logic        [10:0] coefficient1_q10,
    output logic        [10:0] coefficient2_q10,
    output logic        [10:0] coefficient3_q10,
    output logic        [22:0] accumulator0_q22,
    output logic        [22:0] accumulator1_q22,
    output logic        [22:0] accumulator2_q22,
    output logic        [22:0] accumulator3_q22
);
    localparam logic [22:0] UNITY_Q22 = 23'd4194304;
    localparam logic [22:0] MAXIMUM_Q22 = 23'd8384512;
    logic [16:0] lower1_q3, lower2_q3, lower3_q3;
    logic signed [31:0] product0_q6, product1_q6;
    logic signed [31:0] product2_q6, product3_q6;

    function [10:0] export_q10;
        input [22:0] accumulator;
        reg [11:0] quotient;
        reg [11:0] remainder;
        begin
            quotient = {1'b0, accumulator[22:12]};
            remainder = accumulator[11:0];
            if ((remainder > 12'd2048) ||
                ((remainder == 12'd2048) && quotient[0]))
                quotient = quotient + 12'd1;
            export_q10 = quotient > 12'd2047 ? 11'd2047 : quotient[10:0];
        end
    endfunction

    function [16:0] threshold_q3;
        input [12:0] coefficient_sum;
        reg [31:0] wide;
        reg [31:0] quotient;
        reg [9:0] remainder;
        begin
            wide = coefficient_sum * SLICE_WIDTH_Q3;
            quotient = wide >> 10;
            remainder = wide[9:0];
            if ((remainder > 10'd512) ||
                ((remainder == 10'd512) && quotient[0]))
                quotient = quotient + 32'd1;
            threshold_q3 = quotient[16:0];
        end
    endfunction

    // Signed, exact division by the selected positive rational denominator.
    // Magnitude-first rounding makes negative half ties symmetric.
    function signed [63:0] round_divide_even;
        input signed [63:0] numerator;
        reg [63:0] magnitude;
        reg [63:0] quotient;
        reg [63:0] remainder;
        begin
            magnitude = numerator < 0 ? $unsigned(-numerator) : $unsigned(numerator);
            quotient = magnitude / DELTA_DENOMINATOR;
            remainder = magnitude % DELTA_DENOMINATOR;
            if ((2 * remainder > DELTA_DENOMINATOR) ||
                ((2 * remainder == DELTA_DENOMINATOR) && quotient[0]))
                quotient = quotient + 64'd1;
            round_divide_even = numerator < 0 ? -$signed(quotient) : $signed(quotient);
        end
    endfunction

    function [22:0] updated_accumulator;
        input [22:0] accumulator;
        input signed [31:0] product_q6;
        input integer step_numerator;
        reg signed [63:0] requested;
        reg signed [63:0] sum;
        begin
            requested = round_divide_even(
                -$signed({{32{product_q6[31]}}, product_q6}) * step_numerator
            );
            sum = $signed({1'b0, accumulator}) + requested;
            if (sum < 0)
                updated_accumulator = 23'd0;
            else if (sum > $signed({1'b0, MAXIMUM_Q22}))
                updated_accumulator = MAXIMUM_Q22;
            else
                updated_accumulator = sum[22:0];
        end
    endfunction

    always @* begin
        coefficient0_q10 = export_q10(accumulator0_q22);
        coefficient1_q10 = export_q10(accumulator1_q22);
        coefficient2_q10 = export_q10(accumulator2_q22);
        coefficient3_q10 = export_q10(accumulator3_q22);
        lower1_q3 = threshold_q3({2'b00, coefficient0_q10});
        lower2_q3 = threshold_q3(
            {2'b00, coefficient0_q10} + {2'b00, coefficient1_q10}
        );
        lower3_q3 = threshold_q3(
            {2'b00, coefficient0_q10} +
            {2'b00, coefficient1_q10} + {2'b00, coefficient2_q10}
        );
    end

    gated_product_candidate_a #(.GATE_ON_EQUAL(1'b1)) products (
        .valid_in(valid_in),
        .learning_output_q3(learning_output_q3),
        .dither_copy_q3(dither_copy_q3),
        .lower1_q3(lower1_q3),
        .lower2_q3(lower2_q3),
        .lower3_q3(lower3_q3),
        .gate(gate),
        .product0_q6(product0_q6),
        .product1_q6(product1_q6),
        .product2_q6(product2_q6),
        .product3_q6(product3_q6)
    );

    always @(posedge clk) begin
        if (reset) begin
            accumulator0_q22 <= UNITY_Q22;
            accumulator1_q22 <= UNITY_Q22;
            accumulator2_q22 <= UNITY_Q22;
            accumulator3_q22 <= UNITY_Q22;
        end else if (valid_in) begin
            accumulator0_q22 <= updated_accumulator(accumulator0_q22, product0_q6, 1);
            accumulator1_q22 <= updated_accumulator(accumulator1_q22, product1_q6, 3);
            accumulator2_q22 <= updated_accumulator(accumulator2_q22, product2_q6, 6);
            accumulator3_q22 <= updated_accumulator(accumulator3_q22, product3_q6, 12);
        end
    end
endmodule
