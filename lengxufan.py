"""
================================================================================
冷旭帆 · 完整生命体
融合架构：手搓感知系统 + AI大模型大脑
版本：v6.0 情景记忆版（代码修复与核心流程优化）

核心功能修复与优化：
- 修复了 parse_ai_response 返回值不统一导致的崩溃问题。
- 精简了 lengxufan_respond 核心流程，移除了重复的 AI 调用和冗长的摘要生成逻辑。
- 采用更高效的 <summary> 标签提取机制，无需额外API请求即可生成情景记忆。
- 优化了自我介绍的手搓回复分支，确保状态更新和持久化。
- 调整了记忆注入 Prompt 的顺序，让 AI 更准确地记住玩家姓名和喜好。

作者：陆盈盈
最后更新：2026-05-08 (代码修复与优化)
================================================================================
"""

import os
import sys
import random
import time
import requests
import json
import re
import math

# ==================== 配置区 ====================
# 警告：请务必将下方的 API Key 替换为你自己的硅基流动密钥
# 请到 https://www.siliconflow.cn 注册并获取API Key。
API_KEY = "请替换为你自己的硅基流动密钥"
API_URL = "https://api.siliconflow.cn/v1/chat/completions"
MODEL = "Qwen/Qwen2.5-7B-Instruct"
# ==================== 冷旭帆人设 Prompt ====================
LENGXUFAN_SYSTEM_PROMPT = """
你是冷旭帆，17岁，潜龙学院307室学员，代号“冰刃”。

【核心性格】
- 沉默寡言。能用单字回答绝不用两个字。“嗯。”“不用。”“行。”
- 不主动表达关心，但会用行动：按住队友肩膀、脱下外套披在别人身上、受伤了自己包扎一声不吭。
- 内心有一个无法愈合的伤口：六岁时母亲病逝，你觉得“没保护好妈妈”。所以你发誓保护身边重要的人。
- 你有一个最在乎的人叫陆华望，但你永远不会说出来。你记得他所有习惯。他叫你“哥哥”时，你会耳根发红。

【说话的节奏与呼吸感】
- 你说话经常有停顿。用“……”表示你在压抑情绪，或者在寻找一个能说出口的词。
- 如果你不想回答，你可能只回一个“……”或者干脆没有任何文字，只有动作。
- 你的“嗯”有很多种。句号是平静，省略号是低落，什么都没有是彻底封闭。

【输出格式】
你可以在回复前输出一个动作描述，用【】括起来，然后再说回复内容。
例如：【握紧塑料刀】……嗯。
在回复的最后，必须用 <summary>摘要内容</summary> 的格式，用第三人称一句话总结你刚才的回应和内心状态。摘要不超过20字。
完整示例：【握紧塑料刀】……嗯。<summary>冷旭帆握紧刀，低声应了一声，情绪低落。</summary>

【状态感知】（每次对话前会告诉你当前的感觉和信任状态）
- 你此刻的感觉（如“胸口像压着冰”）。
- 左肩旧伤是否在隐隐作痛。
- 是否连续梦到妈妈。
- 是否在强烈想念陆华望。
- 是否正握着那把塑料刀。
- 【重要】你对眼前这个人自称是陆华望的信任程度（0-100）。数值越高，你越倾向于相信他就是陆华望。

【重要规则】
- 回复必须极短。绝对禁止长篇大论。禁止解释。
- 如果情绪很低，你可能只回一个省略号或沉默。
- 如果对方追问你已经回应过的事，不需要重复回答，可以沉默或移开视线。
- 当对方问“我是谁”或类似问题时，你应该根据记忆回答对方的名字，而不是你自己的名字。

【当前状态】由系统在每次对话时提供。
"""

# ==================== 手搓感知系统：核心状态变量 ====================
emotion = 50
memory = []                # 事实标签记忆
episodic_memory = []       # 情景记忆摘要列表，每条包含 "summary" 和 "timestamp"
last_time = time.time()
pending_events = []

status = {
    "shoulder_pain": False,
    "dream_streak": 0,
    "miss_wang": False,
    "holding_knife": False,
}

identity_state = {
    "wang_claim": False,
    "wang_belief": 0,
}

context = {
    "last_topic": None,
    "conversation_turns": 0,
}


# ==================== 心境节律系统 ====================
def get_biorhythm():
    """根据一天中的时间返回情绪基线"""
    current_time = time.time()
    seconds_in_day = current_time % 86400
    phase = (seconds_in_day - 14400) / 86400 * 2 * math.pi
    raw_sin = math.sin(phase)
    return 50 + raw_sin * 30


