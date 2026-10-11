`timescale 1ns/1ps
// Clocked gate equality/neighbor probes at unity, in the proven stage-1 domain.
module tb_review_bank;
    reg clk=0,reset=0,valid_in=0,dither_positive=0;
    reg signed [14:0] learning_output_q3=0;
    wire [3:0] gate;
    wire [10:0] k0,k1,k2,k3;
    wire [22:0] a0,a1,a2,a3;
    integer idx,pol,y,m,step,n,delta,j,cases=0;
    reg [3:0] expected_gate;
    reg [91:0] held;
    fixed_gated_lms_exact_candidate_a dut(.clk(clk),.reset(reset),.valid_in(valid_in),
        .learning_output_q3(learning_output_q3),.dither_positive(dither_positive),.gate(gate),
        .coefficient0_q10(k0),.coefficient1_q10(k1),.coefficient2_q10(k2),.coefficient3_q10(k3),
        .accumulator0_q22(a0),.accumulator1_q22(a1),.accumulator2_q22(a2),.accumulator3_q22(a3));
    function integer expected_state;
        input integer which;
        begin
            case(which) 0: step=1; 1: step=3; 2: step=6; 3: step=12; endcase
            n=(pol ? -1 : 1)*16*step*y;
            delta=(n<0 ? -1 : 1)*((n<0 ? -n : n)+62)/125;
            expected_state=4194304+(expected_gate[which] ? delta : 0);
        end
    endfunction
    initial begin
        for (idx=0;idx<11;idx=idx+1) begin
            case(idx)
                0:y=0;1:y=1023;2:y=1024;3:y=1025;4:y=2047;5:y=2048;
                6:y=2049;7:y=3071;8:y=3072;9:y=3073;10:y=-3072;
            endcase
            for(pol=0;pol<2;pol=pol+1) begin
                valid_in=0;reset=1;#4;clk=1;#4;clk=0;reset=0;
                if ({a0,a1,a2,a3}!={4{23'd4194304}}) $fatal(1,"bank reset mismatch");
                learning_output_q3=y; dither_positive=pol; valid_in=1;#4;
                m=y<0 ? -y : y;
                expected_gate={m>=3072,m>=2048,m>=1024,1'b1};
                if(gate!==expected_gate) $fatal(1,"gate mismatch y=%0d",y);
                clk=1;#4;clk=0;
                if(a0!==expected_state(0)||a1!==expected_state(1)||a2!==expected_state(2)||a3!==expected_state(3))
                    $fatal(1,"clocked bank update mismatch y=%0d polarity=%0d",y,pol);
                held={a0,a1,a2,a3};valid_in=0;#4;clk=1;#4;clk=0;
                if(gate!==0 || {a0,a1,a2,a3}!==held) $fatal(1,"bank idle mismatch");
                cases=cases+1;
            end
        end
        $display("REVIEW_BANK_PASS cases=%0d",cases);$finish;
    end
endmodule
