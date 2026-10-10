// Candidate-A digital adapter, not a reconstruction of the silicon encoder.
// D[0] corresponds to the lowest ordered threshold. A high bit means that
// threshold has been reached. q is a signed four-bit value in [-4, 4].
// Invalid thermometer words produce valid=0 and q=0; downstream logic must
// use valid and must not treat q=0 alone as a legitimate decoded sample.
module flash_thermometer_adapter_a (
    input  logic [7:0] raw_d,
    output logic signed [3:0] q,
    output logic valid
);
    always @* begin
        valid = 1'b1;
        case (raw_d)
            8'h00: q = -4'sd4;
            8'h01: q = -4'sd3;
            8'h03: q = -4'sd2;
            8'h07: q = -4'sd1;
            8'h0f: q =  4'sd0;
            8'h1f: q =  4'sd1;
            8'h3f: q =  4'sd2;
            8'h7f: q =  4'sd3;
            8'hff: q =  4'sd4;
            default: begin
                q = 4'sd0;
                valid = 1'b0;
            end
        endcase
    end
endmodule
