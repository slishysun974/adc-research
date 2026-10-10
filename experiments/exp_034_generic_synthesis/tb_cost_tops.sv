// Reuse the reviewed EXP-031/032 Python records at the code-only boundary.
// The online branch inserts idle clocks and resets/replays a directed prefix.
module tb_gu_cost_top;
    parameter integer ONLINE = 0;
    parameter integer FIRST_PASS_LIMIT = 1000000;
    parameter integer RESET_PASS_LIMIT = 128;
    reg clk = 0, reset = 1, valid_in = 0;
    reg signed [3:0] stage1_symbol = 0, stage2_symbol = 0;
    reg [7:0] backend_raw_code = 0;
    reg stage1_dither_positive = 0, stage2_dither_positive = 0;
    reg [10:0] stage1_coefficient0_q10, stage1_coefficient1_q10;
    reg [10:0] stage1_coefficient2_q10, stage1_coefficient3_q10;
    reg [10:0] stage2_coefficient0_q10, stage2_coefficient1_q10;
    reg [10:0] stage2_coefficient2_q10, stage2_coefficient3_q10;
    wire valid_out;
    wire [11:0] final_code;
    integer file_handle, scanned, checked, pass_index, pass_count, pass_limit;
    integer q1, q2, backend, d1, d2, expected_valid, expected_code;
    integer a0, a1, a2, a3, b0, b1, b2, b3;
    integer ignored0, ignored1, ignored2, ignored3, ignored4, ignored5;
    reg [1023:0] vector_path;

    generate
        if (ONLINE) begin : online_branch
            gu_online_cost_top dut (
                .clk(clk), .reset(reset), .valid_in(valid_in),
                .stage1_symbol(stage1_symbol), .stage2_symbol(stage2_symbol),
                .backend_raw_code(backend_raw_code),
                .stage1_dither_positive(stage1_dither_positive),
                .stage2_dither_positive(stage2_dither_positive),
                .valid_out(valid_out), .final_code(final_code)
            );
        end else begin : frozen_branch
            gu_frozen_cost_top dut (
                .valid_in(valid_in),
                .stage1_symbol(stage1_symbol), .stage2_symbol(stage2_symbol),
                .backend_raw_code(backend_raw_code),
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
                .valid_out(valid_out), .final_code(final_code)
            );
        end
    endgenerate

    task check_code;
        begin
            if (valid_out !== expected_valid[0] ||
                final_code !== expected_code[11:0])
                $fatal(1, "code-only mismatch online=%0d pass=%0d vector=%0d valid=%0d/%0d code=%0d/%0d",
                    ONLINE, pass_index, pass_count, valid_out, expected_valid,
                    final_code, expected_code);
        end
    endtask

    initial begin
        if (!$value$plusargs("VECTORS=%s", vector_path))
            $fatal(1, "VECTORS is required");
        checked = 0;
        for (pass_index = 0; pass_index < (ONLINE ? 2 : 1); pass_index = pass_index + 1) begin
            file_handle = $fopen(vector_path, "r");
            if (!file_handle) $fatal(1, "cannot open vectors");
            pass_count = 0;
            pass_limit = pass_index == 0 ? FIRST_PASS_LIMIT : RESET_PASS_LIMIT;
            if (ONLINE) begin
                valid_in = 0; reset = 1; clk = 0;
                #2 clk = 1;
                #2 clk = 0; reset = 0;
            end
            while (!$feof(file_handle) && pass_count < pass_limit) begin
                if (ONLINE)
                    scanned = $fscanf(file_handle,
                        "%d %d %d %d %d %d %d %d %d %d %d %d %d %d %d %d %d %d %d\n",
                        q1, q2, backend, d1, d2, expected_valid, expected_code,
                        ignored0, ignored1, ignored2, ignored3,
                        a0, a1, a2, a3, b0, b1, b2, b3);
                else
                    scanned = $fscanf(file_handle,
                        "%d %d %d %d %d %d %d %d %d %d %d %d %d %d %d %d %d %d %d %d %d\n",
                        q1, q2, backend, d1, d2, a0, a1, a2, a3, b0, b1, b2, b3,
                        expected_valid, ignored0, ignored1, ignored2, ignored3,
                        expected_code, ignored4, ignored5);
                if (scanned != -1 && scanned != (ONLINE ? 19 : 21))
                    $fatal(1, "malformed record at %0d", pass_count);
                if (scanned == (ONLINE ? 19 : 21)) begin
                    // The golden sequence has no idle updates. Inserting idle
                    // cycles checks that valid_in=0 leaves future behavior intact.
                    if (ONLINE) begin
                        valid_in = 0;
                        #2;
                        if (valid_out !== 0 || final_code !== 0)
                            $fatal(1, "idle output must be invalid and zero");
                        clk = 1;
                        #2 clk = 0;
                    end
                    valid_in = 1;
                    stage1_symbol = q1; stage2_symbol = q2;
                    backend_raw_code = backend;
                    stage1_dither_positive = d1; stage2_dither_positive = d2;
                    stage1_coefficient0_q10 = a0; stage1_coefficient1_q10 = a1;
                    stage1_coefficient2_q10 = a2; stage1_coefficient3_q10 = a3;
                    stage2_coefficient0_q10 = b0; stage2_coefficient1_q10 = b1;
                    stage2_coefficient2_q10 = b2; stage2_coefficient3_q10 = b3;
                    #2;
                    check_code;
                    if (ONLINE) begin
                        clk = 1;
                        #2 clk = 0;
                    end
                    pass_count = pass_count + 1;
                    checked = checked + 1;
                    if (pass_count % 256 == 0 ||
                        (pass_count <= 128 && pass_count % 16 == 0)) begin
                        $display("progress online=%0d pass=%0d records=%0d time=%0t",
                                 ONLINE, pass_index, pass_count, $time);
                        $fflush();
                    end
                end
            end
            if (pass_count == 0) $fatal(1, "empty vector file");
            $fclose(file_handle);
        end
        valid_in = 0;
        #2;
        if (valid_out !== 0 || final_code !== 0)
            $fatal(1, "invalid input must clear outputs");
        valid_in = 1;
        stage1_symbol = 5;
        #2;
        if (valid_out !== 0 || final_code !== 0)
            $fatal(1, "invalid first-stage word must clear outputs");
        stage1_symbol = 0; stage2_symbol = -5;
        #2;
        if (valid_out !== 0 || final_code !== 0)
            $fatal(1, "invalid second-stage word must clear outputs");
        $display("gu_cost_top online=%0d %0d Python code records passed", ONLINE, checked);
        $finish;
    end
endmodule
