// Candidate-A, one conversion and one calibration stage.
// Inputs are already aligned digital learning output and dither copies in Q3
// integer codes. The three thresholds use the same Q3 code unit as the output.
// The 32-bit products are raw Q6 integers, before hardware rounding or sums.
// GATE_ON_EQUAL=1 follows OJSSCS Eq. (7); Fig. 10 depicts strict > instead.
// This block does not infer decimation, channel pooling, or coefficient timing.
module gated_product_candidate_a #(
    parameter bit GATE_ON_EQUAL = 1'b1
) (
    input  logic               valid_in,
    input  logic signed [15:0] learning_output_q3,
    input  logic signed [15:0] dither_copy_q3,
    input  logic        [16:0] lower1_q3,
    input  logic        [16:0] lower2_q3,
    input  logic        [16:0] lower3_q3,
    output logic        [3:0]  gate,
    output logic signed [31:0] product0_q6,
    output logic signed [31:0] product1_q6,
    output logic signed [31:0] product2_q6,
    output logic signed [31:0] product3_q6
);
    logic signed [16:0] output_extended;
    logic        [16:0] magnitude_q3;
    logic signed [31:0] output_wide;
    logic signed [31:0] dither_wide;
    logic signed [31:0] product_wide;

    always @* begin
        output_extended = $signed({learning_output_q3[15], learning_output_q3});
        if (output_extended < 0)
            magnitude_q3 = $unsigned(-output_extended);
        else
            magnitude_q3 = $unsigned(output_extended);

        output_wide = $signed({{16{learning_output_q3[15]}}, learning_output_q3});
        dither_wide = $signed({{16{dither_copy_q3[15]}}, dither_copy_q3});
        product_wide = output_wide * dither_wide;

        gate = 4'b0000;
        if (valid_in) begin
            gate[0] = 1'b1;
            if (GATE_ON_EQUAL) begin
                gate[1] = magnitude_q3 >= lower1_q3;
                gate[2] = magnitude_q3 >= lower2_q3;
                gate[3] = magnitude_q3 >= lower3_q3;
            end else begin
                gate[1] = magnitude_q3 > lower1_q3;
                gate[2] = magnitude_q3 > lower2_q3;
                gate[3] = magnitude_q3 > lower3_q3;
            end
        end

        product0_q6 = gate[0] ? product_wide : 32'sd0;
        product1_q6 = gate[1] ? product_wide : 32'sd0;
        product2_q6 = gate[2] ? product_wide : 32'sd0;
        product3_q6 = gate[3] ? product_wide : 32'sd0;
    end
endmodule
