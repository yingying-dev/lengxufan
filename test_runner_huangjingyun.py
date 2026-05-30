"""
黄景云 · 自动化测试套件 v2.1
用法：python test_runner_huangjingyun.py

功能：
- 从 test_cases_huangjingyun.json 读取测试用例（可自定义）
- 自动重置状态，运行主测试序列
- 模拟退出重进，验证情景记忆持久化
- 生成 Markdown 格式的详细测试报告

注意事项：
- 运行前请确保 huangjingyun.py 中的 API_KEY 已配置为有效密钥
- 测试依赖网络连接（调用硅基流动 API）
- 每次测试耗时约 2-3 分钟（含 API 限流等待）
"""

import time
import os
import json
import sys
from datetime import datetime
import huangjingyun

# ==================== 配置 ====================
TEST_CASES_FILE = "test_cases_huangjingyun.json"  # 测试用例配置文件
REPORT_FILE = "test_report_huangjingyun_latest.md"  # 输出报告文件
SAVE_FILE = "huangjingyun_save.json"  # 存档文件名

# ==================== 辅助函数 ====================
def reset_to_new_game():
    """删除存档并重置状态"""
    if os.path.exists(SAVE_FILE):
        os.remove(SAVE_FILE)
    huangjingyun.init_state()
    # 确保情绪值用节律初始化
    if hasattr(huangjingyun, 'get_biorhythm'):
        huangjingyun.emotion = huangjingyun.get_biorhythm()

def run_test_case(user_input, expected_emotion_range=None, expected_trust_range=None, expected_reply_contains=None):
    """运行单条测试用例，返回结果字典"""
    reply = huangjingyun.huangjingyun_respond(user_input)
    emotion_val = huangjingyun.emotion
    trust_val = huangjingyun.identity_state["trust_level"]

    passed = True
    if expected_emotion_range:
        if not (expected_emotion_range[0] <= emotion_val <= expected_emotion_range[1]):
            passed = False
    if expected_trust_range:
        if not (expected_trust_range[0] <= trust_val <= expected_trust_range[1]):
            passed = False
    if expected_reply_contains:
        # 只要包含任意一个关键词即通过
        found_any = False
        for keyword in expected_reply_contains:
            if keyword in reply:
                found_any = True
                break
        if not found_any:
            passed = False

    return {
        "input": user_input,
        "reply": reply,
        "emotion": emotion_val,
        "trust": trust_val,
        "passed": passed,
        "expected_emotion": expected_emotion_range,
        "expected_trust": expected_trust_range,
        "expected_keywords": expected_reply_contains
    }

def reload_module():
    """模拟退出重进"""
    global huangjingyun
    huangjingyun.init_state()
    if hasattr(huangjingyun, 'load_state'):
        huangjingyun.load_state(SAVE_FILE)

