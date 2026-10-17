// One conversion in flight. At the default COMPUTE_CYCLES=16:
// accept E0, stage2 E1..E4, reconstruction E5, stage1 E6..E9, capture E10,
// hold through E16, seed division E17, divide E18..E38,
// publish/commit E39, next acceptance E40 (2.5 MS/s at 100 MHz).
// All arithmetic and both banks use the pre-conversion coefficients.
// No clock gating; only data registers and synchronous clock enables.
module two_stage_staged_candidate_a #(
    parameter integer COMPUTE_CYCLES = 16
) (
    input logic clk, reset, valid_in,
    output logic ready_in,
    input logic signed [3:0] stage1_symbol, stage2_symbol,
    input logic [7:0] backend_raw_code,
    input logic stage1_dither_positive, stage2_dither_positive,
    output logic done_out, valid_out,
    output logic [11:0] final_code,
    output logic [3:0] stage1_gate, stage2_gate,
    output logic signed [15:0] stage1_learning_q3, stage2_learning_q3,
    output logic [22:0] stage1_accumulator0_q22, stage1_accumulator1_q22,
    output logic [22:0] stage1_accumulator2_q22, stage1_accumulator3_q22,
    output logic [22:0] stage2_accumulator0_q22, stage2_accumulator1_q22,
    output logic [22:0] stage2_accumulator2_q22, stage2_accumulator3_q22
);
    localparam integer COUNT_BITS = $clog2(COMPUTE_CYCLES);
    localparam [3:0] IDLE=0, PWL2_START=1, PWL2_WAIT=2, PWL1_START=3, PWL1_WAIT=4, HOLD=5, NUMERATE=6, DIVIDE=7, COMMIT=8;
    logic [3:0] phase;
    logic [COUNT_BITS-1:0] remaining;
    logic [4:0] divide_remaining;
    wire commit_enable = phase == COMMIT;
    // Pending data is registered at E10. All paths use ordinary one-cycle STA.
    (* DONT_TOUCH = "TRUE" *) logic pending_valid;
    (* DONT_TOUCH = "TRUE" *) logic [11:0] pending_code;
    (* DONT_TOUCH = "TRUE" *) logic [3:0] pending_gate1, pending_gate2;
    (* DONT_TOUCH = "TRUE" *) logic signed [15:0] pending_learning1, pending_learning2;
    logic [20:0] dividend [0:7];
    logic [13:0] quotient [0:7];
    logic [6:0] remainder125 [0:7];
    logic [7:0] negative;
    wire signed [14:0] external_delta [0:7];
    wire [7:0] partial_remainder [0:7];
    integer i;

    function [21:0] biased_numerator;
        input signed [14:0] learning;
        input positive;
        input [3:0] step_numerator;
        input integer reduced_shift;
        reg signed [21:0] scaled_learning, numerator;
        reg [20:0] magnitude, biased;
        begin
            scaled_learning = $signed({{7{learning[14]}},learning}) *
                              $signed({1'b0,step_numerator});
            numerator = (positive ? -scaled_learning : scaled_learning) <<< reduced_shift;
            magnitude = numerator < 0 ? $unsigned(-numerator) : $unsigned(numerator);
            biased = magnitude + 21'd62;
            biased_numerator = {numerator < 0,biased};
        end
    endfunction

    genvar g;
    generate for (g=0;g<8;g=g+1) begin: serial_requests
        assign partial_remainder[g] = {remainder125[g],dividend[g][20]};
        wire enabled = pending_valid &&
            (g<4 ? pending_gate1[g%4] : pending_gate2[g%4]);
        assign external_delta[g] = !enabled ? 15'sd0 : negative[g] ?
            -$signed({1'b0,quotient[g]}) : $signed({1'b0,quotient[g]});
    end endgenerate

    // Held sample and state names retained for full-state verification.
    (* KEEP = "TRUE" *) logic signed [3:0] sample_stage1, sample_stage2;
    (* KEEP = "TRUE" *) logic [7:0] sample_backend;
    (* KEEP = "TRUE" *) logic sample_dither1, sample_dither2;
    logic [10:0] k10, k11, k12, k13, k20, k21, k22, k23;
    (* DONT_TOUCH = "TRUE" *) reg [10:0] snapshot_k10, snapshot_k11, snapshot_k12, snapshot_k13, snapshot_k20, snapshot_k21, snapshot_k22, snapshot_k23;
    wire correction_valid, stage2_valid, stage1_done, stage2_done;
    wire signed [16:0] corrected1, corrected2;
    reg signed [15:0] raw1_registered, learning2_registered;
    reg raw1_valid;
    wire symbols_valid = $signed(sample_stage1) >= -4 && $signed(sample_stage1) <= 4 &&
                         $signed(sample_stage2) >= -4 && $signed(sample_stage2) <= 4;
    wire signed [31:0] raw2_wide = ($signed({1'b0,sample_backend}) - 32'sd128) <<< 3;
    wire signed [31:0] symbol2_wide = {{28{sample_stage2[3]}},sample_stage2};
    wire signed [31:0] corrected2_wide = {{15{corrected2[16]}},corrected2};
    wire signed [31:0] raw1_next = (symbol2_wide <<< 10) + corrected2_wide -
                                  (sample_dither2 ? 32'sd128 : -32'sd128);
    wire signed [31:0] learning2_next = corrected2_wide -
                                      (sample_dither2 ? 32'sd128 : -32'sd128);
    wire signed [31:0] learning1_wide = $signed(corrected1) -
        (sample_dither1 ? 32'sd512 : -32'sd512);
    wire signed [31:0] learning2_wide = {{16{learning2_registered[15]}},learning2_registered};
    reg [3:0] gate1, gate2;
    wire [3:0] unused_bank_gate1,unused_bank_gate2;
    reg [11:0] correction_code;
    reg [15:0] clipped;
    reg [15:0] code_quotient;
    wire signed [31:0] symbol1_wide = {{28{sample_stage1[3]}},sample_stage1};
    wire signed [31:0] corrected1_wide = {{15{corrected1[16]}},corrected1};
    wire signed [31:0] unclip = (symbol1_wide <<< 12) + corrected1_wide -
        (sample_dither1 ? 32'sd512 : -32'sd512) + 32'sd16384;

    // These boundaries follow the paper's correction/extraction separation;
    // their exact cycle placement is this candidate's implementation choice.
    fixed_pwl_staged_candidate_a #(.SLICE_WIDTH_Q3(256)) stage2_pwl (
        .clk(clk),.reset(reset),.enable_in(phase==PWL2_START),.valid_in(symbols_valid),
        .raw_q3(raw2_wide[15:0]),
        .coefficient0_q10(snapshot_k20),.coefficient1_q10(snapshot_k21),.coefficient2_q10(snapshot_k22),.coefficient3_q10(snapshot_k23),
        .done_out(stage2_done),.valid_out(stage2_valid),.corrected_q3(corrected2));
    fixed_pwl_staged_candidate_a #(.SLICE_WIDTH_Q3(1024)) stage1_pwl (
        .clk(clk),.reset(reset),.enable_in(phase==PWL1_START),.valid_in(raw1_valid),
        .raw_q3(raw1_registered),
        .coefficient0_q10(snapshot_k10),.coefficient1_q10(snapshot_k11),.coefficient2_q10(snapshot_k12),.coefficient3_q10(snapshot_k13),
        .done_out(stage1_done),.valid_out(correction_valid),.corrected_q3(corrected1));
    always @* begin
        clipped = 0;
        code_quotient = 0;
        correction_code = 0;
        if(correction_valid) begin
            if(unclip < 0) clipped = 0;
            else if(unclip > 32'sd32760) clipped = 16'd32760;
            else clipped = unclip[15:0];
            code_quotient = clipped >> 3;
            if(clipped[2:0] > 3'd4 || (clipped[2:0] == 3'd4 && code_quotient[0]))
                code_quotient = code_quotient + 1'b1;
            correction_code = code_quotient[11:0];
        end
    end

    function [16:0] snapshot_threshold;
        input [12:0] sum;
        input integer width_q3;
        reg [31:0] wide,quotient;
        begin
            wide=sum*width_q3;
            quotient=wide>>10;
            if(wide[9:0]>10'd512 || (wide[9:0]==10'd512 && quotient[0])) quotient=quotient+1'b1;
            snapshot_threshold=quotient[16:0];
        end
    endfunction
    wire signed [14:0] gate_learning1=learning1_wide[14:0];
    wire signed [14:0] gate_learning2=learning2_wide[14:0];
    wire [15:0] magnitude1=gate_learning1<0 ? -$signed({gate_learning1[14],gate_learning1}) : $signed({1'b0,gate_learning1});
    wire [15:0] magnitude2=gate_learning2<0 ? -$signed({gate_learning2[14],gate_learning2}) : $signed({1'b0,gate_learning2});
    wire [12:0] sum11={2'b0,snapshot_k10};
    wire [12:0] sum12={2'b0,snapshot_k10}+{2'b0,snapshot_k11};
    wire [12:0] sum13={2'b0,snapshot_k10}+{2'b0,snapshot_k11}+{2'b0,snapshot_k12};
    wire [12:0] sum21={2'b0,snapshot_k20};
    wire [12:0] sum22={2'b0,snapshot_k20}+{2'b0,snapshot_k21};
    wire [12:0] sum23={2'b0,snapshot_k20}+{2'b0,snapshot_k21}+{2'b0,snapshot_k22};
    always @* begin
        gate1=0;gate2=0;
        if(correction_valid) begin
            gate1[0]=1;gate2[0]=1;
            gate1[1]={1'b0,magnitude1}>=snapshot_threshold(sum11,1024);
            gate1[2]={1'b0,magnitude1}>=snapshot_threshold(sum12,1024);
            gate1[3]={1'b0,magnitude1}>=snapshot_threshold(sum13,1024);
            gate2[1]={1'b0,magnitude2}>=snapshot_threshold(sum21,256);
            gate2[2]={1'b0,magnitude2}>=snapshot_threshold(sum22,256);
            gate2[3]={1'b0,magnitude2}>=snapshot_threshold(sum23,256);
        end
    end

    fixed_gated_lms_exact_candidate_a #(
        .SLICE_WIDTH_Q3(1024), .REDUCED_SHIFT(4), .EXTERNAL_COMMIT(1), .EXTERNAL_DELTA(1)
    ) stage1_bank (
        .clk(clk), .reset(reset), .valid_in(correction_valid),
        .commit_enable(commit_enable),
        .delta0(external_delta[0]), .delta1(external_delta[1]),
        .delta2(external_delta[2]), .delta3(external_delta[3]),
        .learning_output_q3(learning1_wide[14:0]),
        .dither_positive(sample_dither1), .gate(unused_bank_gate1),
        .coefficient0_q10(k10), .coefficient1_q10(k11),
        .coefficient2_q10(k12), .coefficient3_q10(k13),
        .accumulator0_q22(stage1_accumulator0_q22),
        .accumulator1_q22(stage1_accumulator1_q22),
        .accumulator2_q22(stage1_accumulator2_q22),
        .accumulator3_q22(stage1_accumulator3_q22)
    );
    fixed_gated_lms_exact_candidate_a #(
        .SLICE_WIDTH_Q3(256), .REDUCED_SHIFT(6), .EXTERNAL_COMMIT(1), .EXTERNAL_DELTA(1)
    ) stage2_bank (
        .clk(clk), .reset(reset), .valid_in(correction_valid),
        .commit_enable(commit_enable),
        .delta0(external_delta[4]), .delta1(external_delta[5]),
        .delta2(external_delta[6]), .delta3(external_delta[7]),
        .learning_output_q3(learning2_wide[14:0]),
        .dither_positive(sample_dither2), .gate(unused_bank_gate2),
        .coefficient0_q10(k20), .coefficient1_q10(k21),
        .coefficient2_q10(k22), .coefficient3_q10(k23),
        .accumulator0_q22(stage2_accumulator0_q22),
        .accumulator1_q22(stage2_accumulator1_q22),
        .accumulator2_q22(stage2_accumulator2_q22),
        .accumulator3_q22(stage2_accumulator3_q22)
    );

    always @(posedge clk) begin
        if (reset) begin
            ready_in <= 0;
            phase <= IDLE;
            remaining <= 0;
            divide_remaining <= 0;
            snapshot_k10 <= 11'd1024;
            snapshot_k11 <= 11'd1024;
            snapshot_k12 <= 11'd1024;
            snapshot_k13 <= 11'd1024;
            snapshot_k20 <= 11'd1024;
            snapshot_k21 <= 11'd1024;
            snapshot_k22 <= 11'd1024;
            snapshot_k23 <= 11'd1024;
            raw1_registered <= 0;
            raw1_valid <= 0;
            learning2_registered <= 0;
            pending_valid <= 0;
            pending_code <= 0;
            pending_gate1 <= 0;
            pending_gate2 <= 0;
            pending_learning1 <= 0;
            pending_learning2 <= 0;
            negative <= 0;
            for(i=0;i<8;i=i+1) begin
                dividend[i] <= 0;
                quotient[i] <= 0;
                remainder125[i] <= 0;
            end
            sample_stage1 <= 0;
            sample_stage2 <= 0;
            sample_backend <= 128;
            sample_dither1 <= 0;
            sample_dither2 <= 0;
            done_out <= 0;
            valid_out <= 0;
            final_code <= 0;
            stage1_gate <= 0;
            stage2_gate <= 0;
            stage1_learning_q3 <= 0;
            stage2_learning_q3 <= 0;
        end else begin
            done_out <= 0;
            valid_out <= 0;
            if (ready_in && valid_in) begin
                ready_in <= 0;
                snapshot_k10 <= k10;
                snapshot_k11 <= k11;
                snapshot_k12 <= k12;
                snapshot_k13 <= k13;
                snapshot_k20 <= k20;
                snapshot_k21 <= k21;
                snapshot_k22 <= k22;
                snapshot_k23 <= k23;
                sample_stage1 <= stage1_symbol;
                sample_stage2 <= stage2_symbol;
                sample_backend <= backend_raw_code;
                sample_dither1 <= stage1_dither_positive;
                sample_dither2 <= stage2_dither_positive;
                phase <= PWL2_START;
                remaining <= COMPUTE_CYCLES - 1;
            end else begin
                case(phase)
                PWL2_START: phase <= PWL2_WAIT;
                PWL2_WAIT: if(stage2_done) begin
                    raw1_registered <= raw1_next[15:0];
                    raw1_valid <= stage2_valid;
                    learning2_registered <= learning2_next[15:0];
                    phase <= PWL1_START;
                end
                PWL1_START: phase <= PWL1_WAIT;
                PWL1_WAIT: if(stage1_done) begin
                    pending_valid <= correction_valid;
                    pending_code <= correction_code;
                    pending_gate1 <= gate1;
                    pending_gate2 <= gate2;
                    pending_learning1 <= correction_valid ? learning1_wide[15:0] : 16'sd0;
                    pending_learning2 <= correction_valid ? learning2_wide[15:0] : 16'sd0;
                    remaining <= COMPUTE_CYCLES - 11;
                    phase <= HOLD;
                end
                HOLD: if(remaining==0) phase <= NUMERATE;
                      else remaining <= remaining - 1'b1;
                NUMERATE: begin
                    for(i=0;i<8;i=i+1) begin
                        {negative[i],dividend[i]} <= biased_numerator(
                            i<4 ? pending_learning1[14:0] : pending_learning2[14:0],
                            i<4 ? sample_dither1 : sample_dither2,
                            i%4==0 ? 4'd1 : i%4==1 ? 4'd3 : i%4==2 ? 4'd6 : 4'd12,
                            i<4 ? 4 : 6);
                        remainder125[i] <= 0;
                        quotient[i] <= 0;
                    end
                    divide_remaining <= 20;
                    phase <= DIVIDE;
                end
                DIVIDE: begin
                    for(i=0;i<8;i=i+1) begin
                        dividend[i] <= {dividend[i][19:0],1'b0};
                        if(partial_remainder[i]>=8'd125) begin
                            remainder125[i] <= partial_remainder[i]-8'd125;
                            quotient[i] <= {quotient[i][12:0],1'b1};
                        end else begin
                            remainder125[i] <= partial_remainder[i][6:0];
                            quotient[i] <= {quotient[i][12:0],1'b0};
                        end
                    end
                    if(divide_remaining==0) phase <= COMMIT;
                    else divide_remaining <= divide_remaining-1'b1;
                end
                COMMIT: begin
                    ready_in <= 1;
                    phase <= IDLE;
                    done_out <= 1;
                    valid_out <= pending_valid;
                    final_code <= pending_code;
                    stage1_gate <= pending_gate1;
                    stage2_gate <= pending_gate2;
                    stage1_learning_q3 <= pending_learning1;
                    stage2_learning_q3 <= pending_learning2;
                end
                default: ready_in <= 1;
                endcase
            end
        end
    end
endmodule
