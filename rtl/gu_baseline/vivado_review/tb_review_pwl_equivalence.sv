`timescale 1ns/1ps
// Compare an isolated width-only candidate with the unchanged original PWL.
module tb_review_pwl_equivalence;
    reg valid_in;
    reg signed [15:0] raw;
    reg [10:0] c0,c1,c2,c3;
    wire v1,v2,r1,r2;
    wire [1:0] s1,s2,t1,t2;
    wire signed [16:0] y1,y2,z1,z2;
    integer pattern, word, en, n, checks;
    reg [31:0] rng;
    fixed_pwl_candidate_a #(.SLICE_WIDTH_Q3(1024)) candidate1(valid_in,raw,c0,c1,c2,c3,v1,s1,y1);
    fixed_pwl_candidate_a #(.SLICE_WIDTH_Q3(256)) candidate2(valid_in,raw,c0,c1,c2,c3,v2,s2,y2);
    fixed_pwl_reference_review #(.SLICE_WIDTH_Q3(1024)) reference1(valid_in,raw,c0,c1,c2,c3,r1,t1,z1);
    fixed_pwl_reference_review #(.SLICE_WIDTH_Q3(256)) reference2(valid_in,raw,c0,c1,c2,c3,r2,t2,z2);
    task check;
        begin
            #1;
            if ({v1,s1,y1} !== {r1,t1,z1} || {v2,s2,y2} !== {r2,t2,z2})
                $fatal(1,"PWL width mismatch raw=%0d valid=%0d coefficients=%0d,%0d,%0d,%0d",raw,valid_in,c0,c1,c2,c3);
            checks=checks+2;
        end
    endtask
    task next_random;
        begin rng=rng^(rng<<13); rng=rng^(rng>>17); rng=rng^(rng<<5); end
    endtask
    initial begin
        checks=0; rng=32'h1376abcd;
        for(pattern=0;pattern<6;pattern=pattern+1) begin
            case(pattern)
                0: begin c0=0;c1=0;c2=0;c3=0;end
                1: begin c0=2047;c1=2047;c2=2047;c3=2047;end
                2: begin c0=1024;c1=1024;c2=1024;c3=1024;end
                3: begin c0=0;c1=2047;c2=1;c3=2046;end
                4: begin c0=2047;c1=0;c2=2047;c3=0;end
                5: begin c0=1023;c1=1025;c2=1024;c3=1100;end
            endcase
            for(en=0;en<2;en=en+1) begin
                valid_in=en;
                for(word=-32768;word<32768;word=word+1) begin raw=word;check;end
            end
        end
        for(n=0;n<4096;n=n+1) begin
            next_random;raw=rng[15:0];valid_in=rng[16];
            next_random;c0=rng[10:0];next_random;c1=rng[10:0];
            next_random;c2=rng[10:0];next_random;c3=rng[10:0];check;
        end
        $display("REVIEW_PWL_WIDTH_EQUIVALENCE_PASS checks=%0d",checks);
        $finish;
    end
endmodule
