// Exact 22-bit numerator arithmetic, separated across four register edges.
// A token accepted at T produces {negative_out,biased_out} at T+3.
// Both the signed overflow and the final 21-bit bias wrap match the original
// biased_numerator function; this is not an unbounded-integer replacement.
module fixed_request_seed_staged_candidate_a #(
    parameter [3:0] STEP_NUMERATOR = 4'd1,
    parameter integer REDUCED_SHIFT = 4
) (
    input wire clk, reset, enable_in,
    input wire signed [14:0] learning_q3,
    input wire dither_positive,
    output reg done_out, negative_out,
    output reg [20:0] biased_out
);
    reg [2:0] tokens;
    reg signed [21:0] product_registered, numerator_registered;
    reg positive_registered, sign_registered;
    reg [20:0] magnitude_registered;
    always @(posedge clk) begin
        if (reset) begin
            tokens <= 0;
            done_out <= 0;
            product_registered <= 0;
            positive_registered <= 0;
            numerator_registered <= 0;
            magnitude_registered <= 0;
            sign_registered <= 0;
            biased_out <= 0;
            negative_out <= 0;
        end else begin
            tokens <= {tokens[1:0],enable_in};
            done_out <= tokens[2];
            if (enable_in) begin
                product_registered <= $signed({{7{learning_q3[14]}},learning_q3}) *
                                      $signed({1'b0,STEP_NUMERATOR});
                positive_registered <= dither_positive;
            end
            if (tokens[0])
                numerator_registered <= (positive_registered ? -product_registered :
                                          product_registered) <<< REDUCED_SHIFT;
            if (tokens[1]) begin
                // Low 21 bits of abs(signed22), including signed minimum.
                magnitude_registered <= numerator_registered[21] ?
                    (21'd0 - numerator_registered[20:0]) : numerator_registered[20:0];
                sign_registered <= numerator_registered[21];
            end
            if (tokens[2]) begin
                biased_out <= magnitude_registered + 21'd62;
                negative_out <= sign_registered;
            end
        end
    end
endmodule