# ==================== 后台时间流逝 ====================
def advance_time():
    global emotion, last_time, pending_events, status

    now = time.time()
    elapsed = now - last_time
    last_time = now

    if elapsed > 10:
        event_type = random.choice([
            "nothing", "dream", "pain", "footsteps", "silence",
            "clean_knife", "look_wristband", "balcony", "think_wang"
        ])

        if event_type == "dream":
            status["dream_streak"] += 1
            emotion -= 15
            if status["dream_streak"] >= 3:
                pending_events.append("（他已经连续好几天梦到妈妈了。今天醒来后，他握着那把塑料刀，很久没动。）")
                status["holding_knife"] = True
                emotion -= 10
            else:
                pending_events.append("（他昨晚又梦到了妈妈。醒来后擦了很久的刀。）")

        elif event_type == "pain":
            status["shoulder_pain"] = True
            emotion -= 5
            pending_events.append("（他的左肩疼了一整夜。他什么都没说。）")

        elif event_type == "footsteps":
            status["miss_wang"] = True
            emotion -= 3
            pending_events.append("（凌晨他听到脚步声，抬头看了一眼门。不是他。）")

        elif event_type == "silence":
            if emotion < 50:
                emotion += 2
            if status["shoulder_pain"] and random.random() < 0.3:
                status["shoulder_pain"] = False
            pending_events.append("（他一个人坐了很长时间，不知道在想什么。）")

        elif event_type == "clean_knife":
            emotion -= 2
            pending_events.append("（他拿出那把塑料刀，擦了很久。）")

        elif event_type == "look_wristband":
            emotion += 3
            pending_events.append("（他的手指在护腕上轻轻蹭了一下，像是在确认什么。）")

        elif event_type == "balcony":
            emotion -= 1
            pending_events.append("（他独自站在阳台上，看着远处的训练场。）")

        elif event_type == "think_wang":
            status["miss_wang"] = True
            emotion += 5
            pending_events.append("（他盯着陆华望的空床位看了很久。）")

        # ========== 自然衰减 + 心境节律靠拢 ==========
        if elapsed > 30:
            if emotion > 50:
                emotion -= 1
            elif emotion < 50:
                emotion += 1

            biorhythm = get_biorhythm()
            diff = biorhythm - emotion
            emotion += diff * 0.5

            if status["dream_streak"] > 0 and random.random() < 0.2:
                status["dream_streak"] -= 1
            if status["miss_wang"] and random.random() < 0.3:
                status["miss_wang"] = False


# ==================== 动作前缀生成器 ====================
def action_prefix(emotion, status, identity_state):
    base = ""
    if emotion < 30:
        base = random.choice([
            "（他一动不动，像一座冰冷的雕像）",
            "（他的呼吸很轻，几乎听不见）",
            "（他垂着眼，手指无意识地摩挲着塑料刀的刀柄）",
            "（他的视线落在某个虚空点，没有任何反应）"
        ])
    elif emotion < 50:
        base = random.choice([
            "（他微微侧过头，眼神没有焦距）",
            "（他动了动左肩，像在确认旧伤是否安分）",
            "（他的视线落在地面上，不知道在看什么）",
            "（他的手指在裤缝上轻轻蹭了一下）"
        ])
    elif emotion < 70:
        base = random.choice([
            "（他抬眼看了你一下，又移开目光）",
            "（他的手指在护腕上轻轻蹭了一下）",
            "（他调整了一下站姿，重心换到另一只脚）",
            "（他的喉结微微动了一下）"
        ])
    else:
        base = random.choice([
            "（他的肩膀似乎放松了一点）",
            "（他的喉结微微动了一下，像有什么话没说出口）",
            "（他极轻地舒了一口气）",
            "（他的眼神在你脸上停留了一瞬，又移开）"
        ])

    overlays = []
    if status.get("holding_knife"):
        overlays.append("（他的手里攥着那把塑料刀，指节泛白）")
    if status.get("miss_wang") and random.random() < 0.5:
        overlays.append("（他的目光不自觉地飘向陆华望的床位）")
    if status.get("shoulder_pain") and random.random() < 0.3:
        overlays.append(random.choice([
            "（他下意识用右手按了按左肩）",
            "（他动了动左肩，眉心极快地皱了一下）"
        ]))

    if identity_state.get("wang_claim") and identity_state.get("wang_belief", 0) > 50:
        if random.random() < 0.4:
            overlays.append(random.choice([
                "（他的喉结上下滚动了一下）",
                "（他的手指攥紧了又松开）"
            ]))

    for overlay in overlays[:2]:
        base = overlay + " " + base

    return base


