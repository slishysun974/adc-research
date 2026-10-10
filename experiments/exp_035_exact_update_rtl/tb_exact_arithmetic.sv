// Compare actual old/new RTL functions throughout the declared learning domain.
// Saturation probes cover both ends and unity; the companion range proof covers
// every allowed accumulator value, not just these finite probes.
module tb_exact_arithmetic;
    reg clk = 0, reset = 0, valid_in = 0;
    reg signed [15:0] y_in = 0, d_in = 0;
    reg positive = 0;
    fixed_gated_lms_candidate_a old1 (
        .clk(clk), .reset(reset), .valid_in(valid_in),
        .learning_output_q3(y_in), .dither_copy_q3(d_in));
    fixed_gated_lms_candidate_a #(.SLICE_WIDTH_Q3(256), .DELTA_DENOMINATOR(250)) old2 (
        .clk(clk), .reset(reset), .valid_in(valid_in),
        .learning_output_q3(y_in), .dither_copy_q3(d_in));
    fixed_gated_lms_exact_candidate_a new1 (
        .clk(clk), .reset(reset), .valid_in(valid_in),
        .learning_output_q3(y_in[14:0]), .dither_positive(positive));
    fixed_gated_lms_exact_candidate_a #(.SLICE_WIDTH_Q3(256), .REDUCED_SHIFT(6)) new2 (
        .clk(clk), .reset(reset), .valid_in(valid_in),
        .learning_output_q3(y_in[14:0]), .dither_positive(positive));
    integer stage, y, polarity, step_index, step, probe, acc;
    integer low_y, high_y, amplitude, denominator;
    integer cases_checked = 0, enabled_checked = 0, disabled_checked = 0;
    reg signed [63:0] numerator, old_delta;
    reg signed [14:0] new_delta;
    reg signed [31:0] product;
    reg [22:0] old_acc, new_acc;
    initial begin
        for (stage = 1; stage <= 2; stage = stage+1) begin
            low_y = stage == 1 ? -8700 : -2175;
            high_y = stage == 1 ? 8698 : 2159;
            amplitude = stage == 1 ? 512 : 128;
            denominator = stage == 1 ? 4000 : 250;
            for (y = low_y; y <= high_y; y = y+1)
                for (polarity = 0; polarity <= 1; polarity = polarity+1)
                    for (step_index = 0; step_index < 4; step_index = step_index+1) begin
                        case (step_index)
                            0: step=1; 1: step=3; 2: step=6; 3: step=12;
                        endcase
                        product = (polarity ? amplitude : -amplitude) * y;
                        numerator = -$signed({{32{product[31]}},product}) * step;
                        old_delta = stage == 1 ? old1.round_divide_even(numerator) : old2.round_divide_even(numerator);
                        new_delta = stage == 1 ? new1.requested_delta(y,polarity,step) : new2.requested_delta(y,polarity,step);
                        if (old_delta !== $signed(new_delta))
                            $fatal(1,"delta mismatch stage=%0d y=%0d polarity=%0d step=%0d old=%0d new=%0d",
                                stage,y,polarity,step,old_delta,new_delta);
                        cases_checked = cases_checked+1;
                        for (probe = 0; probe < 5; probe = probe+1) begin
                            case (probe)
                                0: acc=0; 1: acc=1; 2: acc=4194304;
                                3: acc=8384511; 4: acc=8384512;
                            endcase
                            old_acc = stage == 1 ? old1.updated_accumulator(acc,product,step) : old2.updated_accumulator(acc,product,step);
                            new_acc = stage == 1 ? new1.updated_accumulator(acc,y,polarity,step,1'b1) : new2.updated_accumulator(acc,y,polarity,step,1'b1);
                            if (old_acc !== new_acc)
                                $fatal(1,"saturation mismatch stage=%0d y=%0d acc=%0d",stage,y,acc);
                            enabled_checked = enabled_checked+1;
                        end
                        new_acc = stage == 1 ? new1.updated_accumulator(23'd4194304,y,polarity,step,1'b0) : new2.updated_accumulator(23'd4194304,y,polarity,step,1'b0);
                        if (new_acc !== 23'd4194304) $fatal(1,"disabled update changed state");
                        disabled_checked = disabled_checked+1;
                    end
        end
        if (cases_checked != 173872 || enabled_checked != 869360 || disabled_checked != 173872)
            $fatal(1,"incomplete arithmetic domain");
        $display("exact arithmetic: %0d deltas, %0d saturation probes, %0d disabled probes passed",
            cases_checked,enabled_checked,disabled_checked);
        $finish;
    end
endmodule
