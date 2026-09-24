`timescale 1ns/1ps

module trace_tb;
    localparam integer NUM_PORTS = 4;
    localparam integer SEL_WIDTH = 2;
    localparam integer ROWS = 48;

    reg clk;
    reg rst;
    reg [NUM_PORTS-1:0] request;
    wire [NUM_PORTS-1:0] grant;
    wire [SEL_WIDTH-1:0] select;
    wire active;

    integer context_id;
    integer variant_id;
    integer out_fd;
    integer cycle;
    integer fault_fired;
    integer fault_this_cycle;
    reg [NUM_PORTS-1:0] forced_token;
    reg [NUM_PORTS-1:0] forced_grant;
    reg [SEL_WIDTH-1:0] forced_select;
    reg [11:0] row_bits;
    string out_path;

    arbiter #(
        .NUM_PORTS(NUM_PORTS),
        .SEL_WIDTH(SEL_WIDTH)
    ) dut (
        .clk(clk),
        .rst(rst),
        .request(request),
        .grant(grant),
        .select(select),
        .active(active)
    );

    always #5 clk = ~clk;

    function [NUM_PORTS-1:0] request_for_cycle;
        input integer ctx;
        input integer c;
        integer phase;
        begin
            if (ctx == 0) begin
                phase = (c / 3) % 8;
                case (phase)
                    0: request_for_cycle = 4'b0001;
                    1: request_for_cycle = 4'b0010;
                    2: request_for_cycle = 4'b0100;
                    3: request_for_cycle = 4'b1000;
                    4: request_for_cycle = 4'b0011;
                    5: request_for_cycle = 4'b1100;
                    6: request_for_cycle = 4'b0101;
                    default: request_for_cycle = 4'b0000;
                endcase
            end else if (ctx == 1) begin
                phase = (c / 2) % 8;
                case (phase)
                    0: request_for_cycle = 4'b0011;
                    1: request_for_cycle = 4'b0110;
                    2: request_for_cycle = 4'b1100;
                    3: request_for_cycle = 4'b1001;
                    4: request_for_cycle = 4'b1111;
                    5: request_for_cycle = 4'b1010;
                    6: request_for_cycle = 4'b0101;
                    default: request_for_cycle = 4'b0000;
                endcase
            end else begin
                phase = c % 12;
                case (phase)
                    0: request_for_cycle = 4'b0000;
                    1: request_for_cycle = 4'b1111;
                    2: request_for_cycle = 4'b0001;
                    3: request_for_cycle = 4'b1011;
                    4: request_for_cycle = 4'b0100;
                    5: request_for_cycle = 4'b1110;
                    6: request_for_cycle = 4'b0010;
                    7: request_for_cycle = 4'b1001;
                    8: request_for_cycle = 4'b0111;
                    9: request_for_cycle = 4'b1000;
                    10: request_for_cycle = 4'b0101;
                    default: request_for_cycle = 4'b0011;
                endcase
            end
        end
    endfunction

    function integer fault_cycle_for_variant;
        input integer variant;
        begin
            case (variant)
                1, 3, 5, 7: fault_cycle_for_variant = 8;
                2, 4, 6, 8: fault_cycle_for_variant = 22;
                default: fault_cycle_for_variant = -1;
            endcase
        end
    endfunction

    task release_forced_state;
        begin
            case (variant_id)
                3, 4: release dut.token;
                5, 6: release dut.grant;
                7, 8: release dut.select;
                default: ;
            endcase
        end
    endtask

    initial begin
        clk = 1'b0;
        rst = 1'b1;
        request = 4'b0000;
        fault_fired = 0;
        fault_this_cycle = 0;

        if (!$value$plusargs("CONTEXT=%d", context_id)) context_id = 0;
        if (!$value$plusargs("VARIANT=%d", variant_id)) variant_id = 0;
        if (!$value$plusargs("OUT=%s", out_path)) begin
            $display("ERROR missing +OUT=...");
            $finish_and_return(2);
        end
        if (context_id < 0 || context_id > 2 || variant_id < 0 || variant_id > 8) begin
            $display("ERROR bad context or variant");
            $finish_and_return(3);
        end

        out_fd = $fopen(out_path, "w");
        if (out_fd == 0) begin
            $display("ERROR could not open output");
            $finish_and_return(4);
        end
        $fdisplay(out_fd, "cycle,request0,request1,request2,request3,grant0,grant1,grant2,grant3,select0,select1,active,token0,row");

        repeat (3) @(posedge clk);
        @(negedge clk);
        rst = 1'b0;

        for (cycle = 0; cycle < ROWS; cycle = cycle + 1) begin
            @(negedge clk);
            request = request_for_cycle(context_id, cycle);
            fault_this_cycle = (cycle == fault_cycle_for_variant(variant_id));

            if (fault_this_cycle) begin
                case (variant_id)
                    1, 2: begin
                        request[0] = ~request[0];
                    end
                    3, 4: begin
                        forced_token = {dut.token[2:0], dut.token[3]};
                        if (forced_token == 4'b0000)
                            forced_token = 4'b0001;
                        force dut.token = forced_token;
                    end
                    5, 6: begin
                        forced_grant = dut.grant ^ 4'b0001;
                        force dut.grant = forced_grant;
                    end
                    7, 8: begin
                        forced_select = dut.select ^ 2'b01;
                        force dut.select = forced_select;
                    end
                    default: ;
                endcase
                fault_fired = fault_fired + 1;
            end

            @(posedge clk);
            #1;
            row_bits = {
                dut.token[0],
                active,
                select[1], select[0],
                grant[3], grant[2], grant[1], grant[0],
                request[3], request[2], request[1], request[0]
            };
            $fdisplay(out_fd,
                "%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d,%03h",
                cycle,
                request[0], request[1], request[2], request[3],
                grant[0], grant[1], grant[2], grant[3],
                select[0], select[1], active, dut.token[0], row_bits);

            if (fault_this_cycle)
                release_forced_state();
        end

        $fclose(out_fd);
        if ((variant_id == 0 && fault_fired != 0) ||
            (variant_id != 0 && fault_fired != 1)) begin
            $display("ERROR FAULT_FIRED=%0d", fault_fired);
            $finish_and_return(5);
        end
        $display("DONE CONTEXT=%0d VARIANT=%0d FAULT_FIRED=%0d ROWS=%0d", context_id, variant_id, fault_fired, ROWS);
        $finish;
    end
endmodule
