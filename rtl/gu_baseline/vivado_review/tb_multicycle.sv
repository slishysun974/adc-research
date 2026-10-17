`timescale 1ns/1ps
module tb_multicycle;
    parameter integer CYCLES = 16;
    localparam integer LATENCY = CYCLES+23;
    reg clk=0, reset=1, valid_in=0;
    reg signed [3:0] stage1_symbol=0, stage2_symbol=0;
    reg [7:0] backend_raw_code=128;
    reg stage1_dither_positive=0, stage2_dither_positive=0;
    wire ready_in, done_out, valid_out;
    wire [11:0] final_code;
    wire [3:0] stage1_gate, stage2_gate;
    wire signed [15:0] stage1_learning_q3, stage2_learning_q3;
    wire [22:0] stage1_accumulator0_q22, stage1_accumulator1_q22;
    wire [22:0] stage1_accumulator2_q22, stage1_accumulator3_q22;
    wire [22:0] stage2_accumulator0_q22, stage2_accumulator1_q22;
    wire [22:0] stage2_accumulator2_q22, stage2_accumulator3_q22;
    wire [183:0] states = {stage1_accumulator0_q22,stage1_accumulator1_q22,
        stage1_accumulator2_q22,stage1_accumulator3_q22,
        stage2_accumulator0_q22,stage2_accumulator1_q22,
        stage2_accumulator2_q22,stage2_accumulator3_q22};
    two_stage_multicycle_candidate_a #(.COMPUTE_CYCLES(CYCLES)) dut (.*);
    integer fd, n, row, phase, pass, q1,q2,b,d1,d2,ev,ec,g1,g2,y1,y2;
    reg [22:0] a10,a11,a12,a13,a20,a21,a22,a23;
    reg [183:0] old_states;
    reg [4095:0] path;
    task tick;
        begin #5; clk=1; #1; clk=0; #4; end
    endtask
    task idle_check;
        begin
            valid_in=0;
            old_states=states;
            tick;
            if (states !== old_states || done_out !== 0 || valid_out !== 0 || ready_in !== 1)
                $fatal(1,"idle failed row=%0d",row);
        end
    endtask
    initial begin
        if (!$value$plusargs("VECTORS=%s",path)) $fatal(1,"missing vector path");
        tick; reset=0; tick;
        // Reset during every busy phase, including immediately before commit.
        for (phase=0; phase<LATENCY; phase=phase+1) begin
            valid_in=1; stage1_symbol=0; stage2_symbol=0; backend_raw_code=90;
            tick;
            for (n=0;n<phase;n=n+1) tick;
            reset=1; tick; reset=0; #1;
            if (states !== {8{23'd4194304}} || done_out !== 0 || ready_in !== 0)
                $fatal(1,"abort/reset failed phase=%0d",phase);
            for (n=0;n<LATENCY+1;n=n+1) idle_check;
        end
        // Full frozen sequence, then 128-row reset/replay.
        for (pass=0;pass<2;pass=pass+1) begin
            valid_in=0; reset=1; tick; reset=0; tick;
            fd=$fopen(path,"r");
            if (!fd) $fatal(1,"cannot open vectors");
            row=0;
            while (!$feof(fd) && (pass==0 || row<128)) begin
                n=$fscanf(fd,"%d %d %d %d %d %d %d %d %d %d %d %d %d %d %d %d %d %d %d\n",
                    q1,q2,b,d1,d2,ev,ec,g1,g2,y1,y2,a10,a11,a12,a13,a20,a21,a22,a23);
                if (n != 19) $fatal(1,"malformed row=%0d fields=%0d",row,n);
                if (ready_in !== 1) $fatal(1,"not ready row=%0d",row);
                old_states=states;
                valid_in=1; stage1_symbol=q1; stage2_symbol=q2; backend_raw_code=b;
                stage1_dither_positive=d1; stage2_dither_positive=d2;
                tick; // acceptance E0
                if (ready_in !== 0 || done_out !== 0 || states !== old_states)
                    $fatal(1,"acceptance changed state row=%0d",row);
                // Leave valid high and change all inputs: no second acceptance.
                for (n=1;n<=LATENCY;n=n+1) begin
                    stage1_symbol=n; stage2_symbol=-n; backend_raw_code=b^n;
                    stage1_dither_positive=~stage1_dither_positive;
                    stage2_dither_positive=~stage2_dither_positive;
                    tick;
                    if (n<LATENCY && (done_out !== 0 || valid_out !== 0 || states !== old_states || ready_in !== 0))
                        $fatal(1,"early commit row=%0d cycle=%0d",row,n);
                end
                if (done_out !== 1 || ready_in !== 1 || valid_out !== ev || final_code !== ec ||
                    stage1_gate !== g1 || stage2_gate !== g2 ||
                    $signed(stage1_learning_q3) !== y1 || $signed(stage2_learning_q3) !== y2 ||
                    states !== {a10,a11,a12,a13,a20,a21,a22,a23})
                    $fatal(1,"multicycle mismatch pass=%0d row=%0d valid=%0d/%0d code=%0d/%0d",
                        pass,row,valid_out,ev,final_code,ec);
                // Mostly accept on the very next edge; sometimes insert gaps.
                if (row%31==0) idle_check;
                row=row+1;
            end
            $fclose(fd);
            if ((pass==0 && row!=8263) || (pass==1 && row!=128)) $fatal(1,"wrong row count");
        end
        idle_check;
        $display("MULTICYCLE_PASS vectors=8263 replay=128 reset_phases=%0d cycles=%0d",LATENCY,LATENCY);
        $finish;
    end
endmodule
