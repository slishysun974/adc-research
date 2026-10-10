// Directed checks for both source-document gate conventions.
// Run with: iverilog -g2012 -s tb_gated_product_candidate_a -o gate_tb
//   gated_product_candidate_a.sv tb_gated_product_candidate_a.sv
// Then execute the generated gate_tb program.
module tb_gated_product_candidate_a;
    logic valid_in;
    logic signed [15:0] learning_output_q3;
    logic signed [15:0] dither_copy_q3;
    logic [16:0] lower1_q3, lower2_q3, lower3_q3;
    logic [3:0] gate_ge, gate_gt;
    logic signed [31:0] ge0, ge1, ge2, ge3;
    logic signed [31:0] gt0, gt1, gt2, gt3;

    gated_product_candidate_a #(.GATE_ON_EQUAL(1'b1)) inclusive (
        .valid_in, .learning_output_q3, .dither_copy_q3,
        .lower1_q3, .lower2_q3, .lower3_q3,
        .gate(gate_ge), .product0_q6(ge0), .product1_q6(ge1),
        .product2_q6(ge2), .product3_q6(ge3)
    );
    gated_product_candidate_a #(.GATE_ON_EQUAL(1'b0)) strict (
        .valid_in, .learning_output_q3, .dither_copy_q3,
        .lower1_q3, .lower2_q3, .lower3_q3,
        .gate(gate_gt), .product0_q6(gt0), .product1_q6(gt1),
        .product2_q6(gt2), .product3_q6(gt3)
    );

    initial begin
        valid_in = 1'b1;
        learning_output_q3 = 16'sd16;
        dither_copy_q3 = 16'sd8;
        lower1_q3 = 17'd16;
        lower2_q3 = 17'd32;
        lower3_q3 = 17'd48;
        #1;
        if (gate_ge !== 4'b0011 || gate_gt !== 4'b0001 ||
            ge0 !== 32'sd128 || ge1 !== 32'sd128 ||
            ge2 !== 32'sd0 || ge3 !== 32'sd0 ||
            gt0 !== 32'sd128 || gt1 !== 32'sd0)
            $fatal(1, "positive equality failed");

        learning_output_q3 = -16'sd32;
        #1;
        if (gate_ge !== 4'b0111 || gate_gt !== 4'b0011 ||
            ge0 !== -32'sd256 || ge1 !== -32'sd256 ||
            ge2 !== -32'sd256 || ge3 !== 32'sd0 ||
            gt0 !== -32'sd256 || gt1 !== -32'sd256 ||
            gt2 !== 32'sd0)
            $fatal(1, "negative equality failed");

        learning_output_q3 = 16'sh8000;
        dither_copy_q3 = -16'sd1;
        lower1_q3 = 17'd32768;
        lower2_q3 = 17'd32769;
        lower3_q3 = 17'd32770;
        #1;
        if (gate_ge !== 4'b0011 || gate_gt !== 4'b0001 ||
            ge0 !== 32'sd32768 || ge1 !== 32'sd32768 ||
            gt0 !== 32'sd32768 || gt1 !== 32'sd0)
            $fatal(1, "signed minimum failed");

        valid_in = 1'b0;
        #1;
        if (gate_ge !== 4'b0000 || gate_gt !== 4'b0000 ||
            ge0 !== 32'sd0 || ge1 !== 32'sd0 || ge2 !== 32'sd0 ||
            ge3 !== 32'sd0 || gt0 !== 32'sd0 || gt1 !== 32'sd0 ||
            gt2 !== 32'sd0 || gt3 !== 32'sd0)
            $fatal(1, "invalid sample failed");
        $display("gated_product_candidate_a directed checks passed");
        $finish;
    end
endmodule
