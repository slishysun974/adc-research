// Compare frozen-coefficient two-stage RTL with Python-generated digital words.
module tb_two_stage_fixed_candidate_a;
    reg valid_in;
    reg signed [3:0] stage1_symbol;
    reg signed [3:0] stage2_symbol;
    reg [7:0] backend_raw_code;
    reg stage1_dither_positive;
    reg stage2_dither_positive;
    reg [10:0] stage1_coefficient0_q10;
    reg [10:0] stage1_coefficient1_q10;
    reg [10:0] stage1_coefficient2_q10;
    reg [10:0] stage1_coefficient3_q10;
    reg [10:0] stage2_coefficient0_q10;
    reg [10:0] stage2_coefficient1_q10;
    reg [10:0] stage2_coefficient2_q10;
    reg [10:0] stage2_coefficient3_q10;
    wire valid_out;
    wire signed [16:0] stage2_corrected_q3;
    wire signed [15:0] stage1_raw_q3;
    wire signed [16:0] stage1_corrected_q3;
    wire [15:0] clipped_output_q3;
    wire [11:0] final_code;
    wire saturated_low;
    wire saturated_high;

    reg [1023:0] vector_path;
    integer file_handle;
    integer scanned;
    integer checked;
    integer q1, q2, backend, d1, d2;
    integer a0, a1, a2, a3, b0, b1, b2, b3;
    integer expected_valid, expected_stage2, expected_stage1_raw;
    integer expected_stage1, expected_output, expected_final;
    integer expected_low, expected_high;

    two_stage_fixed_candidate_a dut (
        .valid_in(valid_in), .stage1_symbol(stage1_symbol),
        .stage2_symbol(stage2_symbol), .backend_raw_code(backend_raw_code),
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
        .valid_out(valid_out), .stage2_corrected_q3(stage2_corrected_q3),
        .stage1_raw_q3(stage1_raw_q3),
        .stage1_corrected_q3(stage1_corrected_q3),
        .clipped_output_q3(clipped_output_q3), .final_code(final_code),
        .saturated_low(saturated_low), .saturated_high(saturated_high)
    );

    initial begin
        if (!$value$plusargs("VECTORS=%s", vector_path))
            $fatal(1, "VECTORS=<path> is required");
        file_handle = $fopen(vector_path, "r");
        if (file_handle == 0)
            $fatal(1, "cannot open vector file");
        checked = 0;
        while (!$feof(file_handle)) begin
            scanned = $fscanf(
                file_handle,
                "%d %d %d %d %d %d %d %d %d %d %d %d %d %d %d %d %d %d %d %d %d\n",
                q1, q2, backend, d1, d2,
                a0, a1, a2, a3, b0, b1, b2, b3,
                expected_valid, expected_stage2, expected_stage1_raw,
                expected_stage1, expected_output, expected_final,
                expected_low, expected_high
            );
            if (scanned == 21) begin
                valid_in = 1'b1;
                stage1_symbol = q1;
                stage2_symbol = q2;
                backend_raw_code = backend;
                stage1_dither_positive = d1;
                stage2_dither_positive = d2;
                stage1_coefficient0_q10 = a0;
                stage1_coefficient1_q10 = a1;
                stage1_coefficient2_q10 = a2;
                stage1_coefficient3_q10 = a3;
                stage2_coefficient0_q10 = b0;
                stage2_coefficient1_q10 = b1;
                stage2_coefficient2_q10 = b2;
                stage2_coefficient3_q10 = b3;
                #1;
                if (valid_out !== expected_valid[0] ||
                    stage2_corrected_q3 !== expected_stage2[16:0] ||
                    stage1_raw_q3 !== expected_stage1_raw[15:0] ||
                    stage1_corrected_q3 !== expected_stage1[16:0] ||
                    clipped_output_q3 !== expected_output[15:0] ||
                    final_code !== expected_final[11:0] ||
                    saturated_low !== expected_low[0] ||
                    saturated_high !== expected_high[0])
                    $fatal(1, "cascade mismatch at vector %0d", checked);
                checked = checked + 1;
            end else if (scanned != -1)
                $fatal(1, "malformed vector after %0d checks", checked);
        end
        $fclose(file_handle);
        valid_in = 1'b0;
        #1;
        if (valid_out !== 1'b0 || final_code !== 12'd0)
            $fatal(1, "invalid input did not clear final code");
        valid_in = 1'b1;
        stage1_symbol = 4'sd5;
        #1;
        if (valid_out !== 1'b0 || final_code !== 12'd0)
            $fatal(1, "invalid stage1 symbol was accepted");
        stage1_symbol = 4'sd0;
        stage2_symbol = -4'sd5;
        #1;
        if (valid_out !== 1'b0 || final_code !== 12'd0)
            $fatal(1, "invalid stage2 symbol was accepted");
        $display("two_stage_fixed_candidate_a %0d oracle vectors passed", checked);
        $finish;
    end
endmodule
