"""
run_all.py — 一鍵啟動腳本
===========================
步驟：
  1. 確認套件已安裝（uv sync 或 pip install）
  2. 背景啟動 MedMorph 引擎
  3. 前景啟動 Streamlit 儀表板

注意：seed_data 預設不執行，需手動執行：
  uv run python seed_data.py

使用方式：
  uv run python run_all.py              # 建議（自動用 .venv）
  python run_all.py
  python run_all.py --seed              # 明確要求注入假資料
  python run_all.py --skip-engine       # 只跑儀表板
  python run_all.py --port 8502         # 指定 port
"""

import argparse
import os
import shutil
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))


def _python() -> list[str]:
    """回傳優先使用 uv run python 的執行指令前綴"""
    if shutil.which("uv") and os.path.exists(os.path.join(HERE, "pyproject.toml")):
        return ["uv", "run", "python"]
    return [sys.executable]


def run_cmd(cmd: list, **kwargs) -> subprocess.Popen:
    print(f"  $ {' '.join(cmd)}")
    return subprocess.Popen(cmd, cwd=HERE, **kwargs)


def ensure_deps():
    """確認套件可 import；若不行則自動 uv sync 或 pip install"""
    try:
        import streamlit  # noqa: F401
        import plotly     # noqa: F401
        import pandas     # noqa: F401
    except ImportError:
        if shutil.which("uv"):
            print("\n📦 執行 uv sync 安裝套件…")
            subprocess.run(["uv", "sync"], check=True, cwd=HERE)
        else:
            print("\n📦 執行 pip install…")
            req = os.path.join(HERE, "requirements.txt")
            subprocess.run(
                [sys.executable, "-m", "pip", "install", "-r", req, "-q"],
                check=True, cwd=HERE,
            )
        print("   ✅ 套件安裝完成")


def seed_data(count: int = 150, days: int = 30):
    print(f"\n🌱 注入假資料（{count} 筆 / {days} 天）…")
    subprocess.run(
        _python() + ["seed_data.py", "--count", str(count), "--days", str(days)],
        check=True, cwd=HERE,
    )


def main():
    parser = argparse.ArgumentParser(description="傳染病公衛監測系統 — 一鍵啟動")
    parser.add_argument("--seed",        action="store_true", help="注入假資料（預設不執行）")
    parser.add_argument("--skip-engine", action="store_true", help="跳過 MedMorph 引擎")
    parser.add_argument("--port",        type=int, default=8501, help="Streamlit port（預設 8501）")
    parser.add_argument("--count",       type=int, default=150,  help="假資料筆數（預設 150，需搭配 --seed）")
    parser.add_argument("--days",        type=int, default=30,   help="資料涵蓋天數（預設 30，需搭配 --seed）")
    args = parser.parse_args()

    print("=" * 50)
    print("  🏥 傳染病公衛監測系統 — 第五組")
    print("=" * 50)

    ensure_deps()

    if args.seed:
        seed_data(count=args.count, days=args.days)
    else:
        print("\n⏭  略過假資料注入（加 --seed 旗標可手動觸發）")

    processes = []

    if not args.skip_engine:
        print("\n🚀 啟動 MedMorph 引擎（背景）…")
        p_engine = run_cmd(
            _python() + ["medmorph_engine.py"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.STDOUT,
        )
        processes.append(p_engine)
        time.sleep(2)
        print(f"   ✅ 引擎已在背景執行（PID {p_engine.pid}）")

    print(f"\n🌐 啟動 Streamlit 儀表板 → http://localhost:{args.port}")
    print("   按 Ctrl+C 停止所有服務\n")
    p_dash = run_cmd(
        _python() + ["-m", "streamlit", "run", "dashboard.py",
                     "--server.port", str(args.port),
                     "--server.headless", "false"],
    )
    processes.append(p_dash)

    try:
        p_dash.wait()
    except KeyboardInterrupt:
        print("\n🛑 正在停止所有服務…")
    finally:
        for p in processes:
            try:
                p.terminate()
            except Exception:
                pass
        print("   已停止。")


if __name__ == "__main__":
    main()
