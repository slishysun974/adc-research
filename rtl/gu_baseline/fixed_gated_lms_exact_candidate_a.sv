// Exact specialization of the EXP-032 bank for the reviewed top-level domain.
// This interface takes only the dither polarity: arbitrary 16-bit dithers are
// deliberately unsupported. REDUCED_SHIFT=4/6 means D=512/128 respectively.
// Preconditions: coefficients in [0,2047], valid Y1 in [-8700,8698],
// valid Y2 in [-2175,2159]. See CANDIDATE_A_EXACT_UPDATE_ARITHMETIC_V1.md.
module fixed_gated_lms_exact_candidate_a #(
    parameter integer SLICE_WIDTH_Q3 = 1024,
    parameter integer REDUCED_SHIFT = 4,
    // Default preserves the original per-conversion interface. In the
    // multicycle engine, compute gates/deltas continuously but write only at
    // commit; gating valid_in late would put the divider on a one-cycle path.
    parameter integer EXTERNAL_COMMIT = 0,
    // The multicycle engine supplies the same signed integer requests after
    // serial division. Zero requests preserve invalid/disabled coordinates.
    parameter integer EXTERNAL_DELTA = 0
) (
    input  logic               clk, reset, valid_in,
    input  logic               commit_enable,
    input  logic signed [14:0]  delta0, delta1, delta2, delta3,
    input  logic signed [14:0] learning_output_q3,
    input  logic               dither_positive,
    output logic        [3:0]  gate,
    output logic        [10:0] coefficient0_q10, coefficient1_q10,
    output logic        [10:0] coefficient2_q10, coefficient3_q10,
    output logic        [22:0] accumulator0_q22, accumulator1_q22,
    output logic        [22:0] accumulator2_q22, accumulator3_q22
);
    localparam logic [22:0] UNITY_Q22 = 23'd4194304;
    localparam logic [22:0] MAXIMUM_Q22 = 23'd8384512;
    logic [16:0] lower1_q3, lower2_q3, lower3_q3;
    logic [15:0] learning_magnitude_q3;

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

    function signed [14:0] requested_delta;
        input signed [14:0] learning;
        input positive;
        input [3:0] step_numerator;
        reg signed [21:0] scaled_learning;
        reg signed [21:0] numerator;
        reg [20:0] magnitude;
        reg [20:0] biased_magnitude;
        reg [13:0] quotient;
        begin
            // Expand BEFORE multiplication, negation and shifting.
            scaled_learning = $signed({{7{learning[14]}}, learning}) *
                              $signed({1'b0, step_numerator});
            numerator = (positive ? -scaled_learning : scaled_learning) <<< REDUCED_SHIFT;
            magnitude = numerator < 0 ? $unsigned(-numerator) : $unsigned(numerator);
            biased_magnitude = magnitude + 21'd62;
            quotient = biased_magnitude / 21'd125;
            requested_delta = numerator < 0 ?
                -$signed({1'b0, quotient}) : $signed({1'b0, quotient});
        end
    endfunction

    function [22:0] add_delta;
        input [22:0] accumulator;
        input signed [14:0] requested;
        reg signed [24:0] sum;
        begin
            sum = $signed({2'b00, accumulator}) +
                  $signed({{10{requested[14]}}, requested});
            if (sum < 0)
                add_delta = 23'd0;
            else if (sum > 25'sd8384512)
                add_delta = MAXIMUM_Q22;
            else
                add_delta = sum[22:0];
        end
    endfunction

    function [22:0] updated_accumulator;
        input [22:0] accumulator;
        input signed [14:0] learning;
        input positive;
        input [3:0] step_numerator;
        input enabled;
        begin
            updated_accumulator = add_delta(accumulator,
                enabled ? requested_delta(learning, positive, step_numerator) : 15'sd0);
        end
    endfunction

    always @* begin
        coefficient0_q10 = export_q10(accumulator0_q22);
        coefficient1_q10 = export_q10(accumulator1_q22);
        coefficient2_q10 = export_q10(accumulator2_q22);
        coefficient3_q10 = export_q10(accumulator3_q22);
        lower1_q3 = threshold_q3({2'b00, coefficient0_q10});
        lower2_q3 = threshold_q3({2'b00, coefficient0_q10} + {2'b00, coefficient1_q10});
        lower3_q3 = threshold_q3({2'b00, coefficient0_q10} +
            {2'b00, coefficient1_q10} + {2'b00, coefficient2_q10});
        learning_magnitude_q3 = learning_output_q3 < 0 ?
            $unsigned(-$signed({learning_output_q3[14], learning_output_q3})) :
            $unsigned({1'b0, learning_output_q3});
        gate = 4'b0000;
        if (valid_in) begin
            gate[0] = 1'b1;
            gate[1] = {1'b0, learning_magnitude_q3} >= lower1_q3;
            gate[2] = {1'b0, learning_magnitude_q3} >= lower2_q3;
            gate[3] = {1'b0, learning_magnitude_q3} >= lower3_q3;
        end
    end

    always @(posedge clk) begin
        if (reset) begin
            accumulator0_q22 <= UNITY_Q22;
            accumulator1_q22 <= UNITY_Q22;
            accumulator2_q22 <= UNITY_Q22;
            accumulator3_q22 <= UNITY_Q22;
        end else if ((EXTERNAL_DELTA || valid_in) && (!EXTERNAL_COMMIT || commit_enable)) begin
            if (EXTERNAL_DELTA) begin
                accumulator0_q22 <= add_delta(accumulator0_q22, delta0);
                accumulator1_q22 <= add_delta(accumulator1_q22, delta1);
                accumulator2_q22 <= add_delta(accumulator2_q22, delta2);
                accumulator3_q22 <= add_delta(accumulator3_q22, delta3);
            end else begin
                accumulator0_q22 <= updated_accumulator(accumulator0_q22, learning_output_q3, dither_positive, 4'd1, gate[0]);
                accumulator1_q22 <= updated_accumulator(accumulator1_q22, learning_output_q3, dither_positive, 4'd3, gate[1]);
                accumulator2_q22 <= updated_accumulator(accumulator2_q22, learning_output_q3, dither_positive, 4'd6, gate[2]);
                accumulator3_q22 <= updated_accumulator(accumulator3_q22, learning_output_q3, dither_positive, 4'd12, gate[3]);
            end
        end
    end
endmodule
