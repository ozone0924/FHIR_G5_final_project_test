"""
seed_data.py — 真實疾病擴散模式 Demo 資料注入腳本
======================================================
模擬六個月內多波傳染病爆發，呈現符合真實流行病學的：
  - 時間擴散：epidemic curve（高斯分布，rise→peak→decline）
  - 地理擴散：epicenter 向外延遲傳播（縣市延遲模型）
  - 疾病差異：
    * COVID-19 / 流感：人傳人，沿都市/交通廊道快速擴散（北→全台）
    * 登革熱：病媒蚊傳播，局限南部、緩慢向鄰縣蔓延

使用方式：
  python seed_data.py              # 預設 ~350 筆，180 天
  python seed_data.py --scale 1.5  # 擴大 1.5 倍
  python seed_data.py --days 90    # 只取近 90 天
"""

import argparse
import math
import os
import random
import sqlite3
import uuid
from datetime import datetime, timedelta, timezone

from eicr_generator import generate_eicr, save_eicr
from medmorph_engine import (
    DB_PATH, OUTPUT_DIR,
    init_db, insert_case, create_submission,
    random_hospital, random_home,
)

# ── 基本資料 ───────────────────────────────────────────────────────────────────
SURNAMES    = ["王", "李", "張", "劉", "陳", "楊", "黃", "趙", "吳", "周",
               "林", "徐", "孫", "馬", "朱", "胡", "郭", "何", "高", "鄭",
               "羅", "梁", "宋", "謝", "唐", "韓", "曹", "許", "鄧", "洪"]
GIVEN_NAMES = ["小明", "小華", "大偉", "美玲", "志遠", "雅婷", "建宏", "淑芬",
               "冠廷", "怡君", "俊傑", "曉雯", "彥廷", "佳穎", "宇軒", "思穎",
               "宗翰", "育誠", "嘉豪", "淑媛", "奕辰", "詩涵", "智偉", "郁婷"]

# 縣市人口權重（用於呼吸道疾病的病例分布）
COUNTY_POP = {
    "台北市": 22, "新北市": 18, "桃園市": 12, "台中市": 11,
    "台南市": 8,  "高雄市": 10, "新竹縣": 3,  "新竹市": 3,
    "苗栗縣": 2,  "彰化縣": 3,  "南投縣": 1,  "雲林縣": 2,
    "嘉義縣": 1,  "嘉義市": 1,  "屏東縣": 2,  "宜蘭縣": 2,
    "花蓮縣": 1,  "台東縣": 1,  "基隆市": 2,  "澎湖縣": 1,
}

DISEASE_SYMPTOMS = {
    "COVID-19":  [["發燒", "咳嗽", "呼吸困難"],
                  ["發燒", "喪失嗅覺", "疲勞"],
                  ["咳嗽", "胸悶", "喉嚨痛"],
                  ["發燒", "肌肉酸痛", "頭痛"]],
    "Dengue":    [["高燒", "劇烈頭痛", "眼窩疼痛"],
                  ["高燒", "肌肉酸痛", "皮疹"],
                  ["發燒", "噁心", "骨骼疼痛"],
                  ["高燒", "出血傾向", "疲倦"]],
    "Influenza": [["發燒", "畏寒", "肌肉痠痛"],
                  ["發燒", "鼻塞", "喉嚨痛"],
                  ["咳嗽", "頭痛", "疲倦"],
                  ["發燒", "流鼻水", "全身無力"]],
}

