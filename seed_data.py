"""
seed_data.py — Demo 假資料注入腳本
=====================================
為儀表板 demo 預先產生 N 筆橫跨多天、多疾病、多縣市的假案例，
並寫入 SQLite 資料庫與對應的 eICR JSON 檔案。

使用方式：
  python seed_data.py              # 預設產生 120 筆，30 天內
  python seed_data.py --count 200 --days 60
"""

import argparse
import json
import os
import random
import sqlite3
import uuid
from datetime import datetime, timedelta, timezone

from eicr_generator import generate_eicr, save_eicr
from medmorph_engine import (
    init_db, insert_case, DB_PATH, OUTPUT_DIR,
    random_hospital, random_home,
    HOSPITALS, DISTRICTS,
)

# ── 測試資料設定 ───────────────────────────────────────────────────────────────
SURNAMES    = ["王", "李", "張", "劉", "陳", "楊", "黃", "趙", "吳", "周",
               "林", "徐", "孫", "馬", "朱", "胡", "郭", "何", "高", "鄭"]
GIVEN_NAMES = ["小明", "小華", "大偉", "美玲", "志遠", "雅婷", "建宏", "淑芬",
               "冠廷", "怡君", "俊傑", "曉雯", "彥廷", "佳穎", "宇軒", "思穎"]

COUNTIES = [
    ("台北市",  22), ("新北市", 18), ("桃園市", 12), ("台中市", 11),
    ("台南市",   8), ("高雄市", 10), ("新竹縣",  3), ("新竹市",  3),
    ("苗栗縣",   2), ("彰化縣",  3), ("南投縣",  1), ("雲林縣",  2),
    ("嘉義縣",   1), ("嘉義市",  1), ("屏東縣",  2), ("宜蘭縣",  2),
    ("花蓮縣",   1), ("台東縣",  1), ("基隆市",  2), ("澎湖縣",  1),
]
COUNTY_NAMES   = [c[0] for c in COUNTIES]
COUNTY_WEIGHTS = [c[1] for c in COUNTIES]

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

DISEASE_WEIGHTS = {"COVID-19": 0.45, "Influenza": 0.35, "Dengue": 0.20}
STATUS_WEIGHTS  = {"suspected": 0.75, "confirmed": 0.25}


def random_name() -> str:
    return random.choice(SURNAMES) + random.choice(GIVEN_NAMES)


def random_birthdate() -> str:
    days = random.randint(365 * 18, 365 * 75)
    return (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")


def random_encounter_date(days_back: int) -> datetime:
    """在過去 days_back 天內隨機選一個就診時間（回傳 datetime UTC）"""
    offset_minutes = random.randint(0, days_back * 24 * 60)
    return datetime.now(timezone.utc) - timedelta(minutes=offset_minutes)


def generate_seed_cases(count: int = 120, days_back: int = 30) -> list[dict]:
    """產生 count 筆假案例資料"""
    cases    = []
    diseases = list(DISEASE_WEIGHTS.keys())
    d_weights = list(DISEASE_WEIGHTS.values())
    statuses  = list(STATUS_WEIGHTS.keys())
    s_weights = list(STATUS_WEIGHTS.values())

    for _ in range(count):
        pid      = f"patient-{uuid.uuid4().hex[:10]}"
        disease  = random.choices(diseases, weights=d_weights, k=1)[0]
        status   = random.choices(statuses, weights=s_weights, k=1)[0]
        county   = random.choices(COUNTY_NAMES, weights=COUNTY_WEIGHTS, k=1)[0]
        symptoms = random.choice(DISEASE_SYMPTOMS[disease])

        # ── 時間序列（模擬真實通報流程） ──────────────────────────────────────
        # 就診時間：過去 days_back 天內某個時刻
        encounter_obj = random_encounter_date(days_back)
        # 通報時間：就診後 2–24 小時（醫師填寫後送出）
        report_delay  = timedelta(hours=random.uniform(2, 24))
        report_obj    = min(encounter_obj + report_delay,
                            datetime.now(timezone.utc) - timedelta(minutes=5))
        # eICR 建立時間：通報後 1–30 分鐘（系統自動產生）
        created_obj   = report_obj + timedelta(minutes=random.uniform(1, 30))

        encounter_dt = encounter_obj.strftime("%Y-%m-%dT%H:%M:%SZ")
        report_dt    = report_obj.strftime("%Y-%m-%dT%H:%M:%SZ")
        created_at   = created_obj.strftime("%Y-%m-%dT%H:%M:%SZ")

        # ── 地理資料 ──────────────────────────────────────────────────────────
        hospital = random_hospital(county)
        home     = random_home(county)

        cases.append({
            "patient": {
                "id":               pid,
                "name":             random_name(),
                "birthDate":        random_birthdate(),
                "gender":           random.choice(["male", "female"]),
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
                "symptoms":      symptoms,
                "encounter_date": encounter_dt,
                "report_date":    report_dt,
                "created_at":    created_at,
            },
        })
    return cases


def seed(count: int = 120, days_back: int = 30,
         db_path: str = DB_PATH, output_dir: str = OUTPUT_DIR) -> None:
    """主函式：產生假資料並寫入 DB"""
    print(f"🌱 開始產生 {count} 筆假案例（過去 {days_back} 天）…")

    init_db(db_path)
    os.makedirs(output_dir, exist_ok=True)

    raw_cases = generate_seed_cases(count=count, days_back=days_back)

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
        else:
            skipped += 1

    print(f"\n✅ 完成！寫入 {inserted} 筆，略過重複 {skipped} 筆")
    print(f"   資料庫：{db_path}")
    print(f"   eICR 輸出：{output_dir}/")
    print()

    with sqlite3.connect(db_path) as conn:
        rows = conn.execute(
            "SELECT disease, status, COUNT(*) as cnt FROM cases "
            "GROUP BY disease, status ORDER BY disease, status"
        ).fetchall()

    print("── 案例分布統計 ─────────────────────────────")
    print(f"  {'疾病':<12} {'狀態':<12} {'筆數':>6}")
    print("  " + "-" * 32)
    for disease, status, cnt in rows:
        print(f"  {disease:<12} {status:<12} {cnt:>6}")
    total = sum(r[2] for r in rows)
    print("  " + "-" * 32)
    print(f"  {'合計':<24} {total:>6}")
    print()
    print("🚀 現在可以執行：streamlit run dashboard.py")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="注入 demo 假資料")
    parser.add_argument("--count",  type=int, default=120,       help="產生案例數（預設 120）")
    parser.add_argument("--days",   type=int, default=30,        help="資料涵蓋天數（預設 30）")
    parser.add_argument("--db",     type=str, default=DB_PATH,   help="SQLite 路徑")
    parser.add_argument("--output", type=str, default=OUTPUT_DIR, help="eICR 輸出目錄")
    args = parser.parse_args()

    seed(count=args.count, days_back=args.days,
         db_path=args.db, output_dir=args.output)
