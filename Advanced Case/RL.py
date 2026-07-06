
def RL(chongfu, seed, user_id, board_type='fpga', failure_threshold=1):
    """
    参数:
    - failure_threshold: 滑动窗口中认证失败次数的阈值，默认15（窗口大小30的一半）
    """
    reward_log = []
    protection_level_log = []
    count_log = []
    latency_log = []
    energy_log = []
    ASR_log = []
    # 用于收集每个认证过程的 latency 和 energy 数据，便于归一化
    latency_samples = []
    energy_samples = []
    
    # 新增：记录密钥长度和会话时间选择的日志
    key_length_log = []
    session_time_log = []

    ppo_agent = PPO_NEW.PPO(state_dim, action1_dim, action2_dim, action3_dim, lr_actor, lr_critic,lr_E, gamma, K_epochs,
                        eps_clip, has_continuous_action_space,
                        action_std)

    window_size = 30  # 定义滑动窗口大小
    window_results = []  # 用于保存最近认证尝试结果 (1: 成功, 0: 失败)

    # 记录最后一个窗口的状态
    final_window_results = []

    for episod in range(1, episod_max):
        reward = 0
        next_state = []
        now = datetime.now()
        timestamp = now.timestamp()

        for step in tqdm(range(1, step_max)):
            Iov1 = env.IoV(UAV_ID=0)
            state = Iov1.observe() if step == 1 else next_state

            action0 = 0
            if step > 32:
                action1, action2 = ppo_agent.select_action(state, step)
            else:
                action1 = random.randint(0, 2)
                action2 = random.randint(0, 2)
                ppo_agent.buffer.states.append(state)
                ppo_agent.buffer.action0s.append(action1)
                ppo_agent.buffer.action1s.append(action2)

            # 获取选择的密钥长度和会话时间
            key_length = action3_set[action2]  # 密钥长度（位）
            session_time = action2_set[action1]  # 会话时间（秒）

            if action0 == 0:  # 使用PUF认证
                # 根据板子类型选择不同的认证函数
                if board_type == 'fpga':
                    latency, datasize, auth_success = UAV_Authentication(user_id, key_length)
                elif board_type == 'e10':
                    latency, datasize, auth_success = E10_Authentication(user_id, key_length)
                elif board_type == 'pico':
                    latency, datasize, auth_success = Pico_Authentication(user_id, key_length)
                else:
                    print(f"未知的板子类型: {board_type}，使用默认的 FPGA 认证")
                    latency, datasize, auth_success = UAV_Authentication(user_id, key_length)

                # 将本次认证结果记录到滑动窗口中（成功记1，失败记0）
                window_results.append(1 if auth_success else 0)

                # 如果滑动窗口长度超过 window_size，则移除最旧的结果
                if len(window_results) > window_size:
                    window_results.pop(0)

                # 保存最后一个窗口的结果
                final_window_results = window_results.copy()


            # print(f"protection_level={protection_level}")

            # 计算当前时隙的ASR（每个时隙都基于当前窗口判断）
            if step <= window_size:
                # 前30步，加载全局ASR（假设是合法者）
                ASR = load_global_asr()
            else:
                # 判断当前窗口是否为攻击者
                failure_count = window_results.count(0)  # 统计失败次数

                if failure_count > failure_threshold:
                    # 当前时隙判断为攻击者
                    success_count = window_results.count(1)
                    ASR = success_count / len(window_results)  # 攻击成功率
                else:
                    # 当前时隙判断为合法者
                    ASR = load_global_asr()  # 加载全局ASR

            print(f"ASR:{ASR}, 窗口失败次数:{window_results.count(0) if window_results else 0}")

            reward = Iov1.get_utility(latency1, energy1, ASR, protection_level, cost, count)
            next_state = Iov1.step(ASR, protection_level, latency * count, energy * count, count, UAV_ID)

            reward_tensor = torch.tensor(reward, dtype=torch.float32)
            ppo_agent.buffer.rewards.append(reward_tensor)
            ppo_agent.buffer.next_states.append(next_state)

            if step > 64:
                ppo_agent.update()


    # 保存日志文件
    rootpath = './log'
    os.makedirs(rootpath, exist_ok=True)

    log_data = {
        'reward': reward_log,
        'latency': latency_log,
        'energy': energy_log,
        'ASR': ASR_log,
        'protection_level': protection_level_log,
        'count': count_log,
        'key_length': key_length_log,  # 新增：密钥长度日志
        'session_time': session_time_log  # 新增：会话时间日志
    }

    return {
        "reward": last_reward,
        "latency": last_latency,
        "energy": last_energy,
        "ASR": final_asr,
        "protection_level": last_protection_level,
        "is_attacker": is_attacker,  # 只在chongfu==4时有意义
        "auth_success": not is_attacker,  # 合法者认证成功
        "final_window_results": final_window_results,  # 返回窗口结果供调试
        "chongfu": chongfu,  # 当前轮次
        "reward_log": reward_log,
        "latency_log": latency_log,
        "energy_log": energy_log,
        "ASR_log": ASR_log,
        "protection_level_log": protection_level_log,
        "count_log": count_log,
        "key_length_log": key_length_log,  # 新增：返回密钥长度日志
        "session_time_log": session_time_log  # 新增：返回会话时间日志
    }