# ── 爆發事件定義 ───────────────────────────────────────────────────────────────
# start_day  : 爆發開始（相對今天，負值=過去）
# peak_offset: 爆發開始後幾天達到高峰
# duration   : 爆發持續天數
# total_cases: 此波產生案例數
# county_delays: {縣市: 爆發開始後幾天出現第一例}
# spread_type:
#   "respiratory" → 人傳人，按人口權重分配
#   "vector"      → 病媒蚊，不依人口，僅限鄰近縣市
#
# 設計邏輯：
#   county_delays 越小 = 越早出現案例 = 在時間地圖上「顏色越淺/越舊」
#   county_delays 越大 = 越晚才傳入 = 顏色越深/越新，呈現擴散前線
# ────────────────────────────────────────────────────────────────────────────
OUTBREAKS: list[dict] = [
    # ── 流感：冬季，北部→全台（人傳人，沿交通廊道） ──────────────────────
    {
        "id":          "flu_winter",
        "disease":     "Influenza",
        "label":       "冬季流感（台北→全台）",
        "epicenter":   "台北市",
        "start_day":   -180,  # 半年前開始
        "peak_offset": 40,    # 第40天達高峰
        "duration":    95,
        "total_cases": 90,
        "spread_type": "respiratory",
        "county_delays": {
            # 北部核心：最早（0-7天）
            "台北市": 0, "新北市": 3, "基隆市": 5, "桃園市": 7,
            # 北部擴散（8-18天）
            "新竹市": 11, "新竹縣": 13, "宜蘭縣": 8, "苗栗縣": 17,
            # 中部（15-28天，沿高速公路廊道）
            "台中市": 15, "彰化縣": 20, "南投縣": 25,
            # 南部（27-42天）
            "雲林縣": 27, "嘉義縣": 30, "嘉義市": 30,
            "台南市": 33, "高雄市": 36, "屏東縣": 42,
            # 東部（交通較少，稍慢）
            "花蓮縣": 18, "台東縣": 28,
        },
    },
    # ── COVID-19 第一波：北部都市爆發 ─────────────────────────────────────
    {
        "id":          "covid_wave1",
        "disease":     "COVID-19",
        "label":       "COVID-19 第一波（台北→全台）",
        "epicenter":   "台北市",
        "start_day":   -175,
        "peak_offset": 35,
        "duration":    80,
        "total_cases": 75,
        "spread_type": "respiratory",
        "county_delays": {
            # 雙北：立即擴散
            "台北市": 0, "新北市": 4, "基隆市": 6,
            # 北部第二圈（6-15天）
            "桃園市": 8, "新竹市": 13, "新竹縣": 15, "宜蘭縣": 9,
            # 中部（15-25天）
            "苗栗縣": 18, "台中市": 17, "彰化縣": 22, "南投縣": 26,
            # 南部（24-36天，機場/高鐵跳躍）
            "台南市": 26, "高雄市": 28, "屏東縣": 34,
            "雲林縣": 28, "嘉義縣": 32, "嘉義市": 33,
            # 東部
            "花蓮縣": 17, "台東縣": 29,
        },
    },
    # ── 登革熱第一波：夏季高雄，病媒蚊緩慢南部蔓延 ───────────────────────
    {
        "id":          "dengue_south1",
        "disease":     "Dengue",
        "label":       "夏季登革熱（高雄→南部鄰縣）",
        "epicenter":   "高雄市",
        "start_day":   -155,  # 夏季開始
        "peak_offset": 45,
        "duration":    110,
        "total_cases": 58,
        "spread_type": "vector",  # 蚊媒：不依人口，地理鄰近優先
        "county_delays": {
            # 高雄市最早，病媒蚊蔓延到鄰縣需數週
            "高雄市": 0,
            "台南市": 22,  # 往北蔓延
            "屏東縣": 28,  # 往南蔓延
            "嘉義縣": 48,  # 再北上
            "嘉義市": 52,
            # 登革熱不傳至中北部（氣溫較低，蚊媒密度不足）
        },
    },
    # ── COVID-19 第二波：新北再爆發，更快速蔓延 ───────────────────────────
    {
        "id":          "covid_wave2",
        "disease":     "COVID-19",
        "label":       "COVID-19 第二波（新北→全台快速擴散）",
        "epicenter":   "新北市",
        "start_day":   -88,  # 約3個月前
        "peak_offset": 28,
        "duration":    78,
        "total_cases": 90,
        "spread_type": "respiratory",
        "county_delays": {
            # 新北→台北（3天），呈現從南往北的部分反轉
            "新北市": 0, "台北市": 3, "基隆市": 5, "桃園市": 6,
            # 北部（6-14天）
            "新竹市": 9, "新竹縣": 11, "宜蘭縣": 7, "苗栗縣": 14,
            # 中部（10-20天，第二波更快）
            "台中市": 10, "彰化縣": 14, "南投縣": 18,
            # 南部（15-25天）
            "雲林縣": 19, "嘉義縣": 21, "嘉義市": 21,
            "台南市": 15, "高雄市": 17, "屏東縣": 22,
            # 東部
            "花蓮縣": 14, "台東縣": 23,
        },
    },
    # ── 登革熱第二波：台南為中心的次波 ────────────────────────────────────
    {
        "id":          "dengue_south2",
        "disease":     "Dengue",
        "label":       "台南登革熱次波（→高雄/嘉義）",
        "epicenter":   "台南市",
        "start_day":   -68,  # 約2個月前，仍在夏末
        "peak_offset": 25,
        "duration":    65,
        "total_cases": 47,
        "spread_type": "vector",
        "county_delays": {
            "台南市": 0,
            "高雄市": 17,   # 往南
            "嘉義縣": 19,   # 往北
            "嘉義市": 21,
            "屏東縣": 25,
        },
    },
]


