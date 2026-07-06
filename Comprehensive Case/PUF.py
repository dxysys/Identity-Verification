
CAR_SERVER_URL_Authentication= ("http://10.220.229.195:5000/fpga/authenticate")
CAR_SERVER_URL_Registration = "http://10.220.229.195:5000/fpga/register"

FIXED_KEYS = {
    128: b"0123456789012345",              # 16 字节 -> 128 位
    192: b"012345678901234567890123",        # 24 字节 -> 192 位
    256: b"01234567890123456789012345678901"  # 32 字节 -> 256 位
}

def fpga_get_response(challenge_bytes, baudrate=115200, response_timeout=60):

    serial_port = get_default_serial_port()
    try:
        ser = serial.Serial(port=serial_port, baudrate=baudrate, timeout=1)
    except Exception as e:
        raise Exception(f"打开串口 {serial_port} 失败: {e}")

    # 发送挑战数据
    ser.write(challenge_bytes)

    response_bytes = b""
    start_time = time.time()
    while len(response_bytes) < 16 and (time.time() - start_time) < response_timeout:
        response_bytes += ser.read(16 - len(response_bytes))
    ser.close()

    if len(response_bytes) < 16 :
        raise Exception("未接收到足够的响应字节")
    return response_bytes

def UAV_Authentication(uav_id, aes_key_length_bits):

    start_time = time.time()


    conn = sqlite3.connect("registration.db")
    cursor = conn.cursor()
    cursor.execute("SELECT pairs FROM registration WHERE uav_id = ?", (uav_id,))
    row = cursor.fetchone()
    conn.close()

    if not row:
        raise Exception("未找到该 Vehicle 的注册记录")

    pairs_json = row[0]
    pairs_list = json.loads(pairs_json)
    if not pairs_list:
        raise Exception("没有可用的挑战–响应对")

    pairs = []
    for pair in pairs_list:
        challenge_bytes = bytes.fromhex(pair["challenge"])
        expected_response = bytes.fromhex(pair["response"])
        pairs.append((challenge_bytes, expected_response))

    selected_pair = random.choice(pairs)
    challenge, expected_response = selected_pair

    if aes_key_length_bits not in FIXED_KEYS:
        raise Exception("不支持的密钥长度")
    sim_key = FIXED_KEYS[aes_key_length_bits]

    board_response = get_car_response_encrypted(challenge, sim_key)

    if board_response == expected_response:
        auth_success = True
        print("确认，认证成功")
    else:
        auth_success = False
        print("警告：认证失败！")


    end_time = time.time()
    latency = end_time - start_time

    datasize = (len(challenge) + len(board_response)+len(sim_key)) * 8

    datasize = 1664
    return latency, datasize,auth_success
