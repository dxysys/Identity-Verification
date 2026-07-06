module fpga_puf #(
  parameter integer ID_SIZE = 48, // PUF ID位数（默认96位）
  parameter integer CHALLENGE_WIDTH = 192      // 挑战位宽
)(
  input  wire                       clk_i,   // 全局时钟
  input  wire                       rstn_i,  // 同步复位（低有效）
  input  wire                       trig_i,  // 触发信号（上升沿脉冲触发采样）
  input  wire [CHALLENGE_WIDTH:0]   CHALLENGE,// 获得的384位挑战
  output wire                       busy_o,  // 采样过程中输出高电平
  output wire [ID_SIZE-1:0]         id_o     // PUF ID输出（采样完成后有效）
);

  // PLL输出时钟
  wire clk_1, clk_2, clk_3, clk_4; // PLL输出的四个时钟

  // 实例化PLL模块
  ip_pll u_ip_pll (
    .sys_clk(clk_i),        // 使用全局时钟作为PLL输入
    .sys_rst_n(rstn_i),     // 系统复位
    .clk_1(clk_1),          // 第一个时钟
    .clk_2(clk_2),          // 第二个时钟
    .clk_3(clk_3),          // 第三个时钟
    .clk_4(clk_4)           // 第四个时钟
  );
  
  
  // FSM状态编码
  localparam [1:0] S_IDLE   = 2'b00,
                   S_RUN    = 2'b01,
                   S_SAMPLE = 2'b10;

  // 内部寄存器
  reg [1:0]       state;
  reg [ID_SIZE-1:0] sreg;     // 修正：移位寄存器长度改为ID_SIZE位
  reg [1:0]       next_state;
  reg [ID_SIZE-1:0] next_sreg;

  // 根据当前状态生成采样信号
  wire sample = (state == S_SAMPLE);
  assign busy_o = (state != S_IDLE);

  // 实例化PUF单元数组
  genvar i;
  generate 
    for (i = 0; i < ID_SIZE; i = i + 1) begin : puf_cells
      fpga_puf_cell cell_i (
        .clk_i    (clk_i),
        .reset_i  (sreg[i]),        // 复位信号由移位寄存器控制
        .latch_i  (sreg[(i+1)%ID_SIZE]), // 循环移位，修正索引越界
        .sample_i (sample),
        .challenge(CHALLENGE[4*i +: 4]), // 每4位挑战输入
		.clk_1    (clk_1),		
		.clk_2    (clk_2),
		.clk_3    (clk_3),
		.clk_4    (clk_4),
        .data_o   (id_o[i])
      );
    end
  endgenerate

  // FSM和移位寄存器时序逻辑
  always @(posedge clk_i) begin
    if (!rstn_i) begin
      state <= S_IDLE;
      sreg  <= {ID_SIZE{1'b0}};
    end else begin
      next_state = state;
      next_sreg  = {sreg[ID_SIZE-2:0], 1'b0}; // 左移一位

      case (state)
        S_IDLE: begin 
          if (trig_i) begin
            next_sreg[0] = 1'b1;    // 插入启动脉冲
            next_state   = S_RUN;
          end
        end

        S_RUN: begin 
          // 当最高位为1时进入采样状态
          if (sreg[ID_SIZE-1]) begin  // 修正：检查最高位
            next_state = S_SAMPLE;
          end
        end

        S_SAMPLE: begin 
          next_state = S_IDLE;       // 采样后返回空闲
        end

        default: next_state = S_IDLE;
      endcase

      state <= next_state;
      sreg  <= next_sreg;
    end
  end

endmodule


module fpga_puf_cell(
  input  wire clk_i,
  input  wire reset_i,   // 异步复位（高有效）
  input  wire latch_i,   // 锁存控制信号
  input  wire sample_i,  // 采样使能信号
  input  wire [3:0] challenge, // 4位挑战输入
  input  wire clk_1,
  input  wire clk_2,
  input  wire clk_3,
  input  wire clk_4,
  output reg  data_o     // PUF单元输出位
);

  // 选择挑战值指定的两个 PLL 时钟
  wire [1:0] osc_a_idx = challenge[3:2];
  wire [1:0] osc_b_idx = challenge[1:0];

  // 选择两个 PLL 时钟
  wire clk_a = (osc_a_idx == 2'b00) ? clk_1 :
               (osc_a_idx == 2'b01) ? clk_2 :
               (osc_a_idx == 2'b10) ? clk_3 : clk_4;
                                         
  wire clk_b = (osc_b_idx == 2'b00) ? clk_1 :
               (osc_b_idx == 2'b01) ? clk_2 :
               (osc_b_idx == 2'b10) ? clk_3 : clk_4;

  // 在 PLL 时钟域上计数周期
  reg [31:0] counter_a = 0;
  reg [31:0] counter_b = 0;

  always @(posedge clk_a or posedge reset_i) begin
    if (reset_i) counter_a <= 0;
    else counter_a <= counter_a + 1;
  end

  always @(posedge clk_b or posedge reset_i) begin
    if (reset_i) counter_b <= 0;
    else counter_b <= counter_b + 1;
  end

  // 在 clk_i（50MHz）时钟域同步计数值
  reg [31:0] counter_a_sync, counter_b_sync;
  always @(posedge clk_i) begin
    counter_a_sync <= counter_a;
    counter_b_sync <= counter_b;
  end

  // 采样时比较两个 PLL 时钟的计数值
  always @(posedge clk_i or posedge reset_i) begin
    if (reset_i) 
      data_o <= 1'b0;
    else if (sample_i) begin
      if (counter_a_sync > counter_b_sync)
        data_o <= 1'b1;
      else
        data_o <= 1'b0;
    end
  end

endmodule
