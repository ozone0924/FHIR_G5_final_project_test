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
FHIR_SERVER_URL: Optional[str] = os.getenv("FHIR_SERVER_URL")
POLL_INTERVAL: int = int(os.getenv("POLL_INTERVAL", "10"))
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
TW_COUNTY_WEIGHTS = [20, 15, 10, 8, 8, 8, 3, 3, 2, 2, 2, 2, 2, 2, 2, 2, 2, 2, 1, 2]

# ── 疾病症狀對照 ───────────────────────────────────────────────────────────────
DISEASE_SYMPTOMS = {
    "COVID-19":  ["發燒", "咳嗽", "呼吸困難", "喪失嗅覺", "疲勞"],
    "Dengue":    ["高燒", "劇烈頭痛", "眼窩疼痛", "肌肉酸痛", "皮疹"],
    "Influenza": ["發燒", "畏寒", "肌肉痠痛", "鼻塞", "喉嚨痛"],
}

DISEASES = list(DISEASE_SYMPTOMS.keys())
STATUSES = ["suspected"] * 4 + ["confirmed"]
GENDERS  = ["male", "female"]

# ── 台灣醫療院所（通報院所生成用） ────────────────────────────────────────────
# 格式：(機構名稱, 縣市, 地址, 緯度, 經度)
HOSPITALS: list[tuple] = [
    # 台北市
    ("台大醫院",             "台北市", "台北市中正區中山南路7號",       25.0430, 121.5188),
    ("台北榮民總醫院",       "台北市", "台北市北投區石牌路二段201號",   25.1143, 121.5165),
    ("台北馬偕醫院",         "台北市", "台北市中山區中山北路二段92號",  25.0542, 121.5259),
    ("台北長庚醫院",         "台北市", "台北市松山區敦化北路199號",     25.0831, 121.5519),
    ("三軍總醫院",           "台北市", "台北市內湖區成功路二段325號",   25.0651, 121.5842),
    ("萬芳醫院",             "台北市", "台北市文山區興隆路三段111號",   24.9988, 121.5703),
    ("振興醫院",             "台北市", "台北市北投區振興街45號",         25.0965, 121.5125),
    ("台北市立聯合醫院",     "台北市", "台北市大同區鄭州路145號",       25.0529, 121.5155),
    # 新北市
    ("亞東醫院",             "新北市", "新北市板橋區南雅南路二段21號",  24.9906, 121.4544),
    ("雙和醫院",             "新北市", "新北市中和區中正路291號",        24.9997, 121.5142),
    ("輔仁大學附設醫院",     "新北市", "新北市新莊區中正路510號",       25.0297, 121.4271),
    ("汐止國泰醫院",         "新北市", "新北市汐止區建成路59號",        25.0623, 121.6603),
    ("新北市立聯合醫院",     "新北市", "新北市三重區中興北街6號",       25.0618, 121.4921),
    # 桃園市
    ("林口長庚醫院",         "桃園市", "桃園市龜山區舒適路5號",         25.0651, 121.3432),
    ("桃園醫院",             "桃園市", "桃園市桃園區中山路1492號",      24.9929, 121.3038),
    ("敏盛醫院",             "桃園市", "桃園市桃園區經國路168號",        24.9949, 121.3080),
    ("壢新醫院",             "桃園市", "桃園市中壢區民族路200號",       24.9634, 121.2246),
    # 台中市
    ("台中榮民總醫院",       "台中市", "台中市西屯區臺灣大道四段1650號", 24.1640, 120.6440),
    ("中國醫藥大學附設醫院", "台中市", "台中市北區育德路2號",            24.1395, 120.6657),
    ("台中慈濟醫院",         "台中市", "台中市潭子區豐興路一段1號",     24.2041, 120.7139),
    ("澄清醫院",             "台中市", "台中市西區中港路一段101號",     24.1535, 120.6549),
    # 台南市
    ("成功大學醫學院附設醫院", "台南市", "台南市北區勝利路138號",       22.9893, 120.2154),
    ("奇美醫院",             "台南市", "台南市永康區中華路901號",        22.9688, 120.2234),
    ("郭綜合醫院",           "台南市", "台南市中西區民生路二段22號",    22.9966, 120.1978),
    ("台南市立醫院",         "台南市", "台南市東區崇德路670號",          23.0015, 120.2080),
    # 高雄市
    ("高雄榮民總醫院",       "高雄市", "高雄市左營區大中一路386號",     22.6797, 120.2918),
    ("高雄長庚醫院",         "高雄市", "高雄市鳥松區大埤路123號",       22.7541, 120.3875),
    ("高雄醫學大學附設醫院", "高雄市", "高雄市三民區自由一路100號",     22.6295, 120.3101),
    ("義大醫院",             "高雄市", "高雄市燕巢區角宿里義大路1號",   22.7204, 120.4151),
    ("高雄市立大同醫院",     "高雄市", "高雄市前金區中華三路68號",      22.6286, 120.2946),
    # 其他縣市
    ("新竹馬偕醫院",         "新竹市", "新竹市東區光復路二段690號",     24.7893, 121.0029),
    ("竹北台大分院",         "新竹縣", "新竹縣竹北市光明六路東二段21號", 24.8349, 121.0121),
    ("苗栗為恭醫院",         "苗栗縣", "苗栗縣頭份市信義路128號",       24.6908, 120.8770),
    ("彰化基督教醫院",       "彰化縣", "彰化市旭光路135號",              24.0833, 120.5395),
    ("員林基督教醫院",       "彰化縣", "彰化縣員林市莒光路356號",       23.9578, 120.5734),
    ("南投醫院",             "南投縣", "南投市復興路478號",               23.9127, 120.6854),
    ("雲林成大醫院",         "雲林縣", "雲林縣斗六市雲林路二段457號",   23.7062, 120.5414),
    ("嘉義基督教醫院",       "嘉義市", "嘉義市忠孝路539號",              23.4733, 120.4391),
    ("屏東醫院",             "屏東縣", "屏東市中山路270號",               22.6735, 120.4888),
    ("宜蘭縣立醫院",         "宜蘭縣", "宜蘭市新民路152號",              24.7453, 121.7521),
    ("花蓮慈濟醫院",         "花蓮縣", "花蓮市中央路三段707號",          23.9736, 121.5997),
    ("台東基督教醫院",       "台東縣", "台東市開封街350號",               22.7529, 121.1443),
    ("基隆長庚醫院",         "基隆市", "基隆市安樂區麥金路222號",        25.1344, 121.7209),
    ("澎湖馬公醫院",         "澎湖縣", "澎湖縣馬公市中正路73號",         23.5640, 119.5590),
    ("嘉義縣立醫院",         "嘉義縣", "嘉義縣太保市祥和一路東段1號",   23.4561, 120.3371),
]