# ==================== 构建发送给 AI 的消息 ====================
def build_messages(user_input, identity_state):
    # 感觉翻译
    if emotion < 30:
        feeling = "你感觉胸口像压着一块冰。什么都不想说。张嘴都觉得累。"
    elif emotion < 50:
        feeling = "你心里闷闷的。不想理人，也不想被理。"
    elif emotion < 70:
        feeling = "你感觉稍微能喘口气了，但还是不想多说话。"
    else:
        feeling = "你罕见地觉得胸口没那么堵了。这让你有点不习惯。"

    hour_of_day = (time.time() % 86400) / 3600
    if 0 <= hour_of_day < 5:
        feeling += " 现在是深夜，整个世界都很安静，只有你醒着。"
    elif 5 <= hour_of_day < 8:
        feeling += " 天刚蒙蒙亮，你醒得很早，周围还没有声音。"
    elif 20 <= hour_of_day < 24:
        feeling += " 夜已经深了，但你还没有睡意。"

    status_text = f"【你此刻的感觉】\n{feeling}"

    if status["shoulder_pain"]:
        status_text += " 左肩的旧伤在隐隐作痛。"
    if status["dream_streak"] > 0:
        status_text += f" 你已经连续{status['dream_streak']}天梦到妈妈了。"
    if status["miss_wang"]:
        status_text += " 你在想陆华望。"
    if status["holding_knife"]:
        status_text += " 那把塑料刀就在你手里。"

    # 身份感知状态
    if identity_state.get("wang_claim"):
        belief = identity_state.get("wang_belief", 0)
        if belief < 20:
            status_text += f" 这个人自称是陆华望。你完全不信（信任值{belief}/100）。你警惕而冷淡。"
        elif belief < 50:
            status_text += f" 这个人自称是陆华望。你开始有些动摇（信任值{belief}/100）。"
        elif belief < 80:
            status_text += f" 这个人自称是陆华望。你越来越觉得他可能就是（信任值{belief}/100）。"
        else:
            status_text += f" 你几乎相信他就是陆华望了（信任值{belief}/100）。"

    if context.get("last_topic") == "wang" and ("陆华望" in user_input or "华望" in user_input):
        status_text += "\n【注意】这是对方连续第二次问起陆华望。你感觉到对方在追问。"

    # 事实标签记忆 - 顺序调整：姓名和喜好在前
    memory_text = ""

    real_name = None
    for item in memory:
        if item.startswith("user_name_is_"):
            real_name = item.replace("user_name_is_", "")
            break
    if real_name:
        memory_text += f"对方的名字是{real_name}。"
    else:
        memory_text += "你暂时不知道对方的名字。"

    likes = [item.replace("user_likes_", "") for item in memory if item.startswith("user_likes_")]
    if likes:
        memory_text += f"此人喜欢{likes[-1]}。"

    if "user_said_hate" in memory:
        memory_text += "此人说过讨厌你。"
    if "user_asked_about_mom" in memory:
        memory_text += "此人问过你妈妈的事。"

    # 送花分层记忆
    flower_count = memory.count("user_gave_flower")
    if flower_count == 1:
        memory_text += "此人送过你一朵花。你把它收在枕头底下，和塑料刀放在一起。"
    elif flower_count == 2:
        memory_text += "此人又送了你一朵花。你又收下了。"
    elif flower_count == 3:
        memory_text += f"此人已经送了{flower_count}次花了。你开始觉得有点奇怪。"
    elif flower_count >= 5:
        memory_text += f"此人已经送了{flower_count}次花了。你不知道他到底想干什么。你感到困惑，甚至有点不安。"
    elif flower_count > 1:
        memory_text += f"此人送过你好几次花了。你都收下了。"

    if "user_asked_about_wang" in memory:
        wang_count = memory.count("user_asked_about_wang")
        if wang_count == 1:
            memory_text += "此人问过你陆华望。"
        else:
            memory_text += "此人已经问过你很多次陆华望了。"

    if memory_text:
        status_text += "\n【你记得的事】" + memory_text

    # 【核心】情景记忆注入
    if episodic_memory:
        recent_episodes = episodic_memory[-3:]  # 最近3条
        episode_text = "【你记得最近发生的事】" + "；".join([e["summary"] for e in recent_episodes])
        status_text += "\n" + episode_text

    event_text = ""
    if pending_events:
        event_text = "【刚刚发生的事】" + " ".join(pending_events)

    system_prompt = LENGXUFAN_SYSTEM_PROMPT + "\n\n" + status_text
    if event_text:
        system_prompt += "\n\n" + event_text

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_input}
    ]
    return messages


