# Retail Sales Automation System

自動化門市業績 ETL 資料管線 + 互動式 Streamlit Dashboard + ML 預測模型比較

![Dashboard Demo](assets/Dashboard_demo.gif)

---

## 專案背景

門市每日業績需人工手填、缺乏結構化分析。本專案自主設計端對端自動化系統：

- 結構化存放每日時段業績（Google Sheets）
- 自動計算達成率、時段目標（Python ETL）
- 互動式視覺化週報 + 日報（Streamlit）
- Walk-Forward Validation 比較三個預測模型準確度

---

## ML 模型比較結果

使用 **Walk-Forward Validation**（每週用前面所有週訓練，預測下一週，避免 data leakage）

| 模型 | 平均 MAPE | 說明 |
|------|-----------|------|
| Baseline（前兩週均值） | 76.8% | 現行預測方式 |
| Linear Regression | 106.0% | 線性關係無法捕捉時段非線性 |
| **Random Forest** | **60.6%** | 最佳，捕捉時段 × 節日交互效應 |

**Random Forest 比 Baseline 改善 16.2% MAPE**

特徵重要度：`hour`（45%）> `is_holiday`（29%）> `weekday`（18%）> `is_weekend`（7%）

> 資料持續累積中，預計 Phase 2 加入天氣 / 周邊活動因子後進一步降低 MAPE
> 預留考慮節日、天氣、周邊活動等外部因子模組與優化 ML 預測架構，供後續迭代（套用不同分店預測）

---

## 技術棧

- **ETL**：Python、Pandas、gspread
- **視覺化**：Streamlit、Plotly
- **ML**：scikit-learn（LinearRegression、RandomForestRegressor）
- **資料來源**：Google Sheets API
- **驗證方法**：Walk-Forward Validation
- **預測（Phase 2）**：節日 / 天氣係數修正
- **預測（Phase 3）**：Prophet / LightGBM

---

## 專案結構

```
├── app.py                  # Streamlit Dashboard（週報 + 日報 + ML 比較）
├── update_all.py           # 一鍵更新：target + ETL + ML 預測寫回 Sheets
├── ml_forecast.py          # 獨立 ML 分析腳本
├── assets/
│   └── Dashboard_demo.gif
├── docs/
│   ├── sales_project_spec.md
│   └── dev_log.md
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
4. 建立 `.env` 填入 `SPREADSHEET_ID`

```
SPREADSHEET_ID=你的_Sheet_ID
SERVICE_ACCOUNT_FILE=service_account.json
```

### 3. 更新資料

```bash
# 每次填完 daily_raw_clean 後執行
# 自動完成：target 計算 → ETL 彙總 → ML 預測，共 3 步驟
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
| `ml_predictions` | 三模型預測結果 + MAPE | `update_all.py` 自動 |
| `external_factors` | 節日 / 天氣外部因子（Phase 2 預留） | 手動 / API |

---

## 開發路線圖

- [x] Phase 1：ETL 資料管線 + Streamlit Dashboard + upsert target 機制
- [x] Phase 2a：ML 模型比較（Baseline / LR / RF）+ Walk-Forward Validation
- [ ] Phase 2b：節日 / 天氣係數修正（hybrid 預測模型）
- [ ] Phase 3：Prophet / LightGBM 時序預測，量化 MAPE 改善幅度
- [ ] Phase 4：自動週報推播（Line Notify / Email）

---

## 注意事項

- `service_account.json` 和 `.env` 已加入 `.gitignore`，請勿上傳
- 資料為匿名處理，不含個人識別資訊