# ── 台灣縣市區域（住家地址生成用） ───────────────────────────────────────────
# 格式：{縣市: [(區域名稱, 緯度, 經度), ...]}
DISTRICTS: dict[str, list[tuple]] = {
    "台北市": [
        ("中正區", 25.0428, 121.5197), ("大安區", 25.0269, 121.5436),
        ("信義區", 25.0330, 121.5654), ("中山區", 25.0630, 121.5293),
        ("松山區", 25.0502, 121.5778), ("內湖區", 25.0830, 121.5876),
        ("士林區", 25.0935, 121.5255), ("北投區", 25.1317, 121.5001),
        ("萬華區", 25.0299, 121.4997), ("文山區", 24.9982, 121.5758),
        ("大同區", 25.0586, 121.5090), ("南港區", 25.0548, 121.6071),
    ],
    "新北市": [
        ("板橋區", 25.0118, 121.4654), ("三重區", 25.0664, 121.4873),
        ("中和區", 24.9982, 121.4974), ("永和區", 25.0130, 121.5186),
        ("新莊區", 25.0393, 121.4488), ("淡水區", 25.1680, 121.4479),
        ("土城區", 24.9687, 121.4436), ("新店區", 24.9718, 121.5402),
        ("汐止區", 25.0697, 121.6638), ("蘆洲區", 25.0819, 121.4707),
        ("林口區", 25.0715, 121.3714), ("三峽區", 24.9350, 121.3726),
    ],
    "桃園市": [
        ("桃園區", 24.9929, 121.3009), ("中壢區", 24.9634, 121.2246),
        ("平鎮區", 24.9424, 121.2151), ("八德區", 24.9439, 121.3018),
        ("龜山區", 24.9964, 121.3440), ("楊梅區", 24.9144, 121.1456),
        ("蘆竹區", 25.0429, 121.3085), ("大溪區", 24.8811, 121.2887),
    ],
    "台中市": [
        ("北區",   24.1542, 120.6720), ("西區",   24.1427, 120.6647),
        ("南區",   24.1218, 120.6709), ("東區",   24.1419, 120.6876),
        ("北屯區", 24.1780, 120.7100), ("西屯區", 24.1640, 120.6440),
        ("南屯區", 24.1259, 120.6390), ("豐原區", 24.2508, 120.7194),
        ("太平區", 24.1253, 120.7372), ("烏日區", 24.0823, 120.6420),
    ],
    "台南市": [
        ("中西區", 22.9966, 120.1978), ("東區",   23.0015, 120.2280),
        ("北區",   23.0136, 120.2048), ("南區",   22.9765, 120.1956),
        ("安平區", 22.9976, 120.1619), ("安南區", 23.0404, 120.1773),
        ("永康區", 22.9688, 120.2493), ("歸仁區", 22.9380, 120.2729),
        ("新化區", 23.0363, 120.3115), ("善化區", 23.1408, 120.3040),
    ],
    "高雄市": [
        ("前金區", 22.6286, 120.2946), ("三民區", 22.6375, 120.3101),
        ("苓雅區", 22.6175, 120.3150), ("前鎮區", 22.5975, 120.3102),
        ("鳳山區", 22.6220, 120.3551), ("左營區", 22.6797, 120.2918),
        ("楠梓區", 22.7338, 120.3131), ("小港區", 22.5687, 120.3457),
        ("鳥松區", 22.7541, 120.3875), ("仁武區", 22.6840, 120.3617),
        ("岡山區", 22.7965, 120.2948), ("旗山區", 22.8907, 120.4809),
    ],
    "新竹市": [
        ("東區", 24.7893, 121.0029), ("北區", 24.8138, 120.9675),
        ("香山區", 24.7517, 120.9422),
    ],
    "新竹縣": [
        ("竹北市", 24.8349, 121.0121), ("竹東鎮", 24.7385, 121.0919),
        ("新埔鎮", 24.8249, 121.0664), ("關西鎮", 24.7914, 121.1726),
    ],
    "苗栗縣": [
        ("苗栗市", 24.5600, 120.8214), ("頭份市", 24.6908, 120.8770),
        ("通霄鎮", 24.4499, 120.6845), ("竹南鎮", 24.6874, 120.8694),
    ],
    "彰化縣": [
        ("彰化市", 24.0833, 120.5395), ("員林市", 23.9578, 120.5734),
        ("和美鎮", 24.1033, 120.5105), ("鹿港鎮", 24.0542, 120.4335),
        ("溪湖鎮", 23.9681, 120.4636), ("二林鎮", 23.9006, 120.3847),
    ],
    "南投縣": [
        ("南投市", 23.9127, 120.6854), ("草屯鎮", 23.9726, 120.6655),
        ("埔里鎮", 23.9628, 120.9731), ("竹山鎮", 23.7488, 120.6685),
    ],
    "雲林縣": [
        ("斗六市", 23.7062, 120.5414), ("虎尾鎮", 23.7081, 120.4358),
        ("斗南鎮", 23.6803, 120.4803), ("西螺鎮", 23.7988, 120.4650),
    ],
    "嘉義縣": [
        ("太保市", 23.4561, 120.3371), ("朴子市", 23.4549, 120.2454),
        ("水上鄉", 23.4404, 120.2756), ("民雄鄉", 23.5543, 120.4433),
    ],
    "嘉義市": [
        ("東區", 23.4800, 120.4491), ("西區", 23.4700, 120.4291),
    ],
    "屏東縣": [
        ("屏東市", 22.6735, 120.4888), ("潮州鎮", 22.5491, 120.5433),
        ("東港鎮", 22.4642, 120.4543), ("恆春鎮", 22.0031, 120.7439),
        ("里港鄉", 22.7563, 120.4869), ("內埔鄉", 22.6105, 120.5641),
    ],
    "宜蘭縣": [
        ("宜蘭市", 24.7453, 121.7521), ("羅東鎮", 24.6781, 121.7705),
        ("蘇澳鎮", 24.5985, 121.8560), ("礁溪鄉", 24.8240, 121.7727),
    ],
    "花蓮縣": [
        ("花蓮市", 23.9736, 121.5997), ("吉安鄉", 23.9461, 121.5866),
        ("壽豐鄉", 23.8471, 121.5557), ("鳳林鎮", 23.7326, 121.4568),
    ],
    "台東縣": [
        ("台東市", 22.7529, 121.1443), ("成功鎮", 23.0989, 121.3720),
        ("卑南鄉", 22.7011, 121.1221),
    ],
    "澎湖縣": [
        ("馬公市", 23.5711, 119.5793), ("湖西鄉", 23.6064, 119.6388),
    ],
    "基隆市": [
        ("仁愛區", 25.1276, 121.7392), ("中正區", 25.1188, 121.7325),
        ("安樂區", 25.1344, 121.7209), ("暖暖區", 25.0851, 121.7524),
    ],
}

