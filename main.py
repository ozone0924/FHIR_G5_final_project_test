"""
G5 傳染病公衛監測系統 — CLI 入口
=====================================
使用方式（建議以 uv 執行）：

  uv run python main.py              # 互動選單
  uv run python main.py seed         # 手動注入假資料（需要時才執行）
  uv run python main.py dashboard    # 啟動儀表板
  uv run python main.py engine       # 啟動 MedMorph 引擎
  uv run python main.py all          # 一鍵啟動 engine + dashboard（不含 seed）
"""

import sys
import subprocess


COMMANDS = {
    "seed":      ("手動注入假資料（需要時才執行）",         ["python", "seed_data.py"]),
    "dashboard": ("啟動 Streamlit 儀表板",                  ["python", "-m", "streamlit", "run", "dashboard.py"]),
    "engine":    ("啟動 MedMorph 引擎（持續輪詢）",         ["python", "medmorph_engine.py"]),
    "all":       ("一鍵啟動 engine + dashboard（不含 seed）", ["python", "run_all.py"]),
    "eicr":      ("產生範例 eICR JSON",                      ["python", "eicr_generator.py"]),
}


def print_menu():
    print("\n🏥 傳染病公衛監測系統 — 第五組")
    print("=" * 40)
    for key, (desc, _) in COMMANDS.items():
        print(f"  {key:<12} {desc}")
    print("  quit         離開")
    print("=" * 40)


def run_cmd(argv: list[str]) -> None:
    """用和目前 Python 相同的直譯器執行子命令"""
    cmd = [sys.executable] + argv[1:]
    subprocess.run(cmd, check=False)


def main():
    if len(sys.argv) > 1:
        key = sys.argv[1].lower()
        if key in COMMANDS:
            _, cmd = COMMANDS[key]
            run_cmd(cmd)
        else:
            print(f"未知指令：{key}")
            print(f"可用指令：{', '.join(COMMANDS)}")
        return

    # 互動選單
    while True:
        print_menu()
        choice = input("請輸入指令（或 quit）：").strip().lower()
        if choice in ("quit", "q", "exit"):
            print("掰掰！")
            break
        if choice in COMMANDS:
            _, cmd = COMMANDS[choice]
            print()
            run_cmd(cmd)
        else:
            print(f"❌ 未知指令：{choice}")


if __name__ == "__main__":
    main()
