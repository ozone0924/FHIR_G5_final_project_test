# 專案版本功能比較

> 三個版本：**原始專案**（first commit）、**我的專案**（現行版本）、**dashboard_blue.py**（組員另行開發）

---

## 一、我的專案 vs. 原始專案：新增了哪些功能

原始專案（`69bcf60e`）的 `dashboard.py` 僅有 477 行，透過 Sidebar 操作，無 Tab 頁籤。以下是本次開發過程中逐步新增的功能：

### Dashboard 架構重構

| 項目 | 原始 | 現行 |
|------|------|------|
| 頁面結構 | Sidebar 篩選 + 單頁捲動 | 7 個 Tab 頁籤 |
| 疾病 / 狀態篩選 | Sidebar selectbox | 各頁籤各自的 checkbox / datepicker |
| 天數範圍控制 | Sidebar slider（僅趨勢圖用） | 各頁籤頂部 slider，跨頁籤同步 |
| 程式碼行數 | ~477 行 | ~1,600 行 |

### 地理分布（Tab 1）

- 新增 **3 種地圖模式**（segmented control 切換）
  - 縣市累積泡泡圖（含堆疊橫條）
  - **通報院所熱點**（44 家台灣醫院實際座標）
  - **病患居住地時間擴散圖**（顏色深淺代表新舊、每疾病獨立正規化）
- 泡泡大小 **sqrt 正規化**（防止大量資料時泡泡爆版）
- 疾病 checkbox 預設全不勾選，方便單一疾病篩選

### 案例明細 & 通報單（Tab 3）

- 篩選改為 **日期區間 datepicker**（原為固定天數 slider）
- **顯示更多 / 顯示全部** 分頁按鈕（原為固定 50 筆）
- **eICR 通報單查閱**：點選右側彈出 FHIR R4 格式完整通報單
- **PDF 下載**：繁體中文 PDF 通報單（Noto Sans TC 字型）
- **JSON 下載**：原始 eICR Bundle JSON

### 人口統計（Tab 4）

- 年齡分布 **Box Plot**（各疾病）
- **主訴症狀 Top 12**（依疾病分色堆疊橫條）
- 性別分布長條圖
- 疾病確診率統計表

### 通報追蹤（Tab 5）—— Phase B

- **NSSP 送出模擬**：每筆案例偵測後立即建立 `pending` submission
- **非同步更新**：10–100 秒後模擬 NSSP 回應（90% accepted）
- **自動重試**：失敗最多重試 3 次，超過標記為 `failed`
- 合併冗餘的「狀態」+「Task 狀態」→ 單一「通報狀態」欄
- KPI 卡片：累計送出 / Accepted / Error / Pending 即時計數

### 架構說明（Tab 7）

- G1→G5 整體 Pipeline HTML 流程圖
- **MedMorph 完整通報序列圖**（Phase A / B / C 標注）

### 後端 `medmorph_engine.py`

- `create_submission(live=True)` 即時模式 vs `live=False` seed 模式
- `process_pending_submissions()` —— 背景 NSSP worker
- SQLite migrations：`next_check_at`、`retry_count` 欄位

### `seed_data.py`

- **6 波疫情爆發模型**（flu_winter / covid_wave1 / dengue_south1 / covid_wave2 / flu_spring / dengue_south2）
- 高斯流行曲線 + 縣市延遲擴散（呼吸道按人口加權、病媒蚊按地理鄰近）
- `--count` 精確保證筆數（top-up 補齊 loop）
- 44 家醫院 + 全台 22 縣市區域座標

---

## 二、我的專案 vs. dashboard_blue.py：我多了哪些功能

以下是我的 `dashboard.py` 有、但 `dashboard_blue.py` **沒有**的功能：

| 功能 | 我的 dashboard.py | dashboard_blue.py |
|------|:-----------------:|:-----------------:|
| NSSP Phase B 通報追蹤 | ✅ | ❌ |
| eICR 通報單查閱 | ✅ | ❌ |
| PDF / JSON 下載 | ✅ | ❌ |
| 通報院所熱點地圖 | ✅ | ❌ |
| 病患居住地時間擴散地圖 | ✅ | ❌ |
| 年齡分布 Box Plot | ✅ | ❌ |
| 主訴症狀分析（依疾病分色）| ✅ | ❌ |
| MedMorph 架構 / 序列圖 | ✅ | ❌ |
| 跨頁籤同步天數 slider | ✅ | ❌ |
| 案例明細日期區間 picker | ✅ | ❌ |
| 中文 UI | ✅ | ❌（英文）|
| 顯示更多 / 全部分頁 | ✅ | ❌ |

---