# 地址生成用路名
_ROADS = [
    "中山路", "民生路", "復興路", "忠孝路", "仁愛路", "信義路",
    "和平路", "文化路", "建國路", "光復路", "中正路", "中華路",
    "自由路", "民權路", "成功路", "博愛路", "民族路", "中興路",
    "大同路", "新生路",
]


def random_hospital(county: str) -> dict:
    """根據縣市隨機選擇一家通報醫院"""
    candidates = [h for h in HOSPITALS if h[1] == county]
    if not candidates:
        candidates = HOSPITALS
    h = random.choice(candidates)
    return {"name": h[0], "county": h[1], "address": h[2], "lat": h[3], "lon": h[4]}


def random_home(county: str) -> dict:
    """根據縣市隨機產生病患住家地址與座標"""
    districts = DISTRICTS.get(county)
    if districts:
        d_name, base_lat, base_lon = random.choice(districts)
    else:
        d_name = "市區"
        base_lat, base_lon = 23.8, 121.0
    lat = round(base_lat + random.uniform(-0.006, 0.006), 6)
    lon = round(base_lon + random.uniform(-0.006, 0.006), 6)
    road   = random.choice(_ROADS)
    number = random.randint(1, 500)
    address = f"{county}{d_name}{road}{number}號"
    return {"address": address, "district": d_name, "lat": lat, "lon": lon}


