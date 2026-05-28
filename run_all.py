"""
run_all.py — 一鍵啟動腳本
===========================
步驟：
  1. 安裝套件（若尚未安裝）
  2. 注入假資料（seed_data）
  3. 背景啟動 MedMorph 引擎
  4. 前景啟動 Streamlit 儀表板

使用方式：
  python run_all.py
  python run_all.py --skip-seed      # 不重新注入假資料
  python run_all.py --skip-engine    # 只跑儀表板，不啟動引擎
"""

import argparse
import os
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))


def run_cmd(cmd: list, **kwargs) -> subprocess.Popen:
    print(f"  $ {' '.join(cmd)}")
    return subprocess.Popen(cmd, cwd=HERE, **kwargs)


def install_deps():
    print("\n📦 安裝 Python 套件…")
    req = os.path.join(HERE, "requirements.txt")
    subprocess.run(
        [sys.executable, "-m", "pip", "install", "-r", req, "-q"],
        check=True, cwd=HERE,
    )
    print("   ✅ 套件安裝完成")


def seed_data():
    print("\n🌱 注入假資料…")
    subprocess.run(
        [sys.executable, "seed_data.py", "--count", "150", "--days", "30"],
        check=True, cwd=HERE,
    )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--skip-seed",   action="store_true", help="跳過假資料注入")
    parser.add_argument("--skip-engine", action="store_true", help="跳過 MedMorph 引擎")
    parser.add_argument("--port", type=int, default=8501, help="Streamlit port（預設 8501）")
    args = parser.parse_args()

    print("=" * 50)
    print("  🏥 傳染病公衛監測系統 — 第五組")
    print("=" * 50)

    install_deps()

    if not args.skip_seed:
        seed_data()

    processes = []

    if not args.skip_engine:
        print("\n🚀 啟動 MedMorph 引擎（背景）…")
        p_engine = run_cmd(
            [sys.executable, "medmorph_engine.py"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.STDOUT,
        )
        processes.append(p_engine)
        time.sleep(2)
        print("   ✅ 引擎已在背景執行（PID %d）" % p_engine.pid)

    print(f"\n🌐 啟動 Streamlit 儀表板 → http://localhost:{args.port}")
    print("   按 Ctrl+C 停止所有服務\n")
    p_dash = run_cmd(
        [sys.executable, "-m", "streamlit", "run", "dashboard.py",
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
