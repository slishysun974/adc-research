// Physical evaluation boundary; diagnostic ports stay in the RTL testbench.
module gu_multicycle_cost_top (
    input wire clk, reset, valid_in,
    input wire signed [3:0] stage1_symbol, stage2_symbol,
    input wire [7:0] backend_raw_code,
    input wire stage1_dither_positive, stage2_dither_positive,
    output wire ready_in, done_out, valid_out,
    output wire [11:0] final_code
);
    // Keep the 100 MHz frequency and deskew the FPGA clock network against
    // the external reference. A bare IBUF/BUFG left ~5.7 ns insertion delay
    // on externally timed outputs even after the arithmetic was multicycle.
    wire clk_input, clk_unbuffered, clk_core, clk_feedback, clk_feedback_buf;
    wire clock_locked;
    (* ASYNC_REG = "TRUE" *) reg [1:0] locked_sync = 2'b00;
    IBUF input_clock_buffer (.I(clk), .O(clk_input));
    MMCME2_BASE #(
        .CLKIN1_PERIOD(10.0), .CLKFBOUT_MULT_F(10.0),
        .DIVCLK_DIVIDE(1), .CLKOUT0_DIVIDE_F(10.0),
        // Unused outputs must also obey MMCM output-period limits in SDF.
        // Their default divide-by-one would generate unused 1 GHz clocks.
        .CLKOUT1_DIVIDE(10), .CLKOUT2_DIVIDE(10), .CLKOUT3_DIVIDE(10),
        .CLKOUT4_DIVIDE(10), .CLKOUT5_DIVIDE(10), .CLKOUT6_DIVIDE(10)
    ) clock_manager (
        .CLKIN1(clk_input), .CLKFBIN(clk_feedback_buf),
        .CLKFBOUT(clk_feedback), .CLKOUT0(clk_unbuffered),
        .LOCKED(clock_locked), .PWRDWN(1'b0), .RST(1'b0)
    );
    BUFG feedback_clock_buffer (.I(clk_feedback), .O(clk_feedback_buf));
    BUFG core_clock_buffer (.I(clk_unbuffered), .O(clk_core));
    always @(posedge clk_core) begin
        if (reset) locked_sync <= 0;
        else locked_sync <= {locked_sync[0], clock_locked};
    end
    wire core_reset = reset || !locked_sync[1];
    two_stage_multicycle_candidate_a #(.COMPUTE_CYCLES(16)) engine (
        .clk(clk_core), .reset(core_reset), .valid_in(valid_in), .ready_in(ready_in),
        .stage1_symbol(stage1_symbol), .stage2_symbol(stage2_symbol),
        .backend_raw_code(backend_raw_code),
        .stage1_dither_positive(stage1_dither_positive),
        .stage2_dither_positive(stage2_dither_positive),
        .done_out(done_out), .valid_out(valid_out), .final_code(final_code)
    );
endmodule