# ── SQLite 初始化 ──────────────────────────────────────────────────────────────

def init_db(db_path: str = DB_PATH) -> None:
    """建立 SQLite 資料庫與 cases 資料表（若不存在），並遷移新欄位"""
    os.makedirs(os.path.dirname(db_path) if os.path.dirname(db_path) else ".", exist_ok=True)
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS cases (
                id               TEXT PRIMARY KEY,
                patient_name     TEXT NOT NULL,
                birthdate        TEXT,
                gender           TEXT,
                disease          TEXT NOT NULL,
                county           TEXT NOT NULL,
                status           TEXT NOT NULL,
                report_date      TEXT NOT NULL,
                symptoms         TEXT,
                eicr_path        TEXT,
                bundle_id        TEXT,
                created_at       TEXT NOT NULL,
                hospital_name    TEXT,
                hospital_address TEXT,
                hospital_lat     REAL,
                hospital_lon     REAL,
                home_address     TEXT,
                home_lat         REAL,
                home_lon         REAL
            )
            """
        )
        # 遷移：為舊版 DB 補充新欄位
        existing = {row[1] for row in conn.execute("PRAGMA table_info(cases)")}
        for col_def in [
            ("hospital_name",    "TEXT"),
            ("hospital_address", "TEXT"),
            ("hospital_lat",     "REAL"),
            ("hospital_lon",     "REAL"),
            ("home_address",     "TEXT"),
            ("home_lat",         "REAL"),
            ("home_lon",         "REAL"),
        ]:
            if col_def[0] not in existing:
                conn.execute(f"ALTER TABLE cases ADD COLUMN {col_def[0]} {col_def[1]}")
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
                     status, report_date, symptoms, eicr_path, bundle_id, created_at,
                     hospital_name, hospital_address, hospital_lat, hospital_lon,
                     home_address, home_lat, home_lon)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                    case.get("created_at", datetime.now(timezone.utc).isoformat()),
                    case.get("hospital_name", ""),
                    case.get("hospital_address", ""),
                    case.get("hospital_lat"),
                    case.get("hospital_lon"),
                    case.get("home_address", ""),
                    case.get("home_lat"),
                    case.get("home_lon"),
                ),
            )
            inserted = conn.execute("SELECT changes()").fetchone()[0]
            conn.commit()
        return inserted > 0
    except sqlite3.Error as e:
        log.error("❌ DB 寫入失敗：%s", e)
        return False


# ── 模擬 FHIR Client（本地模式） ───────────────────────────────────────────────

def _random_tw_name(gender: str) -> str:
    surnames = [
        "陳", "林", "黃", "張", "李", "王", "吳", "劉", "蔡", "楊",
        "許", "鄭", "謝", "洪", "郭", "邱", "曾", "廖", "賴", "徐",
    ]
    male_names = [
        "志豪", "冠廷", "建宏", "俊傑", "柏翰", "承恩", "宇軒", "智偉", "偉誠", "嘉豪",
        "明哲", "政廷", "宗翰", "家豪", "育誠", "信宏", "文傑", "冠宇", "彥廷", "柏宇",
        "育廷", "建銘", "志銘", "俊宏", "承翰", "宇翔", "奕辰", "恩碩", "宥廷", "冠儒",
        "致遠", "子軒", "家瑋", "柏鈞", "建勳", "俊良", "志強", "明憲", "宗慶", "育維",
        "佳賢", "品睿", "奕勳", "冠穎", "聖傑", "建宇", "威廷", "彥成", "宥翔", "柏叡",
    ]
    female_names = [
        "雅婷", "淑芬", "怡君", "美玲", "淑娟", "佳穎", "惠珊", "靜怡", "婉婷", "欣怡",
        "詩涵", "采潔", "嘉玲", "美惠", "郁婷", "冠儀", "佩珊", "宜君", "雅惠", "淑媛",
        "怡婷", "惠君", "佳琳", "靜雅", "婉君", "欣瑜", "詩婷", "采薇", "嘉慧", "美雲",
        "郁涵", "冠伶", "佩君", "宜珊", "雅君", "淑玲", "怡珊", "惠玲", "佳蓉", "靜雯",
        "婉玲", "欣宜", "詩雅", "采琳", "嘉芬", "美華", "郁君", "冠潔", "佩伶", "宜芳",
    ]
    surname = random.choice(surnames)
    first   = random.choice(male_names if gender.lower() == "male" else female_names)
    return f"{surname}{first}"


def _random_birthdate() -> str:
    days_ago = random.randint(365 * 20, 365 * 80)
    return (datetime.now() - timedelta(days=days_ago)).strftime("%Y-%m-%d")


class MockFHIRPoller:
    """本地模擬 FHIR 輪詢器，每次 poll() 有 40% 機率發現 1-3 筆新案例。"""

    def __init__(self):
        self._seen_ids: set = set()

    def poll_suspected_conditions(self) -> list[dict]:
        if random.random() > 0.40:
            return []

        new_cases = []
        for _ in range(random.randint(1, 3)):
            pid     = f"patient-{uuid.uuid4().hex[:8]}"
            disease = random.choice(DISEASES)
            gender  = random.choice(GENDERS)
            county  = random.choices(TW_COUNTIES, weights=TW_COUNTY_WEIGHTS, k=1)[0]
            symptoms = random.sample(DISEASE_SYMPTOMS[disease], k=random.randint(2, 4))

            now_utc = datetime.now(timezone.utc)
            encounter_dt = now_utc - timedelta(hours=random.uniform(6, 72))
            report_delay = timedelta(hours=random.uniform(2, 24))
            report_dt = min(encounter_dt + report_delay, now_utc - timedelta(minutes=5))

            hospital = random_hospital(county)
            home     = random_home(county)

            new_cases.append({
                "patient": {
                    "id":               pid,
                    "name":             _random_tw_name(gender),
                    "birthDate":        _random_birthdate(),
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
                    "status":        random.choice(STATUSES),
                    "symptoms":      symptoms,
                    "encounter_date": encounter_dt.strftime("%Y-%m-%dT%H:%M:%SZ"),
                    "report_date":    report_dt.strftime("%Y-%m-%dT%H:%M:%SZ"),
                },
            })

        return new_cases


class RealFHIRPoller:
    """真實 HAPI FHIR Server 輪詢器"""

    def __init__(self, base_url: str):
        self.base_url = base_url.rstrip("/")
        self._last_poll: Optional[datetime] = None
        log.info("🔗 FHIR Server：%s", self.base_url)

    def _get(self, path: str, params: dict = None) -> Optional[dict]:
        try:
            resp = requests.get(
                f"{self.base_url}/{path}",
                params=params, timeout=10,
                headers={"Accept": "application/fhir+json"},
            )
            resp.raise_for_status()
            return resp.json()
        except requests.RequestException as e:
            log.warning("⚠️  FHIR 請求失敗：%s", e)
            return None

    def poll_suspected_conditions(self) -> list[dict]:
        now    = datetime.now(timezone.utc)
        since  = self._last_poll or (now - timedelta(minutes=5))
        self._last_poll = now

        bundle = self._get("Condition", params={
            "clinical-status": "suspected",
            "_lastUpdated": f"gt{since.strftime('%Y-%m-%dT%H:%M:%SZ')}",
            "_count": 20,
        })
        if not bundle or bundle.get("total", 0) == 0:
            return []

        results = []
        for entry in bundle.get("entry", []):
            cond       = entry.get("resource", {})
            subject_ref = cond.get("subject", {}).get("reference", "")
            patient_id  = subject_ref.split("/")[-1] if subject_ref else None
            if not patient_id:
                continue
            patient = self._get(f"Patient/{patient_id}")
            if not patient:
                continue

            coding       = (cond.get("code", {}).get("coding") or [{}])[0]
            disease_disp = coding.get("display", "Unknown")
            disease      = next((d for d in DISEASES if d.lower() in disease_disp.lower()), "COVID-19")
            address      = (patient.get("address") or [{}])[0]
            county       = address.get("district") or address.get("city") or "台北市"

            results.append({
                "patient": {
                    "id":       patient_id,
                    "name":     (patient.get("name") or [{}])[0].get("text", "未知"),
                    "birthDate": patient.get("birthDate", ""),
                    "gender":   patient.get("gender", "unknown"),
                    "county":   county,
                },
                "condition": {
                    "id":            cond.get("id", uuid.uuid4().hex[:8]),
                    "disease":       disease,
                    "status":        "suspected",
                    "symptoms":      [],
                    "encounter_date": cond.get("onsetDateTime", now.isoformat()),
                    "report_date":    now.isoformat(),
                },
            })

        return results


# ── 核心處理流程 ───────────────────────────────────────────────────────────────

def process_case(raw: dict, db_path: str = DB_PATH, output_dir: str = OUTPUT_DIR) -> dict:
    patient   = raw["patient"]
    condition = raw["condition"]

    patient_data = {
        "id":               patient["id"],
        "name":             patient["name"],
        "birthDate":        patient.get("birthDate", ""),
        "gender":           patient.get("gender", "unknown"),
        "disease":          condition["disease"],
        "county":           patient["county"],
        "status":           condition["status"],
        "encounter_date":   condition.get("encounter_date", ""),
        "report_date":      condition.get("report_date", condition.get("encounter_date", "")),
        "symptoms":         condition.get("symptoms", []),
        "hospital_name":    patient.get("hospital_name", ""),
        "hospital_address": patient.get("hospital_address", ""),
        "home_address":     patient.get("home_address", ""),
        "home_district":    patient.get("home_district", ""),
    }

    bundle    = generate_eicr(patient_data)
    eicr_path = save_eicr(bundle, output_dir=output_dir)

    case_record = {
        "id":               patient["id"],
        "patient_name":     patient["name"],
        "birthdate":        patient.get("birthDate", ""),
        "gender":           patient.get("gender", "unknown"),
        "disease":          condition["disease"],
        "county":           patient["county"],
        "status":           condition["status"],
        "report_date":      condition.get("report_date", condition.get("encounter_date", "")),
        "symptoms":         condition.get("symptoms", []),
        "eicr_path":        eicr_path,
        "bundle_id":        bundle["id"],
        "hospital_name":    patient.get("hospital_name", ""),
        "hospital_address": patient.get("hospital_address", ""),
        "hospital_lat":     patient.get("hospital_lat"),
        "hospital_lon":     patient.get("hospital_lon"),
        "home_address":     patient.get("home_address", ""),
        "home_lat":         patient.get("home_lat"),
        "home_lon":         patient.get("home_lon"),
    }

    inserted = insert_case(case_record, db_path=db_path)
    if inserted:
        log.info("📋 新案例 → %s | %s | %s | %s",
                 patient["name"], condition["disease"],
                 condition["status"], patient["county"])
    else:
        log.debug("↩️  重複案例，略過：%s", patient["id"])

    return case_record


def simulate_report_submission(bundle: dict) -> bool:
    log.info("📤 [模擬送出] eICR Bundle %s → 疾病管制署通報系統", bundle["id"][:8])
    return True


# ── 主迴圈 ────────────────────────────────────────────────────────────────────

def run_engine(
    db_path: str = DB_PATH,
    output_dir: str = OUTPUT_DIR,
    poll_interval: int = POLL_INTERVAL,
) -> None:
    init_db(db_path)
    os.makedirs(output_dir, exist_ok=True)

    if FHIR_SERVER_URL:
        poller = RealFHIRPoller(FHIR_SERVER_URL)
        mode   = f"真實 FHIR 模式 ({FHIR_SERVER_URL})"
    else:
        poller = MockFHIRPoller()
        mode   = "本地模擬模式"

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
    init_db()
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    poller = MockFHIRPoller()
    cases = []
    while not cases:
        cases = poller.poll_suspected_conditions()
    cases[0]["condition"]["disease"] = disease
    cases[0]["patient"]["county"]    = county
    return process_case(cases[0])


if __name__ == "__main__":
    run_engine()