def random_name() -> str:
    return random.choice(SURNAMES) + random.choice(GIVEN_NAMES)


def random_birthdate() -> str:
    days = random.randint(365 * 18, 365 * 75)
    return (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")


# ── 核心：爆發案例生成 ─────────────────────────────────────────────────────────

def _epidemic_curve_weight(t: float, peak: float, sigma: float) -> float:
    """Gaussian epidemic curve weight at time t"""
    return math.exp(-0.5 * ((t - peak) / sigma) ** 2)


def generate_realistic_cases(days_back: int = 180,
                              scale: float = 1.0) -> list[dict]:
    """
    依 OUTBREAKS 定義產生真實疾病擴散模式的 mock 資料。

    spread 邏輯：
      - 每個爆發有一個 epicenter 縣市（最早出現案例）
      - 其他縣市依 county_delays 延遲出現
      - 同一縣市中，案例時間分布依 epidemic curve（高斯）
      - 呼吸道疾病依人口比例加權分配縣市內案例數
      - 病媒蚊疾病不依人口，純粹依縣市延遲時間分配
    """
    all_cases: list[dict] = []

    for outbreak in OUTBREAKS:
        disease      = outbreak["disease"]
        start_day    = outbreak["start_day"]
        peak_offset  = outbreak["peak_offset"]
        duration     = outbreak["duration"]
        total_target = max(1, int(outbreak["total_cases"] * scale))
        county_delays = outbreak["county_delays"]
        is_respiratory = outbreak["spread_type"] == "respiratory"

        sigma = duration / 4.0   # epidemic curve width

        generated = 0
        max_attempts = total_target * 8

        for _attempt in range(max_attempts):
            if generated >= total_target:
                break

            # 從 epidemic curve 抽樣：爆發開始後第幾天
            t_rel = random.gauss(peak_offset, sigma)
            t_rel = max(0.0, min(float(duration), t_rel))

            # 計算絕對時間（距今天數，負數 = 過去）
            day_abs = start_day + t_rel
            if day_abs > -0.08:       # 不超過現在
                continue
            if day_abs < -days_back:  # 不超過時間視窗
                continue

            # 找出此時已「被感染」的縣市
            eligible = [(county, delay)
                        for county, delay in county_delays.items()
                        if t_rel >= delay]
            if not eligible:
                continue

            # 縣市選擇權重
            weights = []
            for county, delay in eligible:
                time_active = t_rel - delay   # 此縣市已感染多少天

                # 越晚進入縣市的案例，在時間上的累積比例越高
                ramp = min(time_active / 14.0, 1.0)

                if is_respiratory:
                    # 呼吸道：按人口比例（大城市案例更多）
                    pop_w = COUNTY_POP.get(county, 2)
                else:
                    # 病媒蚊：不依人口（蚊蟲密度與人口關係較弱）
                    pop_w = 4.0

                weights.append(ramp * pop_w + 0.05)  # 0.05 避免全零

            total_w = sum(weights)
            r = random.uniform(0, total_w)
            county = eligible[-1][0]  # fallback
            for i, (c, _) in enumerate(eligible):
                r -= weights[i]
                if r <= 0:
                    county = c
                    break

            # 生成時間戳
            base_date = (datetime.now(timezone.utc) + timedelta(days=day_abs)).date()
            encounter_hour = int(random.triangular(8, 19, 10))
            encounter_min  = random.randint(0, 59)
            encounter_sec  = random.randint(0, 59)
            encounter_obj  = datetime(
                base_date.year, base_date.month, base_date.day,
                encounter_hour, encounter_min, encounter_sec,
                tzinfo=timezone.utc,
            )

            report_delay = timedelta(hours=random.uniform(2, 24))
            report_obj   = min(encounter_obj + report_delay,
                               datetime.now(timezone.utc) - timedelta(minutes=5))
            created_obj  = report_obj + timedelta(minutes=random.uniform(1, 30))

            # 確診率：爆發晚期略高（測試量能提升）
            time_ratio    = t_rel / duration
            confirmed_prob = 0.12 + 0.22 * time_ratio
            status = "confirmed" if random.random() < confirmed_prob else "suspected"

            hospital = random_hospital(county)
            home     = random_home(county)
            gender   = random.choice(["male", "female"])

            all_cases.append({
                "patient": {
                    "id":               f"patient-{uuid.uuid4().hex[:10]}",
                    "name":             random_name(),
                    "birthDate":        random_birthdate(),
                    "gender":           gender,
                    "county":           county,
                    "hospital_name":    hospital["name"],
                    "hospital_address": hospital["address"],
                    "hospital_lat":     hospital["lat"],
                    "hospital_lon":     hospital["lon"],
                    "home_address":     home["address"],
                    "home_district":    home["district"],
                    "home_lat":         home["lat"],
                    "home_lon":         home["lon"],
                },
                "condition": {
                    "id":            f"cond-{uuid.uuid4().hex[:8]}",
                    "disease":       disease,
                    "status":        status,
                    "symptoms":      random.choice(DISEASE_SYMPTOMS[disease]),
                    "encounter_date": encounter_obj.strftime("%Y-%m-%dT%H:%M:%SZ"),
                    "report_date":    report_obj.strftime("%Y-%m-%dT%H:%M:%SZ"),
                    "created_at":    created_obj.strftime("%Y-%m-%dT%H:%M:%SZ"),
                },
                "_outbreak_id": outbreak["id"],
            })
            generated += 1

    # 依通報時間排序
    all_cases.sort(key=lambda x: x["condition"]["report_date"])
    return all_cases


# ── 種入資料庫 ─────────────────────────────────────────────────────────────────

def seed(days_back: int = 180, scale: float = 1.0,
         db_path: str = DB_PATH, output_dir: str = OUTPUT_DIR) -> None:

    total_target = int(sum(o["total_cases"] for o in OUTBREAKS) * scale)
    print(f"🌱 產生真實疾病擴散 mock 資料（~{total_target} 筆，過去 {days_back} 天）…")
    for o in OUTBREAKS:
        print(f"   - {o['label']}：目標 {int(o['total_cases']*scale)} 筆")

    init_db(db_path)
    os.makedirs(output_dir, exist_ok=True)

    raw_cases = generate_realistic_cases(days_back=days_back, scale=scale)

    inserted = 0
    skipped  = 0

    for raw in raw_cases:
        patient   = raw["patient"]
        condition = raw["condition"]

        patient_data = {
            "id":               patient["id"],
            "name":             patient["name"],
            "birthDate":        patient["birthDate"],
            "gender":           patient["gender"],
            "disease":          condition["disease"],
            "county":           patient["county"],
            "status":           condition["status"],
            "encounter_date":   condition["encounter_date"],
            "report_date":      condition["report_date"],
            "symptoms":         condition["symptoms"],
            "hospital_name":    patient["hospital_name"],
            "hospital_address": patient["hospital_address"],
            "home_address":     patient["home_address"],
            "home_district":    patient["home_district"],
        }

        bundle    = generate_eicr(patient_data)
        eicr_path = save_eicr(bundle, output_dir=output_dir)

        case_record = {
            "id":               patient["id"],
            "patient_name":     patient["name"],
            "birthdate":        patient["birthDate"],
            "gender":           patient["gender"],
            "disease":          condition["disease"],
            "county":           patient["county"],
            "status":           condition["status"],
            "report_date":      condition["report_date"],
            "symptoms":         condition["symptoms"],
            "eicr_path":        eicr_path,
            "bundle_id":        bundle["id"],
            "created_at":       condition["created_at"],
            "hospital_name":    patient["hospital_name"],
            "hospital_address": patient["hospital_address"],
            "hospital_lat":     patient["hospital_lat"],
            "hospital_lon":     patient["hospital_lon"],
            "home_address":     patient["home_address"],
            "home_lat":         patient["home_lat"],
            "home_lon":         patient["home_lon"],
        }

        ok = insert_case(case_record, db_path=db_path)
        if ok:
            inserted += 1
            create_submission(
                case_id=patient["id"],
                bundle_id=bundle["id"],
                submitted_at=condition["report_date"],
                db_path=db_path,
            )
        else:
            skipped += 1

    print(f"\n✅ 完成！寫入 {inserted} 筆，略過重複 {skipped} 筆")
    print(f"   資料庫：{db_path}　eICR：{output_dir}/")

    # ── 摘要統計 ──────────────────────────────────────────────────────────────
    print()
    print("── 爆發波次分布統計 ────────────────────────────────────────────────")
    with sqlite3.connect(db_path) as conn:
        rows = conn.execute(
            "SELECT disease, county, COUNT(*) AS n FROM cases "
            "GROUP BY disease, county ORDER BY disease, n DESC"
        ).fetchall()
    current_d = None
    for disease, county, n in rows:
        if disease != current_d:
            print(f"\n  【{disease}】")
            current_d = disease
        print(f"    {county:<8} {n:>4} 筆")

    print()
    print("── 時間跨度統計 ────────────────────────────────────────────────────")
    with sqlite3.connect(db_path) as conn:
        first, last, total = conn.execute(
            "SELECT MIN(report_date), MAX(report_date), COUNT(*) FROM cases"
        ).fetchone()
    print(f"  最早通報：{first[:10]}　最晚通報：{last[:10]}　共 {total} 筆")
    print()
    print("🚀 現在可執行：streamlit run dashboard.py")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="真實疾病擴散 mock 資料")
    parser.add_argument("--days",  type=int,   default=180, help="資料涵蓋天數（預設 180）")
    parser.add_argument("--scale", type=float, default=1.0, help="案例數縮放倍率（預設 1.0）")
    parser.add_argument("--db",    type=str,   default=DB_PATH,    help="SQLite 路徑")
    parser.add_argument("--output",type=str,   default=OUTPUT_DIR, help="eICR 輸出目錄")
    args = parser.parse_args()

    seed(days_back=args.days, scale=args.scale,
         db_path=args.db, output_dir=args.output)
