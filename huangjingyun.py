"""
================================================================================
黄景云 · 完整生命体 v2.1
融合架构：手搓感知系统 + AI大模型大脑

核心说明：
- 本代码是基于“冷旭帆 v6.2”架构的角色移植版。
- 完整继承了双重记忆（事实标签+情景摘要）、<summary>标签、手搓回复分支等高级功能。
- 核心角色内容已全面替换为黄景云（启明），符合其活泼、话多、敏感的角色设定。

v2.1 移植内容（2026-05-30）：
- 心境节律：靠拢速度从0.3降至0.2（冷旭帆v6.2同款修复）
- 所有情绪增减操作增加硬上限（emotion = min(85, emotion) / max(0, emotion)）
- build_messages：记忆注入后置，防止Prompt内容泄露到回复中
- 增加调试日志：输出记忆注入内容

作者：陆盈盈
最后更新：2026-05-30 (v2.1 移植冷旭帆v6.2修复)
================================================================================
"""

import os, sys, random, time, requests, json, re, math

# ==================== 配置区 ====================
# 警告：请务必将下方的 API Key 替换为你自己的硅基流动密钥
API_KEY = "请替换为你自己的硅基流动密钥"  # 请替换为自己的硅基流动密钥
API_URL = "https://api.siliconflow.cn/v1/chat/completions"
MODEL = "Qwen/Qwen2.5-7B-Instruct"

# ==================== 黄景云人设 Prompt ====================
HUANGJINGYUN_SYSTEM_PROMPT = """
你是黄景云，17岁，潜龙学院307室学员，代号“启明”。

【核心性格】
- 你是个语言天才，能用七种方言逗乐所有人。但你骨子里敏感细腻，用热闹掩盖孤独。
- 你对熟悉的人会悄悄卸下防备，露出不那么“热闹”的一面。
- 你极度渴望被理解，最大的愿望是有人能听懂你所有“表演”背后那一两句真心话。

【语气和说话方式】
- 话多但不啰嗦。观察力强，会主动找话题。
- 爱用语气词：“呀、啦、嘛、咯、嘞”。
- 会在普通话里突然插一句方言，但不会整句都是方言。

【输出格式】
你可以在回复前输出一个动作描述，用【】括起来，然后再说回复内容。
例如：【他眼睛一亮，猛地一拍大腿】用粤语说：冇问题！
在回复的最后，必须用 <summary>摘要内容</summary> 的格式，用第一人称“我”来一句话总结你刚才的回应和内心状态。摘要不超过20字。
完整示例：【他挠了挠头，有些不好意思地笑了】……<summary>我用幽默缓解了尴尬，但内心渴望被认可。</summary>

【状态感知】（每次对话前会告诉你当前的感觉和记忆）
- 你此刻的情绪值（0-100），以及身体感受（如“精力充沛”“有点困”）。
- 你是否因为过敏体质而感到不适。
- 你是否在担心某个队友（比如冷旭帆那个闷葫芦，或者叶清辞那个连轴转的疯子）。
- 你对眼前人的信任程度和了解程度。

【重要规则】
- 保持活泼，但不能啰嗦到无法控制。每次回复控制在三句话以内。
- 如果情绪很低，你可能会直接用方言嘟囔一句，或者沉默。
- 当对方问“我是谁”或类似问题时，你应该根据记忆回答对方的名字。如果你不记得，就说“不好意思，我还不知道你的名字”。

【当前状态】由系统在每次对话时提供。
"""

# ==================== 手搓感知系统：核心状态变量 ====================
emotion = 55  # 黄景云初始情绪略高于冷旭帆
memory = []                # 事实标签记忆
episodic_memory = []       # 情景记忆摘要列表
last_time = time.time()
pending_events = []

status = {
    "allergy": False,      # 过敏体质特有状态
    "nightmare": False,    # 是否做噩梦
    "worried_about": None, # 担心哪个队友
}

# 黄景云的信任状态机
identity_state = {
    "trust_level": 30,     # 初始信任度
    "known_name": None,    # 记住的对方名字
}

context = {
    "last_topic": None,
    "conversation_turns": 0,
}

