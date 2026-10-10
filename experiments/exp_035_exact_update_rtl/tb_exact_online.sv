module tb_two_stage_adaptive_exact_candidate_a;
    reg clk, reset, valid_in;
    reg signed [3:0] stage1_symbol, stage2_symbol;
    reg [7:0] backend_raw_code;
    reg stage1_dither_positive, stage2_dither_positive;
    wire valid_out;
    wire [11:0] final_code;
    wire [3:0] stage1_gate, stage2_gate;
    wire signed [15:0] stage1_learning_q3, stage2_learning_q3;
    wire [22:0] a10, a11, a12, a13, a20, a21, a22, a23;
    integer file_handle, read_count, vector_count;
    integer q1, q2, backend, d1, d2, expected_valid, expected_code;
    integer expected_gate1, expected_gate2, expected_learning1, expected_learning2;
    integer e10, e11, e12, e13, e20, e21, e22, e23;
    reg [183:0] idle_state;
    reg [1023:0] vector_path;

    two_stage_adaptive_exact_candidate_a dut (
        .clk(clk), .reset(reset), .valid_in(valid_in),
        .stage1_symbol(stage1_symbol), .stage2_symbol(stage2_symbol),
        .backend_raw_code(backend_raw_code),
        .stage1_dither_positive(stage1_dither_positive),
        .stage2_dither_positive(stage2_dither_positive),
        .valid_out(valid_out), .final_code(final_code),
        .stage1_gate(stage1_gate), .stage2_gate(stage2_gate),
        .stage1_learning_q3(stage1_learning_q3),
        .stage2_learning_q3(stage2_learning_q3),
        .stage1_accumulator0_q22(a10), .stage1_accumulator1_q22(a11),
        .stage1_accumulator2_q22(a12), .stage1_accumulator3_q22(a13),
        .stage2_accumulator0_q22(a20), .stage2_accumulator1_q22(a21),
        .stage2_accumulator2_q22(a22), .stage2_accumulator3_q22(a23)
    );

    initial begin
        if (!$value$plusargs("VECTORS=%s", vector_path))
            $fatal(1, "VECTORS path is required");
        file_handle = $fopen(vector_path, "r");
        if (file_handle == 0)
            $fatal(1, "cannot open vector file");
        clk = 0;
        reset = 1;
        valid_in = 0;
        stage1_symbol = 0;
        stage2_symbol = 0;
        backend_raw_code = 0;
        stage1_dither_positive = 0;
        stage2_dither_positive = 0;
        vector_count = 0;
        #2 clk = 1;
        #1;
        if ({a10,a11,a12,a13,a20,a21,a22,a23} !== {8{23'd4194304}})
            $fatal(1, "reset did not set unity accumulators");
        clk = 0;
        reset = 0;
        while (!$feof(file_handle)) begin
            read_count = $fscanf(file_handle,
                "%d %d %d %d %d %d %d %d %d %d %d %d %d %d %d %d %d %d %d\n",
                q1, q2, backend, d1, d2, expected_valid, expected_code,
                expected_gate1, expected_gate2, expected_learning1,
                expected_learning2, e10, e11, e12, e13, e20, e21, e22, e23);
            if (read_count != -1 && read_count != 19)
                $fatal(1, "malformed vector %0d: read %0d fields", vector_count, read_count);
            if (read_count == 19) begin
            idle_state = {a10,a11,a12,a13,a20,a21,a22,a23};
            valid_in = 0;
            #2;
            if (valid_out !== 0 || final_code !== 0 || stage1_gate !== 0 || stage2_gate !== 0)
                $fatal(1, "idle output mismatch at %0d", vector_count);
            clk = 1;
            #2;
            if ({a10,a11,a12,a13,a20,a21,a22,a23} !== idle_state)
                $fatal(1, "idle state changed at %0d", vector_count);
            clk = 0;
            valid_in = 1;
            stage1_symbol = q1;
            stage2_symbol = q2;
            backend_raw_code = backend;
            stage1_dither_positive = d1;
            stage2_dither_positive = d2;
            #2;
            if (valid_out !== expected_valid || final_code !== expected_code ||
                stage1_gate !== expected_gate1 || stage2_gate !== expected_gate2)
                $fatal(1, "pre-edge mismatch at %0d: valid=%0d/%0d code=%0d/%0d gate=%0d,%0d/%0d,%0d",
                    vector_count, valid_out, expected_valid, final_code, expected_code,
                    stage1_gate, stage2_gate, expected_gate1, expected_gate2);
            if (expected_valid &&
                ($signed(stage1_learning_q3) !== expected_learning1 ||
                 $signed(stage2_learning_q3) !== expected_learning2))
                $fatal(1, "learning output mismatch at %0d", vector_count);
            clk = 1;
            #2;
            if (a10 !== e10 || a11 !== e11 || a12 !== e12 || a13 !== e13 ||
                a20 !== e20 || a21 !== e21 || a22 !== e22 || a23 !== e23)
                $fatal(1, "post-edge accumulator mismatch at %0d: stage1=%0d,%0d,%0d,%0d expected=%0d,%0d,%0d,%0d stage2=%0d,%0d,%0d,%0d expected=%0d,%0d,%0d,%0d",
                    vector_count, a10, a11, a12, a13, e10, e11, e12, e13,
                    a20, a21, a22, a23, e20, e21, e22, e23);
            clk = 0;
            vector_count = vector_count + 1;
            end
        end
        $fclose(file_handle);
        $display("two_stage_adaptive_exact_candidate_a %0d sequential oracle vectors passed", vector_count);
        $finish;
    end
endmodule