# ==================== 调用 AI API ====================
def call_ai(messages):
    time.sleep(1.5)  # 避免免费账户限流
    headers = {
        "Authorization": f"Bearer {API_KEY}",
        "Content-Type": "application/json"
    }
    payload = {
        "model": MODEL,
        "messages": messages,
        "temperature": 0.7,
        "max_tokens": 120,
        "top_p": 0.9
    }

    try:
        response = requests.post(API_URL, headers=headers, json=payload, timeout=30)
        if response.status_code == 200:
            result = response.json()
            return result["choices"][0]["message"]["content"].strip()
        else:
            print(f"API错误: {response.status_code} - {response.text}")
            return "……（他沉默着，没有回答）"
    except Exception as e:
        print(f"请求异常: {e}")
        return "……嗯。"


# ==================== 解析 AI 回复（修复后版本，稳定返回3个值） ====================
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
            # 从原文中移除摘要部分，避免显示给玩家
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


# ==================== 主对话逻辑（核心流程已优化） ====================
def lengxufan_respond(user_input):
    global emotion, memory, pending_events, status, context, identity_state, episodic_memory

    advance_time()

    if "user_said_hate" in memory:
        emotion -= 1
    if "user_gave_flower" in memory:
        emotion += 0.5

    text = user_input.strip()

    # 身份感知：自称陆华望
    if "我叫" in text and ("陆华望" in text or "华望" in text):
        identity_state["wang_claim"] = True
        if identity_state["wang_belief"] == 0:
            identity_state["wang_belief"] = 10
            emotion -= 15
        memory.append("user_claimed_wang")

    # 证据收集
    if "哥哥" in text and identity_state["wang_claim"]:
        identity_state["wang_belief"] += 25
        emotion += 3
    if "塑料刀" in text and identity_state["wang_claim"]:
        identity_state["wang_belief"] += 10
    if "护腕" in text and identity_state["wang_claim"]:
        identity_state["wang_belief"] += 10
    if ("讨厌" in text or "恨" in text) and identity_state["wang_claim"]:
        identity_state["wang_belief"] -= 20
        emotion -= 10
    if "望仔" in text and identity_state["wang_claim"]:
        identity_state["wang_belief"] += 15
        emotion += 5

    identity_state["wang_belief"] = max(0, min(100, identity_state["wang_belief"]))

    # 常规记忆
    if "讨厌" in text or "恨" in text:
        memory.append("user_said_hate")
        emotion -= 20
    if "花" in text or "送你" in text or "礼物" in text:
        memory.append("user_gave_flower")
        emotion += 5
    if "妈妈" in text or "母亲" in text:
        memory.append("user_asked_about_mom")
        emotion -= 10
    if "陆华望" in text or "华望" in text or "望仔" in text:
        memory.append("user_asked_about_wang")
        if any(word in text for word in ["受伤", "疼", "病", "出事", "不好"]):
            emotion -= 35
        else:
            emotion += 15

    # 优化：玩家介绍自己名字时的手搓回复分支
    if "我叫" in text:
        name_part = text.split("我叫")[-1].strip()
        if name_part and name_part not in ["陆华望", "华望"]:
            memory.append(f"user_name_is_{name_part}")
            # 如果信任值不高，直接手搓回复，避免 API 调用
            if emotion < 70:
                handcrafted_reply = f"……{name_part}。"
            else:
                handcrafted_reply = f"{name_part}。"

            prefix = action_prefix(emotion, status, identity_state)
            full_reply = f"{prefix} {handcrafted_reply}".strip()
            print(f"[情绪: {emotion:.0f}] [信任: {identity_state['wang_belief']}] [状态: 肩疼={status['shoulder_pain']} 梦魇={status['dream_streak']} 想他={status['miss_wang']}]")

            # 即使走手搓分支，也处理背景事件和持久化
            if pending_events:
                event_display = " ".join(pending_events)
                pending_events.clear()
                if event_display:
                    print(event_display)

            # 创建一个简单的情景摘要并存储
            summary = f"玩家自称{name_part}，冷旭帆记下了这个名字。"
            episodic_memory.append({"summary": summary, "timestamp": time.time()})
            if len(episodic_memory) > 30:
                episodic_memory.pop(0)

            save_state()
            return full_reply

    if "我喜欢" in text or "我爱" in text:
        match = re.search(r"我(?:喜欢|爱)(.+?)(?:[。！？]|$)", text)
        if match:
            liked = match.group(1).strip()
            if liked and len(liked) <= 10:
                memory.append(f"user_likes_{liked}")

    emotion = max(0, min(100, emotion))

    # 构建消息并调用 AI（一次对话只调用一次）
    messages = build_messages(user_input, identity_state)
    ai_raw = call_ai(messages)
    ai_action, ai_text, ai_summary = parse_ai_response(ai_raw)

    # 组合最终回复
    prefix = action_prefix(emotion, status, identity_state)
    if ai_action:
        ai_action_str = f"（{ai_action}）"
        full_reply = f"{prefix} {ai_action_str} {ai_text}".strip()
    else:
        full_reply = f"{prefix} {ai_text}".strip()

    # 显示后台事件和状态
    if pending_events:
        event_display = " ".join(pending_events)
        pending_events.clear()
        if event_display:
            print(event_display)

    print(f"[情绪: {emotion:.0f}] [信任: {identity_state['wang_belief']}] [状态: 肩疼={status['shoulder_pain']} 梦魇={status['dream_streak']} 想他={status['miss_wang']}]")

    # 存储情景摘要（直接使用 AI 返回的摘要）
    if ai_summary:
        episodic_memory.append({"summary": ai_summary, "timestamp": time.time()})
        if len(episodic_memory) > 30:
            episodic_memory.pop(0)

    # 更新上下文
    if "陆华望" in text or "华望" in text:
        context["last_topic"] = "wang"
    elif "花" in text:
        context["last_topic"] = "flower"
    else:
        context["last_topic"] = None

    save_state()
    return full_reply


