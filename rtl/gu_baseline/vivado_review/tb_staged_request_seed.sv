`timescale 1ns/1ps
module tb_staged_request_seed;
    reg clk=0, reset=1, enable_in=0, dither_positive=0;
    reg signed [14:0] learning_q3=0;
    wire [7:0] done_out;
    wire [21:0] actual [0:7];
    reg [21:0] expected [0:3][0:7];
    reg [3:0] valid_history=0;
    integer slot=0, checks=0, token, j, k, r;
    reg [21:0] reference_value, old_value;
    genvar g;
    generate for(g=0;g<8;g=g+1) begin: cases
        fixed_request_seed_staged_candidate_a #(
            .STEP_NUMERATOR(g%4==0 ? 4'd1 : g%4==1 ? 4'd3 : g%4==2 ? 4'd6 : 4'd12),
            .REDUCED_SHIFT(g<4 ? 4 : 6)
        ) dut (.clk(clk),.reset(reset),.enable_in(enable_in),.learning_q3(learning_q3),
               .dither_positive(dither_positive),.done_out(done_out[g]),
               .negative_out(actual[g][21]),.biased_out(actual[g][20:0]));
    end endgenerate
    function [21:0] original;
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
            original = {numerator < 0,biased};
        end
    endfunction
    // Independent wide arithmetic: explicitly reduce modulo 2^22, interpret
    // the sign, take abs, then reduce the biased magnitude modulo 2^21.
    function [21:0] modular_reference;
        input integer learning, positive, multiplier, shift;
        reg signed [63:0] wide, residue, magnitude;
        reg sign_value;
        begin
            wide=learning;
            wide=wide*multiplier*(64'sd1 << shift);
            if(positive) wide=-wide;
            residue=wide & 64'sh3fffff;
            sign_value=residue>=64'sd2097152;
            if(sign_value) residue=residue-64'sd4194304;
            magnitude=residue<0 ? -residue : residue;
            modular_reference={sign_value,21'((magnitude+62)&64'sh1fffff)};
        end
    endfunction
    task tick;
        begin
            #5; clk=1;
            if(reset) valid_history=0;
            else begin
                valid_history={valid_history[2:0],enable_in};
                for(k=3;k>0;k=k-1) for(j=0;j<8;j=j+1) expected[k][j]=expected[k-1][j];
                if(enable_in) for(j=0;j<8;j=j+1) begin
                    r=j%4==0 ? 1 : j%4==1 ? 3 : j%4==2 ? 6 : 12;
                    reference_value=modular_reference($signed(learning_q3),dither_positive,r,j<4 ? 4 : 6);
                    old_value=original(learning_q3,dither_positive,r,j<4 ? 4 : 6);
                    if(reference_value !== old_value) $fatal(1,"SEED_REFERENCE_MISMATCH slot=%0d case=%0d",slot,j);
                    expected[0][j]=reference_value;
                    if($test$plusargs("CORRUPT") && slot==8 && j==5) expected[0][j]=reference_value^22'd1;
                end
            end
            #1;
            if(done_out !== {8{valid_history[3]}}) $fatal(1,"SEED_TOKEN_MISMATCH slot=%0d",slot);
            if(valid_history[3]) for(j=0;j<8;j=j+1) begin
                if(actual[j] !== expected[3][j]) $fatal(1,"SEED_VALUE_MISMATCH slot=%0d case=%0d",slot,j);
                checks=checks+1;
            end
            clk=0; #4; slot=slot+1;
        end
    endtask
    initial begin
        tick; reset=0;
        // Every signed15 input, both dither signs, all eight step/shift pairs.
        for(token=0;token<65536;token=token+1) begin
            enable_in=1; learning_q3=token%32768-16384; dither_positive=token/32768;
            tick;
        end
        enable_in=0; repeat(4) tick;
        if(checks!=524288) $fatal(1,"SEED_WRONG_COUNT checks=%0d",checks);
        // Cancel each pipeline depth, and verify gaps and a fresh token.
        for(token=0;token<4;token=token+1) begin
            enable_in=1; learning_q3=-16384; dither_positive=1; tick;
            enable_in=0; repeat(token) tick;
            reset=1; tick; reset=0; repeat(4) tick;
            enable_in=1; learning_q3=1066; dither_positive=0; tick;
            enable_in=0; repeat(5) tick;
        end
        $display("STAGED_SEED_PASS exhaustive=524288 reset_depths=4 checks=%0d",checks);
        $finish;
    end
endmodule
