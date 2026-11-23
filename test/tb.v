`timescale 1ns / 1ps
`default_nettype none

module tb;
    reg clk;
    reg rst_n;
    reg [7:0] ui_in;
    wire [7:0] uo_out;
    wire [7:0] uio_out;
    wire [7:0] uio_oe;

`ifdef GL_TEST
    supply1 vpwr;
    supply0 vgnd;
`endif

    `DUT_MODULE dut (
`ifdef GL_TEST
        .VPWR(vpwr),
        .VGND(vgnd),
`endif
        .clk(clk),
        .rst_n(rst_n),
        .ena(1'b1),
        .ui_in(ui_in),
        .uo_out(uo_out),
        .uio_in(8'b0),
        .uio_out(uio_out),
        .uio_oe(uio_oe)
    );
endmodule

`default_nettype wire
