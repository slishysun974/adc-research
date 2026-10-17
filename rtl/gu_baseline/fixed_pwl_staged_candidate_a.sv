// Four register boundaries for the existing Q3/Q1.10 PWL arithmetic.
// enable_in is a transaction token; invalid data still produces done_out.
// A token sampled at E0 produces done/data at E3. No coefficient update here.
module fixed_pwl_staged_candidate_a #(
    parameter integer SLICE_WIDTH_Q3 = 1024
) (
    input wire clk, reset, enable_in, valid_in,
    input wire signed [15:0] raw_q3,
    input wire [10:0] coefficient0_q10, coefficient1_q10,
    input wire [10:0] coefficient2_q10, coefficient3_q10,
    output reg done_out, valid_out,
    output reg signed [16:0] corrected_q3
);
    localparam integer FULL_SCALE_Q3 = 4 * SLICE_WIDTH_Q3;
    wire signed [31:0] raw_wide = {{16{raw_q3[15]}},raw_q3};
    wire [31:0] magnitude = raw_wide < 0 ? -raw_wide : raw_wide;
    reg [31:0] local_value;
    reg [10:0] selected;
    reg [12:0] prefix;
    reg [10:0] local_p0, coefficient_p0;
    reg [12:0] prefix_p0;
    reg negative_p0, negative_p1, negative_p2;
    reg token_p0, token_p1, token_p2;
    reg valid_p0, valid_p1, valid_p2;
    reg [21:0] product_p1;
    reg [12:0] offset_p1;
    reg [13:0] magnitude_p2;
    (* use_dsp = "yes" *) wire [21:0] product_value = local_p0 * coefficient_p0;

    function [12:0] round_q10;
        input [31:0] value;
        reg [31:0] quotient;
        begin
            quotient = value >> 10;
            if (value[9:0] > 10'd512 || (value[9:0] == 10'd512 && quotient[0]))
                quotient = quotient + 1'b1;
            round_q10 = quotient[12:0];
        end
    endfunction

    always @* begin
        local_value = magnitude;
        selected = coefficient0_q10;
        prefix = 0;
        if (magnitude >= 3 * SLICE_WIDTH_Q3) begin
            local_value = magnitude - 3 * SLICE_WIDTH_Q3;
            selected = coefficient3_q10;
            prefix = {2'b0,coefficient0_q10} + {2'b0,coefficient1_q10} + {2'b0,coefficient2_q10};
        end else if (magnitude >= 2 * SLICE_WIDTH_Q3) begin
            local_value = magnitude - 2 * SLICE_WIDTH_Q3;
            selected = coefficient2_q10;
            prefix = {2'b0,coefficient0_q10} + {2'b0,coefficient1_q10};
        end else if (magnitude >= SLICE_WIDTH_Q3) begin
            local_value = magnitude - SLICE_WIDTH_Q3;
            selected = coefficient1_q10;
            prefix = {2'b0,coefficient0_q10};
        end
    end

    always @(posedge clk) begin
        if (reset) begin
            local_p0 <= 0; coefficient_p0 <= 0; prefix_p0 <= 0;
            negative_p0 <= 0; negative_p1 <= 0; negative_p2 <= 0;
            token_p0 <= 0; token_p1 <= 0; token_p2 <= 0; done_out <= 0;
            valid_p0 <= 0; valid_p1 <= 0; valid_p2 <= 0; valid_out <= 0;
            product_p1 <= 0; offset_p1 <= 0; magnitude_p2 <= 0; corrected_q3 <= 0;
        end else begin
            local_p0 <= local_value[10:0];
            coefficient_p0 <= selected;
            prefix_p0 <= prefix;
            negative_p0 <= raw_q3[15];
            token_p0 <= enable_in;
            valid_p0 <= enable_in && valid_in && raw_wide >= -FULL_SCALE_Q3 && raw_wide < FULL_SCALE_Q3;
            product_p1 <= product_value;
            offset_p1 <= round_q10(SLICE_WIDTH_Q3 * prefix_p0);
            token_p1 <= token_p0; valid_p1 <= valid_p0; negative_p1 <= negative_p0;
            magnitude_p2 <= {1'b0,round_q10({10'b0,product_p1})} + {1'b0,offset_p1};
            token_p2 <= token_p1; valid_p2 <= valid_p1; negative_p2 <= negative_p1;
            done_out <= token_p2;
            valid_out <= valid_p2;
            corrected_q3 <= !valid_p2 ? 17'sd0 : negative_p2 ?
                -$signed({3'b0,magnitude_p2}) : $signed({3'b0,magnitude_p2});
        end
    end
endmodule