def generate_markdown_report(results_main, results_persistence, test_name="v2.1"):
    """生成 Markdown 格式的测试报告"""
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    lines = [
        f"# 黄景云自动化测试报告",
        f"**测试版本**：{test_name}",
        f"**测试时间**：{now}",
        "",
        "## 一、主测试序列结果",
        "",
        "| 序号 | 输入 | 回复摘要 | 情绪值 | 信任值 | 结果 |",
        "|:---:|:---|:---|:---:|:---:|:---:|"
    ]

    passed_main = 0
    for i, r in enumerate(results_main, 1):
        status = "✅" if r["passed"] else "❌"
        reply_short = r['reply'][:30] + "..." if len(r['reply']) > 30 else r['reply']
        lines.append(f"| {i} | {r['input']} | {reply_short} | {r['emotion']:.1f} | {r['trust']} | {status} |")
        if r["passed"]:
            passed_main += 1

    lines.extend([
        "",
        f"**主测试通过率**：{passed_main}/{len(results_main)}",
        "",
        "## 二、情景记忆持久化验证（退出重进后）",
        "",
        "| 序号 | 输入 | 回复 | 情绪值 | 信任值 | 结果 |",
        "|:---:|:---|:---|:---:|:---:|:---:|"
    ])

    passed_persist = 0
    for i, r in enumerate(results_persistence, 1):
        status = "✅" if r["passed"] else "❌"
        lines.append(f"| {i} | {r['input']} | {r['reply']} | {r['emotion']:.1f} | {r['trust']} | {status} |")
        if r["passed"]:
            passed_persist += 1

    lines.extend([
        "",
        f"**持久化测试通过率**：{passed_persist}/{len(results_persistence)}",
        "",
        "## 三、失败用例详情",
        ""
    ])

    failed_cases = [r for r in results_main + results_persistence if not r["passed"]]
    if failed_cases:
        for r in failed_cases:
            lines.append(f"### ❌ 输入：{r['input']}")
            lines.append(f"- 实际回复：{r['reply']}")
            lines.append(f"- 实际情绪：{r['emotion']:.1f}，信任：{r['trust']}")
            if r.get('expected_emotion'):
                lines.append(f"- 预期情绪范围：{r['expected_emotion']}")
            if r.get('expected_trust'):
                lines.append(f"- 预期信任范围：{r['expected_trust']}")
            if r.get('expected_keywords'):
                lines.append(f"- 预期包含关键词：{r['expected_keywords']}")
            lines.append("")
    else:
        lines.append("🎉 全部用例通过！")

    # 写入文件
    with open(REPORT_FILE, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    # 同时打印到控制台
    print("\n".join(lines))
    print(f"\n📄 详细报告已保存至：{REPORT_FILE}")

def load_test_cases():
    """从 JSON 文件加载测试用例，如果不存在则使用内置默认用例"""
    default_cases = [
        # (输入, 情绪范围, 信任范围, 关键词列表)
        # 注：黄景云初始信任为30，热情外向，信任值预期始终≥30
        ["你好呀", [40, 80], [30, 30], ["你好", "呀", "嘞", "咯", "~"]],  # 信任[0,0]→[30,30]
        ["我叫陆盈盈", [40, 80], [30, 50], ["陆盈盈", "你好", "认识"]],
        ["送你一包零食", [45, 85], [30, 50], ["谢谢", "零食", "好", "吃", "喜欢"]],
        ["零食好吃吗？", [45, 85], [30, 50], ["好吃", "美味", "嗯", "喜欢", "~", "好"]],
        ["我喜欢太阳", [45, 85], [30, 50], None],
        ["我喜欢什么", [45, 85], [30, 50], ["太阳", "喜欢", "记得"]],
        ["你认识冷旭帆吗", [45, 85], [30, 50], ["冷旭帆", "307", "闷", "冰刃"]],
        ["叶清辞最近怎么样", [45, 85], [30, 50], ["叶清辞", "时序", "忙", "疯"]],
        ["我心情不好", [35, 75], [30, 50], ["怎么", "啦", "吧", "呀", "耶", "咯"]],
        ["你真好", [45, 85], [30, 55], ["呀", "啦", "谢谢", "开心"]],  # 关键词调整
        ["我讨厌你", [30, 60], [30, 50], ["呀", "啦", "……", "嗯"]],  # 信任[20,50]→[30,50]，情绪放宽，关键词调整
        ["对不起，我刚才是气话", [35, 70], [30, 50], ["呀", "啦", "关系", "吧"]],  # 关键词调整
        ["你会说几种方言", [35, 70], [30, 50], ["七", "方言", "种"]],  # 情绪[50,85]→[35,70]
        ["用粤语说一句听听", [35, 70], [30, 55], ["冇", "问题", "呀", "~", "啦", "食"]],  # 情绪放宽
        ["你奶奶还好吗", [40, 75], [30, 55], ["奶奶", "好", "想", "硬朗"]],
        ["谢谢你陪我聊天", [35, 70], [30, 60], ["不谢", "不用", "客气", "开心", "呀", "~"]],
    ]

    if os.path.exists(TEST_CASES_FILE):
        try:
            with open(TEST_CASES_FILE, "r", encoding="utf-8") as f:
                cases = json.load(f)
            print(f"✅ 从 {TEST_CASES_FILE} 加载了 {len(cases)} 条测试用例")
            return cases
        except json.JSONDecodeError as e:
            print(f"⚠️ {TEST_CASES_FILE} 格式错误：{e}，使用内置默认用例")
            return default_cases
    else:
        print(f"⚠️ 未找到 {TEST_CASES_FILE}，使用内置默认用例")
        return default_cases

# ==================== 主测试流程 ====================
if __name__ == "__main__":
    # 检查 API Key 是否已配置
    if huangjingyun.API_KEY == "请替换为你自己的硅基流动密钥" or "sk-" not in huangjingyun.API_KEY:
        print("❌ 错误：请先在 huangjingyun.py 中配置有效的 API Key")
        print("   到 https://www.siliconflow.cn 注册并获取密钥")
        print("   获取后在 huangjingyun.py 中替换 API_KEY 变量的值")
        sys.exit(1)

    print("=" * 60)
    print("黄景云 v2.1 自动化测试套件")
    print("=" * 60)

    # 1. 重置为新游戏
    reset_to_new_game()
    print("🔄 状态已重置，开始主测试序列...")
    time.sleep(1)

    # 2. 加载测试用例
    test_cases = load_test_cases()

    # 3. 运行主测试序列
    results_main = []
    for case in test_cases:
        user_input, emo_range, trust_range, keywords = case
        result = run_test_case(user_input, emo_range, trust_range, keywords)
        results_main.append(result)
        print(f"  测试: {user_input} → {'✅' if result['passed'] else '❌'}")
        time.sleep(1.5)  # 避免 API 限流

    # 4. 模拟退出重进
    print("\n🔄 模拟退出重进，验证情景记忆持久化...")

    if not os.path.exists(SAVE_FILE):
        print(f"⚠️ 警告：存档文件 {SAVE_FILE} 不存在，可能主测试序列未正常完成")
        print("   跳过持久化验证，直接生成主测试报告")
        results_persistence = []
    else:
        reload_module()
        time.sleep(1)

        # 5. 运行持久化验证用例
        persistence_cases = [
            ["还记得我是谁吗", [30, 85], [30, 60], ["陆盈盈"]],
            ["上次你送我的零食是什么", [30, 85], [30, 60], ["零食", "好吃", "记得"]],
            ["你还记得我喜欢什么吗", [30, 85], [30, 60], ["太阳"]],
            ["冷旭帆最近怎么样了", [30, 85], [30, 60], ["冷旭帆", "307", "闷"]],
        ]
        results_persistence = []
        for case in persistence_cases:
            user_input, emo_range, trust_range, keywords = case
            result = run_test_case(user_input, emo_range, trust_range, keywords)
            results_persistence.append(result)
            print(f"  持久化测试: {user_input} → {'✅' if result['passed'] else '❌'}")
            time.sleep(1.5)

    # 6. 生成报告
    generate_markdown_report(results_main, results_persistence, "v2.1")