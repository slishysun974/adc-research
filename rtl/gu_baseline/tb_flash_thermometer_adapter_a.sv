// Exhaustive candidate-A adapter check; no silicon encoding is inferred.
module tb_flash_thermometer_adapter_a;
    reg [7:0] raw_d;
    wire signed [3:0] q;
    wire valid;
    integer code;
    integer count;
    integer expected_q;
    reg expected_valid;

    flash_thermometer_adapter_a dut (
        .raw_d(raw_d), .q(q), .valid(valid)
    );

    initial begin
        for (code = 0; code < 256; code = code + 1) begin
            raw_d = code[7:0];
            expected_valid = 1'b0;
            expected_q = 0;
            for (count = 0; count <= 8; count = count + 1) begin
                if (code == ((1 << count) - 1)) begin
                    expected_valid = 1'b1;
                    expected_q = count - 4;
                end
            end
            #1;
            if (valid !== expected_valid || q !== expected_q[3:0])
                $fatal(1, "adapter mismatch for raw_d=%02h", raw_d);
        end
        $display("flash_thermometer_adapter_a all 256 inputs passed");
        $finish;
    end
endmodule
