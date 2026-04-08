# 門市業績自動化分析系統 — 資料結構規格書

> 版本：v2.0 | 更新：2026-04  
> 目標：手動填寫每日時段業績 → 自動計算達成率 → 視覺化週報 → 未來接 ML 預測

---

## 專案架構總覽

```
Google Sheets（手動輸入）
    └── daily_raw_clean     ← 每筆時段原始資料（手key）
    └── target              ← 時段預期目標（Python 自動算）
    └── daily_summary       ← 每日達成率彙總（Python 自動算）
    └── weekly_summary      ← 每週彙總（Python 自動算）
    └── external_factors    ← 外部因子（Phase 2 預留）

Python 層
    └── update_all.py       ← 主要入口：一鍵跑完所有更新
    └── app.py              ← Streamlit Dashboard

（calculate_target.py / etl.py 已整合進 update_all.py，保留備用）
```

---

## 執行方式

```bash
# 每次填完新資料後執行一次
python update_all.py

# 啟動 Dashboard
streamlit run app.py
```

---

## Sheet 結構

### daily_raw_clean（主要手key來源）

| 欄位 | 格式 | 說明 |
|------|------|------|
| `Date` | `yyyy/mm/dd` | 日期 |
| `Weekday` | 文字 | 星期（公式自動帶） |
| `Week_num` | `W0x` | 週別（公式自動帶） |
| `Time` | `HH:MM` | 時段起始時間 |
| `order_counts` | 整數 | 訂單筆數 |
| `cups` | 整數 | 杯數 |
| `revenues` | 整數 | 營業額（TWD） |

**注意：** 未營業時段填 `0`，不要留空。

### target（時段預期目標）

由 `update_all.py` 自動計算寫回，**不要手動修改**。

| 欄位 | 說明 |
|------|------|
| `date` | 日期 |
| `week_num` | 週別 |
| `time` | 時段 |
| `target_cups` | 前兩週同星期同時段杯數均值 |
| `target_rev` | 前兩週同星期同時段營業額均值 |

**更新邏輯（upsert）：**
- 掃描 `daily_raw_clean` 所有日期 + 下週（若 raw 最新資料距今 ≤ 14 天）
- 用 `date + time` 為 key，新資料覆蓋舊資料，不清空歷史
- 只有 raw 實際出現的時段才寫入，不產生空列

### daily_summary

| 欄位 | 說明 |
|------|------|
| `date` | 日期 |
| `weekday` | 星期 |
| `week_num` | 週別 |
| `target_cups` | 當日預期杯數 |
| `target_rev` | 當日預期營業額 |
| `actual_cups` | 當日實際杯數 |
| `actual_rev` | 當日實際營業額 |
| `achieved_pct` | 達成率（actual_rev / target_rev × 100） |

### weekly_summary

| 欄位 | 說明 |
|------|------|
| `week_num` | 週別 |
| `actual_cups` | 週總杯數 |
| `actual_rev` | 週總營業額 |
| `avg_cups_per_hour` | 週平均每小時杯數 |
| `peak_hour` | 當週最高峰時段 |

### external_factors（Phase 2 預留）

| 欄位 | 說明 | 來源 |
|------|------|------|
| `date` | 日期 | — |
| `is_weekend` | 是否週末 | 公式 |
| `is_holiday` | 國定假日 | API |
| `is_long_weekend` | 連假 | 推導 |
| `weather` | 天氣 | OpenWeatherMap |
| `nearby_event` | 周邊活動 | 手動 |
| `school_holiday` | 學校假期 | 手動 |
| `special_day` | 情人節等商業節日 | 手動 |
| `note` | 其他觀察 | 手動 |

**現在就要開始填的欄位：`note`（每天一句話）**

---

## 檔案說明

| 檔案 | 說明 |
|------|------|
| `update_all.py` | 主要入口，整合 target 計算 + ETL，一鍵跑完 |
| `app.py` | Streamlit Dashboard（週報 + 日報兩頁籤） |
| `calculate_target.py` | 已整合進 update_all，保留備用 |
| `etl.py` | 已整合進 update_all，保留備用 |
| `service_account.json` | Google Service Account 金鑰（不上傳 GitHub） |
| `.gitignore` | 排除金鑰檔案 |
| `README.md` | 專案說明 |

---

## 已知問題與處理

| 問題 | 原因 | 處理方式 |
|------|------|---------|
| target 被清空 | 每次 clear 再寫 | 改為 upsert，讀舊資料合併後寫回 |
| 4月空資料自動生成 | 無條件加入下週日期 | raw 最新資料距今 > 14 天就不加下週 |
| 10:00/22:00 空列 | HOURS 寫死 range(10,23) | 改為從 raw 動態取實際時段 |
| gspread 空白 header 報錯 | get_all_records() 遇空欄 | 改用 get_all_values() 自行處理 |
| pyodbc 版本衝突 | 4.0.0-unsupported 格式錯 | 用 conda 新環境安裝 |

---

## 開發路線圖

```
Phase 1（完成）
├── Google Sheets 手動填寫 daily_raw_clean
├── update_all.py 自動算 target + ETL 寫回
├── Streamlit Dashboard（週報 + 日報）
└── GitHub repo

Phase 2（資料 > 8 週）
├── external_factors 串接放假 / 天氣 API
├── 加權係數修正：預估 = 前兩週均值 × 節日係數 × 天氣係數
└── 評估 MAPE 改善幅度

Phase 3（資料 > 3 個月）
├── Prophet / LightGBM 時序預測
├── baseline vs ML achieved% 對比欄位
└── 人力需求預測：預估杯數 ÷ 每人每小時產能

Phase 4（之後）
└── 自動週報推播（Email / Line Notify）
```
