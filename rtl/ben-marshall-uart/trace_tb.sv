`timescale 1ns/1ps
module trace_tb;
  localparam integer PAYLOAD_BITS = 4;
  localparam integer BIT_RATE = 1_000_000;
  localparam integer CLK_HZ = 4_000_000;

  reg clk = 1'b0;
  reg resetn = 1'b0;
  reg uart_tx_en = 1'b0;
  reg uart_rx_en = 1'b1;
  reg [PAYLOAD_BITS-1:0] uart_tx_data = 0;
  reg line_fault = 1'b0;
  wire uart_txd;
  wire uart_tx_busy;
  wire uart_rxd = uart_txd ^ line_fault;
  wire uart_rx_break;
  wire uart_rx_valid;
  wire [PAYLOAD_BITS-1:0] uart_rx_data;

  integer payload = 5;
  integer fault_kind = 0;
  integer fault_cycle = -1;
  integer fault_value = 0;
  integer rows = 48;
  integer c = 0;
  integer fault_fired = 0;
  integer unknown_rows = 0;
  integer rx_valid_count = 0;
  integer fd;
  reg fault_active = 1'b0;
  reg [11:0] row;
  string trace_path;

  always #5 clk = ~clk;

  uart_tx #(
    .BIT_RATE(BIT_RATE), .CLK_HZ(CLK_HZ),
    .PAYLOAD_BITS(PAYLOAD_BITS), .STOP_BITS(1)
  ) tx (
    .clk(clk), .resetn(resetn), .uart_txd(uart_txd),
    .uart_tx_busy(uart_tx_busy), .uart_tx_en(uart_tx_en),
    .uart_tx_data(uart_tx_data)
  );

  uart_rx #(
    .BIT_RATE(BIT_RATE), .CLK_HZ(CLK_HZ),
    .PAYLOAD_BITS(PAYLOAD_BITS), .STOP_BITS(1)
  ) rx (
    .clk(clk), .resetn(resetn), .uart_rxd(uart_rxd),
    .uart_rx_en(uart_rx_en), .uart_rx_break(uart_rx_break),
    .uart_rx_valid(uart_rx_valid), .uart_rx_data(uart_rx_data)
  );

  // Faults are armed on a falling edge so they are stable for exactly one
  // sampled rising edge. Kinds: 1=line, 2=TX state, 3=TX data bit 0,
  // 4=RX state, 5=RX sampled bit.
  always @(negedge clk) begin
    if (resetn && !fault_active && fault_kind != 0 && c == fault_cycle) begin
      fault_active = 1'b1;
      fault_fired = fault_fired + 1;
      case (fault_kind)
        1: line_fault = 1'b1;
        2: force tx.fsm_state = fault_value[2:0];
        3: force tx.data_to_send[0] = fault_value[0];
        4: force rx.fsm_state = fault_value[2:0];
        5: force rx.bit_sample = fault_value[0];
        default: begin
          $display("ERROR invalid fault kind %0d", fault_kind);
          $finish_and_return(2);
        end
      endcase
    end else if (fault_active && c == fault_cycle + 1) begin
      case (fault_kind)
        1: line_fault = 1'b0;
        2: release tx.fsm_state;
        3: release tx.data_to_send[0];
        4: release rx.fsm_state;
        5: release rx.bit_sample;
      endcase
      fault_active = 1'b0;
    end
  end

  initial begin
    if (!$value$plusargs("PAYLOAD=%d", payload)) payload = 5;
    if (!$value$plusargs("FAULT_KIND=%d", fault_kind)) fault_kind = 0;
    if (!$value$plusargs("FAULT_CYCLE=%d", fault_cycle)) fault_cycle = -1;
    if (!$value$plusargs("FAULT_VALUE=%d", fault_value)) fault_value = 0;
    if (!$value$plusargs("ROWS=%d", rows)) rows = 48;
    if (!$value$plusargs("TRACE=%s", trace_path)) begin
      $display("ERROR missing TRACE plusarg");
      $finish_and_return(2);
    end
    if (payload < 0 || payload >= (1 << PAYLOAD_BITS) || rows < 1) begin
      $display("ERROR invalid payload/rows");
      $finish_and_return(2);
    end
    uart_tx_data = payload[PAYLOAD_BITS-1:0];
    fd = $fopen(trace_path, "w");
    if (fd == 0) begin
      $display("ERROR cannot open trace %s", trace_path);
      $finish_and_return(2);
    end
    $fdisplay(fd, "cycle,txd,tx_busy,tx_fsm0,tx_fsm1,tx_bit0,tx_bit1,tx_data0,rxd,rx_valid,rx_fsm0,rx_fsm1,rx_sample,row");

    repeat (3) @(posedge clk);
    #1 resetn = 1'b1;
    @(negedge clk); uart_tx_en = 1'b1;
    @(negedge clk); uart_tx_en = 1'b0;

    for (c = 0; c < rows; c = c + 1) begin
      @(posedge clk); #1;
      row = {rx.bit_sample, rx.fsm_state[1], rx.fsm_state[0], uart_rx_valid,
             uart_rxd, tx.data_to_send[0], tx.bit_counter[1], tx.bit_counter[0],
             tx.fsm_state[1], tx.fsm_state[0], uart_tx_busy, uart_txd};
      if (^row === 1'bx) unknown_rows = unknown_rows + 1;
      if (uart_rx_valid) rx_valid_count = rx_valid_count + 1;
      $fdisplay(fd, "%0d,%b,%b,%b,%b,%b,%b,%b,%b,%b,%b,%b,%b,%0d",
                c, uart_txd, uart_tx_busy, tx.fsm_state[0], tx.fsm_state[1],
                tx.bit_counter[0], tx.bit_counter[1], tx.data_to_send[0],
                uart_rxd, uart_rx_valid, rx.fsm_state[0], rx.fsm_state[1],
                rx.bit_sample, row);
    end
    $fclose(fd);
    $display("RESULT rows=%0d fired=%0d unknown=%0d rx_valid=%0d rx_data=%0d",
             rows, fault_fired, unknown_rows, rx_valid_count, uart_rx_data);
    if (fault_active) begin
      $display("ERROR fault remained active");
      $finish_and_return(3);
    end
    if (fault_kind == 0 && fault_fired != 0) begin
      $display("ERROR nominal fault count");
      $finish_and_return(3);
    end
    if (fault_kind != 0 && fault_fired != 1) begin
      $display("ERROR fault did not fire exactly once");
      $finish_and_return(3);
    end
    if (unknown_rows != 0) begin
      $display("ERROR unknown captured rows");
      $finish_and_return(3);
    end
    $finish;
  end
endmodule