## 三、dashboard_blue.py vs. 原始專案：組員新增了哪些功能

組員在原始專案基礎上開發的新功能（不包含本次 Session 的改動）：

### 設計系統

- **Morandi 深藍主題**：完整 CSS design token（`THEME_PALETTES` Light / Dark 兩套）
- DM Sans + DM Mono 字型（Google Fonts）
- 頂部 topbar + 閃爍 LIVE 徽章 + 時間戳
- KPI 卡片帶彩色頂線（covid / dengue / flu 各自顏色）
- `.panel` 容器統一樣式，視覺更整齊

### 新圖表（原始沒有）

| 圖表 | 說明 |
|------|------|
| **Disease Distribution donut** | 三種疾病佔比甜甜圈圖 |
| **Case Status donut** | 疑似 vs 確診佔比甜甜圈圖 |
| **7-Day Moving Average** | 7 日滾動平均趨勢線（單獨一圖）|
| **Weekly Stacked Bar** | 近 8 週每週堆疊長條圖 |
| **Area fill on trend lines** | 折線下方半透明填色 |

### 互動體驗

- 地圖旁加入 **縣市排名側欄**（進度條 + 數字）
- 案例明細可調 **顯示筆數 slider**（10–200 筆）
- 縣市名稱顯示**英文**（COUNTY_NAME_EN 對照表）
- 地圖疾病篩選改為 **radio button**（All / 三種疾病）
- **Status 欄彩色**：Confirmed 磚紅、Suspected 琥珀

---

## 四、整合建議

以下是 `dashboard_blue.py` 的功能可以移植到我的 `dashboard.py` 後，能帶來的提升：

### 高價值整合（視覺 + 資訊量大幅提升）

**1. Disease + Status 雙甜甜圈圖**
- 放在趨勢分析 Tab 或概覽區塊
- 讓使用者一眼看到疾病佔比 & 疑似 vs 確診比率
- 原始程式碼可直接搬移（`fig_donut` / `fig_status_donut`）

**2. 7 日滾動平均線**
- 加在趨勢分析 Tab 的折線圖下方
- 消除每日波動雜訊，讓疫情走勢更清晰
- 原始程式碼可直接搬移（`fig_ma7`）

**3. 每週堆疊長條圖**
- 加在趨勢分析 Tab，補充週尺度視角
- 原始程式碼可直接搬移（`fig_weekly`）

**4. 縣市排名側欄**
- 地圖模式「縣市累積分布」右側改放排名清單（現在是橫條圖）
- 更直覺、空間利用更好

### 中等價值整合（體驗改善）

**5. 頂部 Topbar 設計**
- 替換現有的簡易標題列
- 閃爍 LIVE 點 + 時間戳更有監控系統的專業感

**6. KPI 卡片帶彩色頂線**
- 現有 KPI 卡片是漸層背景
- 改為白底 + 彩色 2px 頂線（Morandi 配色）更簡潔有質感

**7. 折線圖面積填充**
- 在趨勢折線下加半透明填色（`fill="tozeroy"`）
- 視覺上更能突顯爆發期

**8. 案例明細篩選 + 行數控制**
- 現有用 datepicker + 顯示更多按鈕
- 可額外加「每頁顯示 N 筆」slider，兩種篩選方式並存

### 低優先（保留即可）

**9. 英文縣市名稱**
- 目前中文 UI 對學術報告已足夠
- 若有國際展示需求可切換

**10. Dark Mode**
- `THEME_PALETTES` 結構設計良好，可整合到設定 Tab 的切換選項
- 目前使用情境以報告展示為主，Light 即可

---

## 五、總結對照表

| 功能面向 | 原始專案 | 我的專案 | dashboard_blue.py |
|----------|:--------:|:--------:|:-----------------:|
| 頁面數 | 1（sidebar）| 7 tabs | 4 tabs |
| 地圖種類 | 1（縣市泡泡）| 3 | 1 |
| 疫情分析圖 | 折線圖 | 折線 + 症狀 + 年齡 | 折線 + MA7 + 週分佈 |
| 摘要圖表 | 橫條圖 | 橫條圖 | 甜甜圈 × 2 + 橫條 |
| Phase B 通報追蹤 | ❌ | ✅（pending / retry）| ❌ |
| eICR 查閱 / PDF | ❌ | ✅ | ❌ |
| 設計系統 | 無 | 基本 | Morandi 深藍（完整）|
| 語言 | 中文 | 中文 | 英文 |
| 醫院地理資料 | ❌ | ✅（44 家）| ❌ |
| 爆發模型 | 簡易 | 6 波高斯擴散 | 沿用原始 |
| NSSP 模擬 | ❌ | ✅ | ❌ |