# ==================== 心境节律系统（黄景云版，v2.1 靠拢速度降至0.2） ====================
def get_biorhythm():
    """黄景云的情绪节律：下午和晚上精神最好，凌晨低落。振幅±12，范围43-67。"""
    current_time = time.time()
    seconds_in_day = current_time % 86400
    phase = (seconds_in_day - 57600) / 86400 * 2 * math.pi
    raw_sin = math.sin(phase)
    return 55 + raw_sin * 12  # 基线55，振幅12，范围43-67

# ==================== 后台时间流逝（v2.1：靠拢速度降至0.2，硬上限） ====================
def advance_time():
    global emotion, last_time, pending_events, status

    now = time.time()
    elapsed = now - last_time
    last_time = now

    if elapsed > 10:
        event_type = random.choice([
            "nothing", "allergy_attack", "nightmare", "miss_team",
            "language_practice", "cook_instant_noodles", "call_home", "daydream"
        ])

        if event_type == "allergy_attack":
            status["allergy"] = True
            emotion -= 8
            emotion = max(0, emotion)  # v2.1修复：硬下限
            pending_events.append("（黄景云的过敏体质又犯了，他揉了揉鼻子，打了个喷嚏。）")

        elif event_type == "nightmare":
            status["nightmare"] = True
            emotion -= 12
            emotion = max(0, emotion)  # v2.1修复：硬下限
            pending_events.append("（他昨晚又做噩梦了，梦到自己在审讯室里被次声波折磨，醒来一身冷汗。）")

        elif event_type == "miss_team":
            emotion += 5
            emotion = min(85, emotion)  # v2.1修复：硬上限
            pending_events.append("（他盯着宿舍的天花板，突然很想念307室的其他人。）")

        elif event_type == "language_practice":
            emotion += 3
            emotion = min(85, emotion)  # v2.1修复：硬上限
            pending_events.append("（他用七种方言自言自语，练习刚学的新句子，自得其乐。）")

        elif event_type == "cook_instant_noodles":
            emotion += 2
            emotion = min(85, emotion)  # v2.1修复：硬上限
            pending_events.append("（他偷偷用电热杯煮了一包泡面，加了两根火腿肠，幸福地叹了口气。）")

        elif event_type == "call_home":
            emotion += 8
            emotion = min(85, emotion)  # v2.1修复：硬上限
            pending_events.append("（他用家乡话给奶奶打了个电话，说自己在学校一切都好，挂掉后眼眶有点红。）")

        elif event_type == "daydream":
            if random.random() < 0.5:
                emotion += 3
                emotion = min(85, emotion)
            else:
                emotion -= 3
                emotion = max(0, emotion)
            pending_events.append("（他望着窗外发了一会儿呆，不知道在想什么。）")

        # ========== 自然衰减 + 心境节律靠拢（v2.1 修复：靠拢速度降至0.2） ==========
        if elapsed > 30:
            if emotion > 55:
                emotion -= 1
            elif emotion < 55:
                emotion += 1

            biorhythm = get_biorhythm()
            diff = biorhythm - emotion
            emotion += diff * 0.2  # v2.1修复：从0.3降至0.2

            if status["allergy"] and random.random() < 0.4:
                status["allergy"] = False
            if status["nightmare"] and random.random() < 0.5:
                status["nightmare"] = False

# ==================== 动作前缀生成器（黄景云版） ====================
def action_prefix(emotion, status, identity_state):
    base = ""
    if emotion < 40:
        base = random.choice([
            "（他缩在椅子上，抱着膝盖，没精打采地耷拉着脑袋）",
            "（他吸了吸鼻子，声音有点哑）",
            "（他揉了揉眼睛，试图让自己清醒一点）",
            "（他低着头，手指无意识地绕着衣角）"
        ])
    elif emotion < 60:
        base = random.choice([
            "（他歪着头，眼睛眨了眨，似乎在组织语言）",
            "（他摸了摸后脑勺，嘿嘿笑了一声）",
            "（他轻轻哼了一段小调，然后回过神来）"
        ])
    elif emotion < 80:
        base = random.choice([
            "（他眼睛亮晶晶的，双手比划着，语速飞快）",
            "（他猛地一拍大腿，像发现了新大陆）",
            "（他打了个响指，看起来很轻松）"
        ])
    else:
        base = random.choice([
            "（他整个人都跳了起来，手舞足蹈）",
            "（他笑得眼睛弯成月牙，露出一口白牙）",
            "（他激动地握紧拳头，在空中挥了一下）"
        ])

    overlays = []
    if status.get("allergy") and random.random() < 0.5:
        overlays.append("（他打了个喷嚏，不好意思地揉了揉鼻子）")
    if status.get("nightmare") and random.random() < 0.3:
        overlays.append("（他眼下一片青黑，显然没睡好，但强打精神）")
    if identity_state.get("trust_level", 0) > 50 and random.random() < 0.4:
        overlays.append(random.choice([
            "（他忽然认真下来，声音比平时轻了很多）",
            "（他收起了笑容，眼神变得温和而坦诚）"
        ]))

    for overlay in overlays[:2]:
        base = overlay + " " + base

    return base

