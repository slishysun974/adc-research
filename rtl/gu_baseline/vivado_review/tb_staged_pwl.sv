`timescale 1ns/1ps
module tb_staged_pwl;
    reg clk=0, reset=1, enable_in=0, valid_in=0;
    reg signed [15:0] raw_q3=0;
    reg [10:0] coefficient0_q10=1024,coefficient1_q10=1024,coefficient2_q10=1024,coefficient3_q10=1024;
    wire done1,done2,valid1,valid2,reference_valid1,reference_valid2;
    wire signed [16:0] out1,out2,reference1,reference2;
    wire [1:0] unused1,unused2;
    fixed_pwl_staged_candidate_a #(.SLICE_WIDTH_Q3(1024)) dut1(
        .clk(clk),.reset(reset),.enable_in(enable_in),.valid_in(valid_in),.raw_q3(raw_q3),
        .coefficient0_q10(coefficient0_q10),.coefficient1_q10(coefficient1_q10),
        .coefficient2_q10(coefficient2_q10),.coefficient3_q10(coefficient3_q10),
        .done_out(done1),.valid_out(valid1),.corrected_q3(out1));
    fixed_pwl_staged_candidate_a #(.SLICE_WIDTH_Q3(256)) dut2(
        .clk(clk),.reset(reset),.enable_in(enable_in),.valid_in(valid_in),.raw_q3(raw_q3),
        .coefficient0_q10(coefficient0_q10),.coefficient1_q10(coefficient1_q10),
        .coefficient2_q10(coefficient2_q10),.coefficient3_q10(coefficient3_q10),
        .done_out(done2),.valid_out(valid2),.corrected_q3(out2));
    fixed_pwl_candidate_a #(.SLICE_WIDTH_Q3(1024)) ref1(
        .valid_in(valid_in),.raw_q3(raw_q3),.coefficient0_q10(coefficient0_q10),
        .coefficient1_q10(coefficient1_q10),.coefficient2_q10(coefficient2_q10),
        .coefficient3_q10(coefficient3_q10),.valid_out(reference_valid1),
        .slice_index(unused1),.corrected_q3(reference1));
    fixed_pwl_candidate_a #(.SLICE_WIDTH_Q3(256)) ref2(
        .valid_in(valid_in),.raw_q3(raw_q3),.coefficient0_q10(coefficient0_q10),
        .coefficient1_q10(coefficient1_q10),.coefficient2_q10(coefficient2_q10),
        .coefficient3_q10(coefficient3_q10),.valid_out(reference_valid2),
        .slice_index(unused2),.corrected_q3(reference2));
    reg [3:0] exp_done=0, exp_valid1=0, exp_valid2=0;
    reg signed [16:0] exp1[0:3],exp2[0:3];
    integer i,j,checks=0,valid_checks1=0,valid_checks2=0,resets=0;
    reg corrupt;
    reg [31:0] rng=32'h6d2b79f5;
    task random_step;
        begin rng=rng^(rng<<13); rng=rng^(rng>>17); rng=rng^(rng<<5); end
    endtask
    task tick;
        begin
            #5; clk=1;
            if(reset) begin
                exp_done=0; exp_valid1=0; exp_valid2=0;
                for(j=0;j<4;j=j+1) begin exp1[j]=0; exp2[j]=0; end
            end else begin
                for(j=3;j>0;j=j-1) begin exp1[j]=exp1[j-1]; exp2[j]=exp2[j-1]; end
                exp1[0]=(enable_in && reference_valid1) ? reference1 : 0;
                exp2[0]=(enable_in && reference_valid2) ? reference2 : 0;
                exp_done={exp_done[2:0],enable_in};
                exp_valid1={exp_valid1[2:0],enable_in && reference_valid1};
                exp_valid2={exp_valid2[2:0],enable_in && reference_valid2};
            end
            #1;
            if(corrupt && exp_valid1[3]) exp1[3]=exp1[3]^17'd1;
            if(done1!==exp_done[3] || done2!==exp_done[3] || valid1!==exp_valid1[3] ||
               valid2!==exp_valid2[3] || out1!==exp1[3] || out2!==exp2[3])
                $fatal(1,"PWL_STAGED_MISMATCH slot=%0d actual1=%0d expected1=%0d actual2=%0d expected2=%0d",i,out1,exp1[3],out2,exp2[3]);
            if(exp_done[3]) checks=checks+1;
            if(exp_valid1[3]) valid_checks1=valid_checks1+1;
            if(exp_valid2[3]) valid_checks2=valid_checks2+1;
            #4; clk=0;
        end
    endtask
    initial begin
        corrupt=$test$plusargs("CORRUPT");
        tick; reset=0;
        for(i=0;i<100000;i=i+1) begin
            random_step;
            raw_q3=$signed({1'b0,rng[13:0]})-16'sd8192;
            if(i<256) begin
                case(i%16)
                0:raw_q3=-32768; 1:raw_q3=-4096; 2:raw_q3=-4095; 3:raw_q3=-3072;
                4:raw_q3=-2048; 5:raw_q3=-1024; 6:raw_q3=-1023; 7:raw_q3=-256;
                8:raw_q3=-1; 9:raw_q3=0; 10:raw_q3=1; 11:raw_q3=256;
                12:raw_q3=1023; 13:raw_q3=1024; 14:raw_q3=4095; 15:raw_q3=4096;
                endcase
            end
            random_step; coefficient0_q10=rng[10:0];
            random_step; coefficient1_q10=rng[10:0];
            random_step; coefficient2_q10=rng[10:0];
            random_step; coefficient3_q10=rng[10:0];
            if(i<64) begin coefficient0_q10=1;coefficient1_q10=3;coefficient2_q10=1024;coefficient3_q10=2047;end
            enable_in=(i%7!=0);valid_in=(i%11!=0);
            reset=(i%4093==4092);
            if(reset) resets=resets+1;
            tick;
        end
        reset=0;enable_in=0;valid_in=0;
        repeat(5) tick;
        $display("PWL_STAGED_PASS slots=100000 completions=%0d valid1=%0d valid2=%0d resets=%0d",checks,valid_checks1,valid_checks2,resets);
        $finish;
    end
endmodule
