`timescale 1ns/1ps
// Same accepted digital sequence as the state-level RTL bench, for a routed
// cost-top netlist. Count edges of the routed engine clock and allow output
// propagation. External-reference IO timing is checked separately by STA.
module tb_multicycle_cost;
    localparam integer LATENCY=39;
    reg clk=0, reset=1, valid_in=0;
    reg signed [3:0] stage1_symbol=0, stage2_symbol=0;
    reg [7:0] backend_raw_code=128;
    reg stage1_dither_positive=0, stage2_dither_positive=0;
    wire ready_in, done_out, valid_out;
    wire [11:0] final_code;
    gu_multicycle_cost_top dut (.*);
    // MMCM timing models and routed clock-tree insertion shift clock phase.
    // Count transactions against the actual engine clock. External-reference
    // IO setup/hold remains a separate STA check, not this scoreboard's claim.
    wire observed_clk = dut.core_clock_buffer.O;
    always #5 clk=~clk;
    integer fd,n,row,phase,pass,q1,q2,b,d1,d2,ev,ec,g1,g2,y1,y2,wait_count;
    integer a10,a11,a12,a13,a20,a21,a22,a23;
    reg [4095:0] path;
    real observed_edge;
    task tick;
        begin @(posedge observed_clk); #9.2; end
    endtask
    task idle_check;
        begin
            valid_in=0;
            tick;
            if (done_out !== 0 || valid_out !== 0 || ready_in !== 1)
                $fatal(1,"cost idle failed row=%0d",row);
        end
    endtask
    task release_reset;
        begin
            valid_in=0;
            @(posedge observed_clk); #1; reset=1;
            tick;
            @(posedge observed_clk); #1; reset=0;
            // MMCM lock synchronization extends the physical top's reset.
            repeat(5) tick;
            wait_count=0;
            while(ready_in !== 1 && wait_count<10000) begin tick; wait_count=wait_count+1; end
            if(ready_in !== 1 || done_out !== 0 || valid_out !== 0)
                $fatal(1,"clock/reset qualification failed");
        end
    endtask
    initial begin
        if (!$value$plusargs("VECTORS=%s",path)) $fatal(1,"missing vectors");
        #10000;
        @(posedge observed_clk); observed_edge=$realtime;
        @(posedge observed_clk);
        if (($realtime-observed_edge < 9.995) || ($realtime-observed_edge > 10.005))
            $fatal(1,"working clock is not 100 MHz");
        release_reset;
        // Drive at engine-clock +1 ns; the input is captured on the next edge.
        // Abort at E2..E39; the RTL bench also covers E1.
        for (phase=0;phase<LATENCY-1;phase=phase+1) begin
            @(posedge observed_clk); #1;
            valid_in=1; stage1_symbol=0; stage2_symbol=0; backend_raw_code=90;
            tick;
            valid_in=0;
            for(n=0;n<phase;n=n+1) tick;
            release_reset;
            for(n=0;n<LATENCY+1;n=n+1) idle_check;
        end
        for(pass=0;pass<2;pass=pass+1) begin
            release_reset;
            fd=$fopen(path,"r");
            if(!fd) $fatal(1,"cannot open vectors");
            row=0;
            while(!$feof(fd) && (pass==0 || row<128)) begin
                n=$fscanf(fd,"%d %d %d %d %d %d %d %d %d %d %d %d %d %d %d %d %d %d %d\n",
                    q1,q2,b,d1,d2,ev,ec,g1,g2,y1,y2,a10,a11,a12,a13,a20,a21,a22,a23);
                if(n!=19) $fatal(1,"malformed row=%0d",row);
                if(ready_in !== 1) $fatal(1,"cost not ready row=%0d",row);
                // One idle edge between conversions; full-rate E40 acceptance
                // is covered by the state-level RTL bench.
                @(posedge observed_clk); #1;
                valid_in=1; stage1_symbol=q1; stage2_symbol=q2; backend_raw_code=b;
                stage1_dither_positive=d1; stage2_dither_positive=d2;
                tick;
                valid_in=0;
                if(ready_in !== 0 || done_out !== 0 || valid_out !== 0)
                    $fatal(1,"cost acceptance failed row=%0d",row);
                for(n=1;n<=LATENCY;n=n+1) begin
                    stage1_symbol=n; stage2_symbol=-n; backend_raw_code=b^n;
                    stage1_dither_positive=~stage1_dither_positive;
                    stage2_dither_positive=~stage2_dither_positive;
                    tick;
                    if(n<LATENCY && (done_out !== 0 || valid_out !== 0 || ready_in !== 0))
                        $fatal(1,"cost early output row=%0d cycle=%0d",row,n);
                end
                if(done_out !== 1 || ready_in !== 1 || valid_out !== ev || final_code !== ec)
                    $fatal(1,"cost mismatch pass=%0d row=%0d valid=%0d/%0d code=%0d/%0d",pass,row,valid_out,ev,final_code,ec);
                if(row%31==0) idle_check;
                row=row+1;
                if(row%512==0) $display("MULTICYCLE_SDF_PROGRESS pass=%0d rows=%0d time=%0t",pass,row,$time);
            end
            $fclose(fd);
            if((pass==0 && row!=8263)||(pass==1 && row!=128)) $fatal(1,"wrong count");
        end
        idle_check;
        $display("MULTICYCLE_COST_PASS vectors=8263 replay=128 reset_phases=38");
        $finish;
    end
endmodule
