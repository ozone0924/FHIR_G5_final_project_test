"""
程式 A：MedMorph 後端引擎
==========================
模仿 MedMorph Reference Architecture 的自動通報引擎。

功能：
  1. 每隔 POLL_INTERVAL 秒輪詢 FHIR server（預設：本地模擬模式）
  2. 偵測到 clinicalStatus=suspected 的 Condition 資源
  3. 抓取完整病患資料（Patient / Condition / Observation）
  4. 呼叫 eicr_generator 產生 eICR Bundle JSON
  5. 將案例寫入 SQLite 資料庫（供 Streamlit 儀表板讀取）
  6. 模擬 POST 送出通報（存成 JSON 檔案）

執行模式：
  - 本地模擬模式（預設）：自動產生假的 FHIR Condition 觸發事件
  - 真實 FHIR 模式：設定環境變數 FHIR_SERVER_URL 即可切換

使用方式：
  python medmorph_engine.py               # 本地模擬模式，持續執行
  FHIR_SERVER_URL=http://localhost:8080/fhir python medmorph_engine.py
"""

import json
import logging
import os
import random
import sqlite3
import time
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

import requests

from eicr_generator import generate_eicr, save_eicr

# ── 設定 ──────────────────────────────────────────────────────────────────────
FHIR_SERVER_URL: Optional[str] = os.getenv("FHIR_SERVER_URL")   # None = 模擬模式
POLL_INTERVAL: int = int(os.getenv("POLL_INTERVAL", "10"))       # 秒
DB_PATH: str = os.getenv("DB_PATH", "data/cases.db")
OUTPUT_DIR: str = os.getenv("OUTPUT_DIR", "output")
LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")

logging.basicConfig(
    level=getattr(logging, LOG_LEVEL),
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger("medmorph")

# ── 台灣縣市清單 ───────────────────────────────────────────────────────────────
TW_COUNTIES = [
    "台北市", "新北市", "桃園市", "台中市", "台南市", "高雄市",
    "新竹縣", "新竹市", "苗栗縣", "彰化縣", "南投縣", "雲林縣",
    "嘉義縣", "嘉義市", "屏東縣", "宜蘭縣", "花蓮縣", "台東縣",
    "澎湖縣", "基隆市",
]

# ── 疾病症狀對照 ───────────────────────────────────────────────────────────────
DISEASE_SYMPTOMS = {
    "COVID-19":  ["發燒", "咳嗽", "呼吸困難", "喪失嗅覺", "疲勞"],
    "Dengue":    ["高燒", "劇烈頭痛", "眼窩疼痛", "肌肉酸痛", "皮疹"],
    "Influenza": ["發燒", "畏寒", "肌肉痠痛", "鼻塞", "喉嚨痛"],
}

DISEASES = list(DISEASE_SYMPTOMS.keys())
STATUSES = ["suspected"] * 4 + ["confirmed"]  # 80% suspected, 20% confirmed
GENDERS = ["male", "female"]

# ── SQLite 初始化 ──────────────────────────────────────────────────────────────

def init_db(db_path: str = DB_PATH) -> None:
    """建立 SQLite 資料庫與 cases 資料表（若不存在）"""
    os.makedirs(os.path.dirname(db_path) if os.path.dirname(db_path) else ".", exist_ok=True)
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS cases (
                id           TEXT PRIMARY KEY,
                patient_name TEXT NOT NULL,
                birthdate    TEXT,
                gender       TEXT,
                disease      TEXT NOT NULL,
                county       TEXT NOT NULL,
                status       TEXT NOT NULL,
                report_date  TEXT NOT NULL,
                symptoms     TEXT,
                eicr_path    TEXT,
                bundle_id    TEXT,
                created_at   TEXT NOT NULL
            )
            """
        )
        conn.commit()
    log.info("✅ SQLite 資料庫初始化完成：%s", db_path)


def insert_case(case: dict, db_path: str = DB_PATH) -> bool:
    """
    將一筆案例寫入資料庫。若 ID 已存在則略過（避免重複）。
    Returns True if inserted, False if duplicate.
    """
    try:
        with sqlite3.connect(db_path) as conn:
            conn.execute(
                """
                INSERT OR IGNORE INTO cases
                    (id, patient_name, birthdate, gender, disease, county,
                     status, report_date, symptoms, eicr_path, bundle_id, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    case["id"],
                    case["patient_name"],
                    case.get("birthdate", ""),
                    case.get("gender", "unknown"),
                    case["disease"],
                    case["county"],
                    case["status"],
                    case["report_date"],
                    json.dumps(case.get("symptoms", []), ensure_ascii=False),
                    case.get("eicr_path", ""),
                    case.get("bundle_id", ""),
                    datetime.now(timezone.utc).isoformat(),
                ),
            )
            inserted = conn.execute(
                "SELECT changes()"
            ).fetchone()[0]
            conn.commit()
        return inserted > 0
    except sqlite3.Error as e:
        log.error("❌ DB 寫入失敗：%s", e)
        return False


