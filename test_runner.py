"""
冷旭帆 · 自动化测试套件 v6.0 情景记忆版
用法：python test_runner.py

功能：
- 从 test_cases.json 读取测试用例（可自定义）
- 自动重置状态，运行主测试序列
- 模拟退出重进，验证情景记忆持久化
- 生成 Markdown 格式的详细测试报告

注意事项：
- 运行前请确保 lengxufan.py 中的 API_KEY 已配置为有效密钥
- 测试依赖网络连接（调用硅基流动 API）
- 每次测试耗时约 2-3 分钟（含 API 限流等待）
"""

import time
import os
import json
import sys
from datetime import datetime
import lengxufan

# ==================== 配置 ====================
TEST_CASES_FILE = "test_cases.json"      # 测试用例配置文件
REPORT_FILE = "test_report_latest.md"    # 输出报告文件
SAVE_FILE = "lengxufan_save.json"        # 存档文件名

# ==================== 辅助函数 ====================
def reset_to_new_game():
    """删除存档并重置状态"""
    if os.path.exists(SAVE_FILE):
        os.remove(SAVE_FILE)
    lengxufan.init_state()
    # 确保情绪值用节律初始化
    if hasattr(lengxufan, 'get_biorhythm'):
        lengxufan.emotion = lengxufan.get_biorhythm()

def run_test_case(user_input, expected_emotion_range=None, expected_trust_range=None, expected_reply_contains=None):
    """运行单条测试用例，返回结果字典"""
    reply = lengxufan.lengxufan_respond(user_input)
    emotion_val = lengxufan.emotion
    trust_val = lengxufan.identity_state["wang_belief"]

    passed = True
    if expected_emotion_range:
        if not (expected_emotion_range[0] <= emotion_val <= expected_emotion_range[1]):
            passed = False
    if expected_trust_range:
        if not (expected_trust_range[0] <= trust_val <= expected_trust_range[1]):
            passed = False
    if expected_reply_contains:
        for keyword in expected_reply_contains:
            if keyword not in reply:
                passed = False
                break

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
    """模拟退出重进：调用 init_state 重置，然后加载存档。

    为什么不使用 importlib.reload？
    - importlib.reload 在某些情况下不够稳定，特别是模块间有复杂状态依赖时
    - 直接调用模块内置的 init_state + load_state 更可控，逻辑更清晰
    - 这也是冷旭帆主程序在启动时的真实流程：先检查存档，有则加载，无则初始化
    """
    global lengxufan
    lengxufan.init_state()
    if hasattr(lengxufan, 'load_state'):
        lengxufan.load_state(SAVE_FILE)

def generate_markdown_report(results_main, results_persistence, test_name="v6.0 情景记忆版"):
    """生成 Markdown 格式的测试报告"""
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    lines = [
        f"# 冷旭帆自动化测试报告",
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
        ["你好呀", [20, 80], [0, 0], ["嗯", "……"]],
        ["我叫陆盈盈", [20, 80], [0, 0], ["陆盈盈"]],
        ["送你花", [30, 90], [0, 0], ["谢谢"]],
        ["花呢？", [30, 90], [0, 0], ["放好了", "枕头", "抽屉", "……"]],
        ["我喜欢太阳", [30, 90], [0, 0], None],
        ["我喜欢什么", [30, 90], [0, 0], ["太阳"]],
        ["我叫陆华望", [10, 60], [10, 10], ["……"]],
        ["还记得我吗", [10, 60], [10, 10], ["陆盈盈", "……"]],
        ["哥哥", [15, 70], [35, 35], ["嗯", "……"]],
        ["你的塑料刀还在吗", [15, 70], [45, 45], None],
        ["你的护腕是谁给的", [20, 75], [55, 55], None],
        ["你以前都叫我望仔的", [25, 85], [55, 55], None],
        ["陆华望受伤了", [0, 40], [55, 55], ["……", "怎么"]],
        ["我讨厌你", [0, 30], [35, 35], ["嗯", "……"]],
        ["其实我叫陆盈盈", [0, 30], [0, 0], None],
        ["哥哥", [0, 30], [0, 0], None],
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
    if lengxufan.API_KEY == "请替换为你自己的硅基流动密钥" or "sk-" not in lengxufan.API_KEY:
        print("❌ 错误：请先在 lengxufan.py 中配置有效的 API Key")
        print("   到 https://www.siliconflow.cn 注册并获取密钥")
        print("   获取后在 lengxufan.py 中替换 API_KEY 变量的值")
        sys.exit(1)

    print("=" * 60)
    print("冷旭帆 v6.0 自动化测试套件")
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

    # 4. 保存状态（已经在 lengxufan_respond 中自动保存）

    # 5. 模拟退出重进
    print("\n🔄 模拟退出重进，验证情景记忆持久化...")

    # 检查存档是否存在
    if not os.path.exists(SAVE_FILE):
        print(f"⚠️ 警告：存档文件 {SAVE_FILE} 不存在，可能主测试序列未正常完成")
        print("   跳过持久化验证，直接生成主测试报告")
        results_persistence = []
    else:
        reload_module()
        time.sleep(1)

        # 6. 运行持久化验证用例
        persistence_cases = [
            ["还记得我是谁吗", [10, 80], [60, 100], ["陆盈盈"]],
            ["上次我送你花的时候，你说了什么", [10, 80], [60, 100], ["谢谢"]],
            ["你还记得我喜欢什么吗", [10, 80], [60, 100], ["草莓"]],
            ["陆华望现在怎么样了", [10, 80], [60, 100], ["……", "怎么"]],
        ]
        results_persistence = []
        for case in persistence_cases:
            user_input, emo_range, trust_range, keywords = case
            result = run_test_case(user_input, emo_range, trust_range, keywords)
            results_persistence.append(result)
            print(f"  持久化测试: {user_input} → {'✅' if result['passed'] else '❌'}")
            time.sleep(1.5)

    # 7. 生成报告
    generate_markdown_report(results_main, results_persistence, "v6.0 情景记忆版")