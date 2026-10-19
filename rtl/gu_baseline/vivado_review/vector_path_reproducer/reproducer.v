`timescale 1ps/1ps
module chain_vector(input CI, input [3:0] S, output [3:0] O);
  wire [3:0] c;
  assign c[0] = CI;
  assign c[3:1] = S[2:0] & c[2:0];
  assign O = S ^ c;
  specify
    (CI => O[0]) = (219,219);
    (CI => O[1]) = (323,323);
    (CI => O[2]) = (239,239);
    (CI => O[3]) = (0,0);
    (S[0] => O[0]) = (228,228);
    (S[0] => O[1]) = (403,403);
    (S[0] => O[2]) = (520,520);
    (S[0] => O[3]) = (0,0);
    (S[1] => O[0]) = (0,0);
    (S[1] => O[1]) = (210,210);
    (S[1] => O[2]) = (558,558);
    (S[1] => O[3]) = (0,0);
    (S[2] => O[0]) = (0,0);
    (S[2] => O[1]) = (0,0);
    (S[2] => O[2]) = (228,228);
    (S[2] => O[3]) = (0,0);
    (S[3] => O[0]) = (0,0);
    (S[3] => O[1]) = (0,0);
    (S[3] => O[2]) = (0,0);
    (S[3] => O[3]) = (0,0);
    specparam PATHPULSE$ = 0;
  endspecify
endmodule
module chain_scalar(input CI, input [3:0] S, output [3:0] O);
  wire [3:0] c;
  assign c[0] = CI;
  assign c[3:1] = S[2:0] & c[2:0];
  assign O[0] = S[0] ^ c[0];
  assign O[1] = S[1] ^ c[1];
  assign O[2] = S[2] ^ c[2];
  assign O[3] = S[3] ^ c[3];
  specify
    (CI => O[0]) = (219,219);
    (CI => O[1]) = (323,323);
    (CI => O[2]) = (239,239);
    (CI => O[3]) = (0,0);
    (S[0] => O[0]) = (228,228);
    (S[0] => O[1]) = (403,403);
    (S[0] => O[2]) = (520,520);
    (S[0] => O[3]) = (0,0);
    (S[1] => O[0]) = (0,0);
    (S[1] => O[1]) = (210,210);
    (S[1] => O[2]) = (558,558);
    (S[1] => O[3]) = (0,0);
    (S[2] => O[0]) = (0,0);
    (S[2] => O[1]) = (0,0);
    (S[2] => O[2]) = (228,228);
    (S[2] => O[3]) = (0,0);
    (S[3] => O[0]) = (0,0);
    (S[3] => O[1]) = (0,0);
    (S[3] => O[2]) = (0,0);
    (S[3] => O[3]) = (0,0);
    specparam PATHPULSE$ = 0;
  endspecify
endmodule
module tb_path_reproducer;
  initial $sdf_annotate("chain.sdf",tb_path_reproducer);
  reg CI=1'b1;
  reg [3:0] S=4'b0111;
  wire [3:0] full_o,scalar_o;
  wire [17:3] parent;
  wire [3:3] unused;
  wire [3:0] split_o={unused[3],parent[17:15]};
  chain_vector full_vector(.CI(CI),.S(S),.O(full_o));
  chain_vector split_vector(.CI(CI),.S(S),.O({unused[3],parent[17:15]}));
  wire [17:3] scalar_parent;
  wire [3:3] scalar_unused;
  assign scalar_o={scalar_unused[3],scalar_parent[17:15]};
  chain_scalar split_scalar(.CI(CI),.S(S),.O({scalar_unused[3],scalar_parent[17:15]}));
  integer checks=0,discrepancies=0;
  reg [3:0] want;
  task check;
    begin
      $display("MINIMAL_POINT check=%0d time=%0t CI=%b S=%b full=%b split=%b scalar=%b want=%b",checks,$time,CI,S,full_o,split_o,scalar_o,want);
      if(full_o!==want || scalar_o!==want) $fatal(1,"MINIMAL_CONTROL_MISMATCH check=%0d time=%0t",checks,$time);
      if(split_o!==want) discrepancies=discrepancies+1;
      checks=checks+1;
    end
  endtask
  initial begin
    $dumpfile("path.vcd");$dumpvars(0,tb_path_reproducer);
    #9000;want=4'b1000;check;
    #1000;S=4'b0011;
    #66;S=4'b0001;
    #211;CI=0;
    #2000;want=4'b0001;
    if($test$plusargs("CORRUPT"))want=want^4'b1;
    check;
    if(discrepancies==0)$display("MINIMAL_ALL_CONTROLS_PASS checks=2");
    else $display("MINIMAL_SPLIT_DISCREPANCY checks=2 discrepancies=%0d",discrepancies);
    $finish;
  end
endmodule