# ── 模擬 FHIR Client（本地模式） ───────────────────────────────────────────────

def _random_tw_name() -> str:
    """產生隨機中文姓名"""
    surnames = ["王", "李", "張", "劉", "陳", "楊", "黃", "趙", "吳", "周", "林", "徐"]
    names = ["小明", "小華", "大偉", "美玲", "志遠", "雅婷", "建宏", "淑芬", "冠廷", "怡君"]
    return random.choice(surnames) + random.choice(names)


def _random_birthdate() -> str:
    """產生隨機生日（20-80 歲）"""
    days_ago = random.randint(365 * 20, 365 * 80)
    dt = datetime.now() - timedelta(days=days_ago)
    return dt.strftime("%Y-%m-%d")


class MockFHIRPoller:
    """
    本地模擬 FHIR 輪詢器。
    每次 poll() 有 40% 機率「發現」1-3 筆新 suspected 案例。
    """

    def __init__(self):
        self._seen_ids: set = set()

    def poll_suspected_conditions(self) -> list[dict]:
        """模擬 GET /Condition?clinical-status=suspected&_include=Condition:patient"""
        if random.random() > 0.40:
            return []   # 這輪沒有新案例

        new_cases = []
        count = random.randint(1, 3)
        for _ in range(count):
            pid = f"patient-{uuid.uuid4().hex[:8]}"
            disease = random.choice(DISEASES)
            symptoms = random.sample(DISEASE_SYMPTOMS[disease], k=random.randint(2, 4))
            encounter_dt = (
                datetime.now(timezone.utc) - timedelta(hours=random.randint(0, 48))
            ).strftime("%Y-%m-%dT%H:%M:%SZ")

            fhir_condition = {
                # 模擬 FHIR Condition resource
                "patient": {
                    "id": pid,
                    "name": _random_tw_name(),
                    "birthDate": _random_birthdate(),
                    "gender": random.choice(GENDERS),
                    "county": random.choices(
                        TW_COUNTIES,
                        weights=[20, 15, 10, 8, 8, 8, 3, 3, 2, 2, 2, 2, 2, 2, 2, 2, 2, 2, 1, 2],
                        k=1
                    )[0],
                },
                "condition": {
                    "id": f"cond-{uuid.uuid4().hex[:8]}",
                    "disease": disease,
                    "status": random.choice(STATUSES),
                    "symptoms": symptoms,
                    "encounter_date": encounter_dt,
                },
            }
            new_cases.append(fhir_condition)

        return new_cases


class RealFHIRPoller:
    """
    真實 HAPI FHIR Server 輪詢器。
    連接 FHIR_SERVER_URL，查詢最近 N 分鐘內新增的 suspected Condition。
    """

    def __init__(self, base_url: str):
        self.base_url = base_url.rstrip("/")
        self._last_poll: Optional[datetime] = None
        log.info("🔗 FHIR Server：%s", self.base_url)

    def _get(self, path: str, params: dict = None) -> Optional[dict]:
        try:
            resp = requests.get(
                f"{self.base_url}/{path}",
                params=params,
                timeout=10,
                headers={"Accept": "application/fhir+json"},
            )
            resp.raise_for_status()
            return resp.json()
        except requests.RequestException as e:
            log.warning("⚠️  FHIR 請求失敗：%s", e)
            return None

    def _get_patient(self, patient_id: str) -> Optional[dict]:
        return self._get(f"Patient/{patient_id}")

    def poll_suspected_conditions(self) -> list[dict]:
        """
        查詢 FHIR server 上 clinicalStatus=suspected 的 Condition，
        並合併對應的 Patient 資料。
        """
        now = datetime.now(timezone.utc)
        since = self._last_poll or (now - timedelta(minutes=5))
        self._last_poll = now

        params = {
            "clinical-status": "suspected",
            "_lastUpdated": f"gt{since.strftime('%Y-%m-%dT%H:%M:%SZ')}",
            "_count": 20,
        }
        bundle = self._get("Condition", params=params)
        if not bundle or bundle.get("total", 0) == 0:
            return []

        results = []
        for entry in bundle.get("entry", []):
            cond = entry.get("resource", {})
            subject_ref = cond.get("subject", {}).get("reference", "")
            patient_id = subject_ref.split("/")[-1] if subject_ref else None
            if not patient_id:
                continue

            patient = self._get_patient(patient_id)
            if not patient:
                continue

            # 解析疾病代碼
            coding = (cond.get("code", {}).get("coding") or [{}])[0]
            disease_display = coding.get("display", "Unknown")
            disease = next(
                (d for d in DISEASES if d.lower() in disease_display.lower()),
                "COVID-19",
            )

            # 解析縣市
            address = (patient.get("address") or [{}])[0]
            county = address.get("district") or address.get("city") or "台北市"

            results.append({
                "patient": {
                    "id": patient_id,
                    "name": (patient.get("name") or [{}])[0].get("text", "未知"),
                    "birthDate": patient.get("birthDate", ""),
                    "gender": patient.get("gender", "unknown"),
                    "county": county,
                },
                "condition": {
                    "id": cond.get("id", _new_id()),
                    "disease": disease,
                    "status": "suspected",
                    "symptoms": [],
                    "encounter_date": cond.get(
                        "onsetDateTime",
                        datetime.now(timezone.utc).isoformat(),
                    ),
                },
            })

        return results


