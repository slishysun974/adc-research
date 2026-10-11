`timescale 1ns/1ps
// Same digital input/reference sequence for RTL and post-synthesis netlist.
module tb_review_cost;
    reg clk=0, reset=0, valid_in=0;
    reg signed [3:0] stage1_symbol=0, stage2_symbol=0;
    reg [7:0] backend_raw_code=128;
    reg stage1_dither_positive=0, stage2_dither_positive=0;
    wire valid_out;
    wire [11:0] final_code;
    integer f, rc, pass, row, count=0, idle_count=0;
    integer q1,q2,b,d1,d2,ev,ec,g1,g2,y1,y2,a0,a1,a2,a3,a4,a5,a6,a7;
    reg [2047:0] path;
    gu_online_cost_top dut(.*);
    initial begin
        if (!$value$plusargs("VECTORS=%s",path)) $fatal(1,"VECTORS is required");
        // The FPGA glbl model keeps GSR asserted for the first 100 ns.
        // Apply our explicit reset after GSR in both RTL and netlist tests.
        #120;
        for (pass=0;pass<2;pass=pass+1) begin
            reset=1; valid_in=0;
            #4; clk=1; #4; clk=0; reset=0;
            f=$fopen(path,"r");
            if (!f) $fatal(1,"cannot open reference vectors");
            row=0;
            while (!$feof(f) && (pass==0 || row<128)) begin
                rc=$fscanf(f,"%d %d %d %d %d %d %d %d %d %d %d %d %d %d %d %d %d %d %d\n",
                    q1,q2,b,d1,d2,ev,ec,g1,g2,y1,y2,a0,a1,a2,a3,a4,a5,a6,a7);
                if (rc!=-1 && rc!=19) $fatal(1,"malformed reference row");
                if (rc==19) begin
                    valid_in=0; #4;
                    if (valid_out!==0 || final_code!==0) $fatal(1,"idle output mismatch");
                    clk=1; #4; clk=0; idle_count=idle_count+1;
                    valid_in=1; stage1_symbol=q1; stage2_symbol=q2; backend_raw_code=b;
                    stage1_dither_positive=d1; stage2_dither_positive=d2;
                    #4;
                    if (valid_out!==ev || final_code!==ec)
                        $fatal(1,"cost output mismatch pass=%0d row=%0d valid=%0d/%0d code=%0d/%0d",pass,row,valid_out,ev,final_code,ec);
                    clk=1; #4; clk=0;
                    row=row+1; count=count+1;
                end
            end
            $fclose(f);
            if ((pass==0 && row!=8263) || (pass==1 && row!=128)) $fatal(1,"incomplete sequence");
        end
        $display("REVIEW_COST_PASS vectors=%0d idle_cycles=%0d reset_replay=128",count,idle_count);
        $finish;
    end
endmodule
