# 第五組：傳染病自動通報與公衛儀表板系統

> **NTU 智慧醫療期末專題** — FHIR-based 傳染病監測 Pipeline  
> 負責範圍：MedMorph 自動通報引擎 + HL7 eICR 產生 + Streamlit 即時儀表板

---

## 系統架構

```
病患對話（第1組）
    → FHIR 資料庫（第2組）
        → CQL 決策引擎（第3組）
            → 群聚分析（第4組）
                → 【本組】自動通報 + 公衛儀表板
```

---

## 檔案說明

| 檔案 | 說明 |
|------|------|
| `eicr_generator.py` | **程式 B**：產生 HL7 eICR 格式的 FHIR R4 Bundle JSON |
| `medmorph_engine.py` | **程式 A**：MedMorph 引擎，輪詢 FHIR server，偵測疑似病例並寫入資料庫 |
| `dashboard.py` | **程式 C**：Streamlit 即時公衛儀表板 |
| `seed_data.py` | 注入假資料（demo 用），產生 SQLite 資料庫與 eICR JSON |
| `run_all.py` | 一鍵啟動腳本 |
| `requirements.txt` | Python 套件清單 |

---

## 安裝與執行

### 前置需求

- Python 3.10 以上
- Git

> ⚠️ **請使用從 [python.org](https://www.python.org/downloads/) 安裝的 Python**，避免使用 MSYS2、Homebrew 等環境管理器的 Python，以免套件安裝失敗。

---

### Step 1：Clone 專案

```bash
git clone https://github.com/Saltenfish-cosine/FHIR_G5_final_project_test.git
cd FHIR_G5_final_project_test
```

---

### Step 2：建立虛擬環境

**Windows（PowerShell）**
```powershell
python -m venv venv
venv\Scripts\activate
```

**Mac / Linux**
```bash
python3 -m venv venv
source venv/bin/activate
```

成功後終端機最前面會出現 `(venv)`。

---

### Step 3：安裝套件

```bash
pip install -r requirements.txt
```

---

### Step 4：注入假資料

```bash
python seed_data.py
```

執行後會自動建立 `data/cases.db` 和 `output/` 資料夾，並印出案例分布統計。

---

### Step 5：啟動儀表板

```bash
streamlit run dashboard.py
```

瀏覽器會自動開啟 `http://localhost:8501`。

按 `Ctrl + C` 停止。

---

### Step 6（選做）：同時啟動 MedMorph 引擎

另開一個終端，同樣先啟動虛擬環境後執行：

**Windows**
```powershell
venv\Scripts\activate
python medmorph_engine.py
```

**Mac / Linux**
```bash
source venv/bin/activate
python medmorph_engine.py
```

引擎每 10 秒隨機產生新案例，儀表板每 15 秒自動刷新，數字會即時更新。

---

### 一鍵啟動（選做）

以上步驟也可以用 `run_all.py` 一次完成：

**Windows**
```powershell
python run_all.py
```

**Mac / Linux**
```bash
python3 run_all.py
```

---

## 連接真實 FHIR Server（對接第二組）

預設為本地模擬模式。若要連接第二組的 HAPI FHIR Server，設定環境變數後執行：

**Windows**
```powershell
$env:FHIR_SERVER_URL="http://localhost:8080/fhir"
python medmorph_engine.py
```

**Mac / Linux**
```bash
FHIR_SERVER_URL=http://localhost:8080/fhir python3 medmorph_engine.py
```

---

## 儀表板功能

| 功能 | 說明 |
|------|------|
| 📊 KPI 卡片 | COVID-19 / 登革熱 / 流感 各疾病即時計數（含今日新增） |
| 🗺️ 台灣地圖 | Plotly 各縣市泡泡熱力圖，泡泡大小代表案例數 |
| 📈 趨勢折線圖 | 近 14 天每日新增案例（可調整天數） |
| 📋 案例明細表 | 最近 50 筆案例清單，可依疾病 / 狀態篩選 |
| ⏱ 自動刷新 | 每 15 秒自動更新資料 |

---

## eICR 輸出格式

每筆案例會在 `output/` 資料夾產生一個 FHIR R4 Document Bundle JSON，包含：

```
Bundle (type: document)
├── Composition    — eICR 主文件頭
├── Patient        — 病患基本資料
├── Condition      — 診斷（含 SNOMED-CT 代碼）
├── Observation    — 檢驗觀察（含 LOINC 代碼）
├── Encounter      — 就診紀錄
└── Organization   — 通報機構（疾管署）
```

---

## 常見問題

**Q：`streamlit: command not found`**  
A：確認虛擬環境已啟動（終端機前有 `(venv)`），再重新執行。

**Q：Mac 上 `python` 找不到**  
A：改用 `python3`。

**Q：儀表板顯示「目前沒有符合條件的案例」**  
A：先執行 `python seed_data.py` 注入資料。

**Q：Port 8501 已被佔用**  
A：改用其他 port：`streamlit run dashboard.py --server.port 8502`

---

## 使用標準

| 項目 | 內容 |
|------|------|
| 通報標準 | HL7 eICR（Electronic Initial Case Report） |
| 資料交換框架 | MedMorph Reference Architecture |
| FHIR 版本 | FHIR R4 |
| 儀表板工具 | Streamlit |
| 程式語言 | Python 3.10+ |