def _new_id() -> str:
    return uuid.uuid4().hex[:8]


# ── 核心處理流程 ───────────────────────────────────────────────────────────────

def process_case(raw: dict, db_path: str = DB_PATH, output_dir: str = OUTPUT_DIR) -> dict:
    """
    處理單筆 FHIR Condition 觸發事件：
      1. 組裝 patient_data
      2. 呼叫 eICR 產生器
      3. 儲存 eICR JSON
      4. 寫入 SQLite
    """
    patient = raw["patient"]
    condition = raw["condition"]

    patient_data = {
        "id": patient["id"],
        "name": patient["name"],
        "birthDate": patient.get("birthDate", ""),
        "gender": patient.get("gender", "unknown"),
        "disease": condition["disease"],
        "county": patient["county"],
        "status": condition["status"],
        "encounter_date": condition.get("encounter_date", ""),
        "symptoms": condition.get("symptoms", []),
    }

    # 產生 eICR
    bundle = generate_eicr(patient_data)
    eicr_path = save_eicr(bundle, output_dir=output_dir)

    # 組裝資料庫記錄
    case_record = {
        "id": patient["id"],
        "patient_name": patient["name"],
        "birthdate": patient.get("birthDate", ""),
        "gender": patient.get("gender", "unknown"),
        "disease": condition["disease"],
        "county": patient["county"],
        "status": condition["status"],
        "report_date": condition.get("encounter_date", datetime.now().strftime("%Y-%m-%dT%H:%M:%SZ")),
        "symptoms": condition.get("symptoms", []),
        "eicr_path": eicr_path,
        "bundle_id": bundle["id"],
    }

    inserted = insert_case(case_record, db_path=db_path)
    if inserted:
        log.info(
            "📋 新案例 → %s | %s | %s | %s",
            patient["name"],
            condition["disease"],
            condition["status"],
            patient["county"],
        )
    else:
        log.debug("↩️  重複案例，略過：%s", patient["id"])

    return case_record


def simulate_report_submission(bundle: dict) -> bool:
    """
    模擬將 eICR 送出給公衛單位（此處僅印 log）。
    實際部署時可替換成 POST 到 NPHIES 或疾管署 API。
    """
    log.info(
        "📤 [模擬送出] eICR Bundle %s → 疾病管制署通報系統",
        bundle["id"][:8],
    )
    return True


# ── 主迴圈 ────────────────────────────────────────────────────────────────────

def run_engine(
    db_path: str = DB_PATH,
    output_dir: str = OUTPUT_DIR,
    poll_interval: int = POLL_INTERVAL,
) -> None:
    """
    啟動 MedMorph 引擎主迴圈。
    Ctrl+C 可安全中止。
    """
    init_db(db_path)
    os.makedirs(output_dir, exist_ok=True)

    # 選擇輪詢器
    if FHIR_SERVER_URL:
        poller = RealFHIRPoller(FHIR_SERVER_URL)
        mode = f"真實 FHIR 模式 ({FHIR_SERVER_URL})"
    else:
        poller = MockFHIRPoller()
        mode = "本地模擬模式"

    log.info("🚀 MedMorph 引擎啟動 — %s", mode)
    log.info("   輪詢間隔：%d 秒 | DB：%s | 輸出：%s", poll_interval, db_path, output_dir)
    log.info("   按 Ctrl+C 停止")

    cycle = 0
    try:
        while True:
            cycle += 1
            log.debug("⏱  第 %d 輪輪詢…", cycle)

            cases = poller.poll_suspected_conditions()
            if cases:
                log.info("🔔 偵測到 %d 筆新案例，開始處理…", len(cases))
                for raw in cases:
                    process_case(raw, db_path=db_path, output_dir=output_dir)
            else:
                log.debug("   無新案例")

            time.sleep(poll_interval)

    except KeyboardInterrupt:
        log.info("🛑 引擎已停止（Ctrl+C）")


# ── 單次觸發（供測試用） ───────────────────────────────────────────────────────

def trigger_once(disease: str = "COVID-19", county: str = "台北市") -> dict:
    """
    手動觸發一筆指定疾病與縣市的假案例（供單元測試 / demo 使用）。
    """
    init_db()
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    poller = MockFHIRPoller()
    # 強制產生案例
    cases = []
    while not cases:
        cases = poller.poll_suspected_conditions()

    # 覆寫疾病與縣市
    cases[0]["condition"]["disease"] = disease
    cases[0]["patient"]["county"] = county

    return process_case(cases[0])


if __name__ == "__main__":
    run_engine()
