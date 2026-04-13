# Retail Sales Automation System

自動化門市業績 ETL 資料管線 + 互動式 Streamlit Dashboard，架構預留 ML 預測模組。

![Dashboard Demo](assets/Dashboard_demo.gif)

---

## 專案背景

門市每日業績需人工手填、缺乏結構化分析。本專案自主設計端對端自動化系統：

- 結構化存放每日時段業績（Google Sheets）
- 自動計算達成率、時段目標（Python ETL）
- 互動式視覺化週報 + 日報（Streamlit）
- 架構預留 Phase 2/3 ML 預測模組

---

## Demo

| 每週總覽 | 每日時段 |
|---------|---------|
| 週別切換、KPI 卡、實際 vs 目標、熱力圖 | 時段營業額（實線）& 杯數（虛線）雙軸圖 |

---

## 技術棧

- **ETL**：Python、Pandas、gspread
- **視覺化**：Streamlit、Plotly
- **資料來源**：Google Sheets API
- **預測（Phase 2）**：節日 / 天氣係數修正
- **預測（Phase 3）**：Prophet / LightGBM

---

## 專案結構

```
├── app.py                  # Streamlit Dashboard（週報 + 日報）
├── update_all.py           # 一鍵更新：算 target + ETL 寫回 Sheets
├── assets/
│   └── Dashboard_demo.gif  # Demo 動圖
├── docs/
│   ├── sales_project_spec.md  # 資料結構規格書
│   └── dev_log.md             # 開發日誌
├── requirements.txt
└── .gitignore
```

---

## 快速開始

### 1. 安裝環境

```bash
conda create -n sales_dashboard python=3.10 -y
conda activate sales_dashboard
pip install -r requirements.txt
```

### 2. 設定 Google Sheets

1. 建立 Google Cloud 專案，啟用 Sheets API + Drive API
2. 建立 Service Account，下載金鑰存為 `service_account.json`（**不要上傳 GitHub**）
3. 將 Service Account email 加入 Google Sheet 編輯權限
4. 在 `update_all.py` 和 `app.py` 填入你的 `SPREADSHEET_ID`

### 3. 更新資料

```bash
# 每次填完 daily_raw_clean 後執行
python update_all.py
```

### 4. 啟動 Dashboard

```bash
streamlit run app.py
```

---

## Google Sheets 資料結構

| Sheet | 說明 | 更新方式 |
|-------|------|---------|
| `daily_raw_clean` | 每日時段原始資料 | 每天手動填寫 |
| `target` | 時段預期目標（前兩週均值，upsert） | `update_all.py` 自動 |
| `daily_summary` | 每日達成率彙總 | `update_all.py` 自動 |
| `weekly_summary` | 每週彙總 + 高峰時段 | `update_all.py` 自動 |
| `external_factors` | 節日 / 天氣外部因子（Phase 2 預留） | 手動 / API |

---

## 開發路線圖

- [x] Phase 1：ETL 資料管線 + Streamlit Dashboard + upsert target 機制
- [ ] Phase 2：節日 / 天氣係數修正（hybrid 預測模型）
- [ ] Phase 3：Prophet / LightGBM 時序預測，量化 MAPE 改善幅度
- [ ] Phase 4：自動週報推播（Line Notify / Email）

---

## 注意事項

- `service_account.json` 已加入 `.gitignore`，請勿上傳
- 資料為匿名處理，不含個人識別資訊