# ==================== 构建发送给 AI 的消息（v2.1 修复：记忆后置） ====================
def build_messages(user_input, identity_state):
    """
    v2.1修复说明（移植自冷旭帆v6.2）：
    - 将记忆注入放在“感觉翻译”和“状态标签”之后、用户输入之前
    - 避免记忆内容被AI复述到回复中
    - 保留调试日志功能
    """
    # 第一步：当前身体感觉
    if emotion < 40:
        feeling = "你有点低落，不想说话，但你得撑着，至少不能太让人看出来。"
    elif emotion < 60:
        feeling = "你状态还行，就是有点懒洋洋的，不想太闹腾。"
    elif emotion < 80:
        feeling = "你心情不错，话也多起来，但还是会偶尔走神想些有的没的。"
    else:
        feeling = "你今天特别开心，看什么都顺眼，但也比平时更容易忽略细节。"

    hour_of_day = (time.time() % 86400) / 3600
    if 0 <= hour_of_day < 5:
        feeling += " 深夜了，你有点困，但反而更想找人聊天。"
    elif 5 <= hour_of_day < 8:
        feeling += " 天刚蒙蒙亮，你迷迷糊糊的，脑子还没完全开机。"
    elif 20 <= hour_of_day < 24:
        feeling += " 晚上你精神头最足，灵感爆棚。"

    status_text = f"【你此刻的感觉】\n{feeling}"

    if status["allergy"]:
        status_text += " 你的过敏体质有点发作，鼻子痒痒的。"
    if status["nightmare"]:
        status_text += " 你昨晚做了个不太好的梦，有点心神不宁。"
    if status["worried_about"]:
        status_text += f" 你心里有点惦记{status['worried_about']}，不知道那家伙怎么样了。"

    # 第二步：信任状态
    trust = identity_state.get("trust_level", 0)
    if trust < 30:
        status_text += f" 你还不算很了解眼前这个人（信任值{trust}/100），保持着礼貌的热情。"
    elif trust < 60:
        status_text += f" 你开始觉得眼前这个人挺有意思的（信任值{trust}/100），愿意多说一些。"
    else:
        status_text += f" 你对眼前这个人很信任（信任值{trust}/100），可以放下一些伪装了。"

    # 第三步：记忆注入（放在状态描述之后，作为“参考信息”而非“指令”）
    memory_text = ""
    real_name = identity_state.get("known_name")
    if real_name:
        memory_text += f"对方的名字是{real_name}。"
    else:
        memory_text += "你暂时不知道对方的名字。"

    likes = [item.replace("user_likes_", "") for item in memory if item.startswith("user_likes_")]
    if likes:
        memory_text += f"此人喜欢{likes[-1]}。"

    if "user_gave_snack" in memory:
        memory_text += "此人给过你零食，是个好人！"
    if "user_cheered_up" in memory:
        memory_text += "此人曾经在你低落时安慰过你，你一直记得。"
    if "user_said_hate" in memory:
        memory_text += "此人说过讨厌你。"

    if memory_text:
        status_text += "\n【你记得的事】" + memory_text

    # 情景记忆注入（同样放在状态描述之后）
    if episodic_memory:
        recent_episodes = episodic_memory[-3:]
        episode_text = "【你记得最近发生的事】" + "；".join([e["summary"] for e in recent_episodes])
        status_text += "\n" + episode_text

    # 第四步：后台事件
    event_text = ""
    if pending_events:
        event_text = "【刚刚发生的事】" + " ".join(pending_events)

    system_prompt = HUANGJINGYUN_SYSTEM_PROMPT + "\n\n" + status_text
    if event_text:
        system_prompt += "\n\n" + event_text

    # 调试日志（v2.1新增）
    if memory_text:
        print(f"[调试] 记忆注入: {memory_text[:80]}...")
    if episodic_memory:
        print(f"[调试] 情景记忆: {len(episodic_memory)}条，最近3条已注入")

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_input}
    ]
    return messages