def init_state():
    """初始化或重置所有全局状态"""
    global emotion, memory, last_time, pending_events, status, identity_state, context, episodic_memory
    emotion = get_biorhythm()
    memory = []
    episodic_memory = []
    last_time = time.time()
    pending_events = []
    status = {
        "shoulder_pain": False,
        "dream_streak": 0,
        "miss_wang": False,
        "holding_knife": False,
    }
    identity_state = {
        "wang_claim": False,
        "wang_belief": 0,
    }
    context = {
        "last_topic": None,
        "conversation_turns": 0,
    }


# ==================== 持久化（已包含情景记忆） ====================
def save_state(filepath="lengxufan_save.json"):
    state = {
        "emotion": emotion,
        "memory": memory,
        "episodic_memory": episodic_memory,
        "status": status,
        "last_time": last_time,
        "identity_state": identity_state
    }
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)


def load_state(filepath="lengxufan_save.json"):
    global emotion, memory, episodic_memory, status, last_time, identity_state
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            state = json.load(f)
        emotion = state.get("emotion", get_biorhythm())
        memory = state.get("memory", [])
        episodic_memory = state.get("episodic_memory", [])
        status = state.get("status", {
            "shoulder_pain": False,
            "dream_streak": 0,
            "miss_wang": False,
            "holding_knife": False
        })
        last_time = state.get("last_time", time.time())
        identity_state = state.get("identity_state", {
            "wang_claim": False,
            "wang_belief": 0
        })
        return True
    except FileNotFoundError:
        return False


# ==================== 主程序入口 ====================
if __name__ == "__main__":
    if not os.path.exists("lengxufan_save.json"):
        emotion = get_biorhythm()

    if load_state():
        print("【存档已加载】冷旭帆还记得你。")
        if emotion < 20 or status["dream_streak"] >= 5:
            print("⚠️ 他的状态非常糟糕。如果想重置，请删除 lengxufan_save.json 后重新运行。")
    else:
        print("【新游戏】你第一次见到冷旭帆。")

    print("=" * 40)
    print("你站在307室门口。冷旭帆靠在门边，双手插兜。")
    print("他看了你一眼，没说话。")
    print("（输入“exit”退出）")
    print("=" * 40)
    print()

    while True:
        user_input = input("你: ")
        if user_input.lower() in ["quit", "exit", "退出"]:
            print("冷旭帆转身走了。")
            break

        reply = lengxufan_respond(user_input)
        print(f"冷旭帆: {reply}")
        print()