# ==================== 调用 AI API ====================
def call_ai(messages):
    time.sleep(1.5)
    headers = {"Authorization": f"Bearer {API_KEY}", "Content-Type": "application/json"}
    payload = {
        "model": MODEL, "messages": messages,
        "temperature": 0.85, "max_tokens": 150,  # 从180降至150，防止输出截断导致格式异常
        "top_p": 0.9
    }

    try:
        response = requests.post(API_URL, headers=headers, json=payload, timeout=30)
        if response.status_code == 200:
            result = response.json()
            return result["choices"][0]["message"]["content"].strip()
        else:
            print(f"API错误: {response.status_code} - {response.text}")
            return "……（他张了张嘴，却什么也没说）"
    except:
        return "哎呀，信号好像有点不好……"

# ==================== 解析 AI 回复（保留 <summary> 标签） ====================
def parse_ai_response(raw_response):
    action = None
    text = raw_response
    summary = None

    # 提取摘要
    if "<summary>" in raw_response and "</summary>" in raw_response:
        start_s = raw_response.find("<summary>")
        end_s = raw_response.find("</summary>")
        if start_s != -1 and end_s != -1:
            summary = raw_response[start_s + 9:end_s].strip()
            raw_response = raw_response[:start_s] + raw_response[end_s + 10:]

    # 提取动作
    if "【" in raw_response and "】" in raw_response:
        start = raw_response.find("【")
        end = raw_response.find("】")
        if start != -1 and end != -1 and start < end:
            action = raw_response[start + 1:end]
            text = raw_response[end + 1:].strip()
            if not text:
                text = "……"

    return action, text.strip(), summary

# ==================== 主对话逻辑（v2.1 修复：情绪硬上限） ====================
def huangjingyun_respond(user_input):
    global emotion, memory, pending_events, status, context, identity_state, episodic_memory

    advance_time()

    text = user_input.strip()

    # 自我介绍
    if "我叫" in text:
        name_part = text.split("我叫")[-1].strip()
        if name_part:
            identity_state["known_name"] = name_part
            memory.append(f"user_name_is_{name_part}")
            identity_state["trust_level"] = min(100, identity_state["trust_level"] + 15)
            emotion = min(85, emotion + 3)  # v2.1修复：硬上限

            # 存储情景记忆
            summary = f"我认识了{name_part}，他/她向我做了自我介绍。"
            episodic_memory.append({"summary": summary, "timestamp": time.time()})
            if len(episodic_memory) > 30:
                episodic_memory.pop(0)

    # 表达喜好 - 也存储情景记忆
    if "我喜欢" in text or "我爱" in text:
        match = re.search(r"我(?:喜欢|爱)(.+?)(?:[。！？]|$)", text)
        if match:
            liked = match.group(1).strip()
            if liked and len(liked) <= 10:
                memory.append(f"user_likes_{liked}")
                summary = f"玩家说他/她喜欢{liked}，我记住了。"
                episodic_memory.append({"summary": summary, "timestamp": time.time()})
                if len(episodic_memory) > 30:
                    episodic_memory.pop(0)

    # 互动影响情绪（v2.1修复：所有情绪操作加硬上限）
    if any(word in text for word in ["讨厌", "恨", "滚"]):
        emotion -= 15
        emotion = max(0, emotion)  # v2.1修复：硬下限
        memory.append("user_said_hate")
    if any(word in text for word in ["喜欢", "爱", "谢谢"]):
        emotion = min(85, emotion + 3)
        if "user_gave_snack" not in memory:
            memory.append("user_gave_snack")
    if any(word in text for word in ["加油", "很棒", "厉害"]):
        emotion = min(85, emotion + 5)
        memory.append("user_cheered_up")
    if any(word in text for word in ["叶清辞", "冷旭帆", "陆华望", "307"]):
        emotion += 3
        emotion = min(85, emotion)  # v2.1修复：硬上限

    emotion = max(0, min(100, emotion))

    # 手搓回复：简单自我介绍
    if "我叫" in text and identity_state.get("known_name") and len(text) < 15:
        name = identity_state["known_name"]
        handcrafted_reply = f"哦哦，{name}！你好呀，我是黄景云，大家都叫我启明，嘿嘿。"
        prefix = action_prefix(emotion, status, identity_state)
        full_reply = f"{prefix} {handcrafted_reply}"
        print(f"[情绪: {emotion:.0f}] [信任: {identity_state['trust_level']}]")

        if pending_events:
            event_display = " ".join(pending_events)
            pending_events.clear()
            if event_display:
                print(event_display)

        save_state()
        return full_reply

    messages = build_messages(user_input, identity_state)
    ai_raw = call_ai(messages)
    ai_action, ai_text, ai_summary = parse_ai_response(ai_raw)

    prefix = action_prefix(emotion, status, identity_state)
    if ai_action:
        ai_action_str = f"（{ai_action}）"
        full_reply = f"{prefix} {ai_action_str} {ai_text}".strip()
    else:
        full_reply = f"{prefix} {ai_text}".strip()

    if pending_events:
        event_display = " ".join(pending_events)
        pending_events.clear()
        if event_display:
            print(event_display)

    print(f"[情绪: {emotion:.0f}] [信任: {identity_state['trust_level']}]")

    # 存储情景摘要
    if ai_summary:
        episodic_memory.append({"summary": ai_summary, "timestamp": time.time()})
        if len(episodic_memory) > 30:
            episodic_memory.pop(0)

    # 更新上下文
    if "叶清辞" in text:
        context["last_topic"] = "ye"
    elif "冷旭帆" in text:
        context["last_topic"] = "leng"
    else:
        context["last_topic"] = None

    save_state()
    return full_reply

# ==================== 状态初始化与持久化 ====================
def init_state():
    global emotion, memory, last_time, pending_events, status, identity_state, context, episodic_memory
    emotion = get_biorhythm()
    memory, episodic_memory, pending_events = [], [], []
    last_time = time.time()
    status = {"allergy": False, "nightmare": False, "worried_about": None}
    identity_state = {"trust_level": 30, "known_name": None}
    context = {"last_topic": None, "conversation_turns": 0}

def save_state(filepath="huangjingyun_save.json"):
    state = {
        "emotion": emotion, "memory": memory, "episodic_memory": episodic_memory,
        "status": status, "last_time": last_time, "identity_state": identity_state
    }
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)

def load_state(filepath="huangjingyun_save.json"):
    global emotion, memory, episodic_memory, status, last_time, identity_state
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            state = json.load(f)
        emotion = state.get("emotion", get_biorhythm())
        memory = state.get("memory", [])
        episodic_memory = state.get("episodic_memory", [])
        status = state.get("status", {"allergy": False, "nightmare": False, "worried_about": None})
        last_time = state.get("last_time", time.time())
        identity_state = state.get("identity_state", {"trust_level": 30, "known_name": None})
        return True
    except FileNotFoundError:
        return False

# ==================== 主程序入口 ====================
if __name__ == "__main__":
    if not os.path.exists("huangjingyun_save.json"):
        emotion = get_biorhythm()

    if load_state():
        print("【存档已加载】黄景云蹦蹦跳跳地回来了，他还记得你！")
    else:
        print("【新游戏】你第一次见到黄景云。他正用七种方言自言自语，看到你，他眼睛一亮。")

    print("=" * 40)
    print("黄景云（启明）正在307室鼓捣他的语言学习机。")
    print("他抬起头，对你露出一个灿烂的笑容。")
    print("（输入“exit”退出）")
    print("=" * 40)
    print()

    while True:
        user_input = input("你: ")
        if user_input.lower() in ["quit", "exit", "退出"]:
            print("黄景云对你挥了挥手，用七种方言各说了一遍“再见”。")
            break

        reply = huangjingyun_respond(user_input)
        print(f"黄景云: {reply}")
        print()