"""
ml_forecast.py  ─  業績預測模型比較
比較三個模型的 MAPE：Baseline / Linear Regression / Random Forest
用法：python ml_forecast.py
"""

import os
import gspread
import pandas as pd
import numpy as np
from dotenv import load_dotenv
from google.oauth2.service_account import Credentials
from sklearn.linear_model import LinearRegression
from sklearn.ensemble import RandomForestRegressor
from sklearn.metrics import mean_absolute_percentage_error

load_dotenv()
SPREADSHEET_ID       = os.getenv("SPREADSHEET_ID")
SERVICE_ACCOUNT_FILE = os.getenv("SERVICE_ACCOUNT_FILE", "service_account.json")

HOLIDAYS = [
    "2026/02/14",                                           # 情人節
    "2026/02/16","2026/02/17","2026/02/18","2026/02/19",   # 春節連假
    "2026/02/20","2026/02/21","2026/02/22","2026/02/28",  #和平紀念日
    "2026/04/03","2026/04/04","2026/04/05" ,"2026/04/06" #清明兒童節連假
]


def load_data() -> pd.DataFrame:
    scopes = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive",
    ]
    creds  = Credentials.from_service_account_file(SERVICE_ACCOUNT_FILE, scopes=scopes)
    sh     = gspread.authorize(creds).open_by_key(SPREADSHEET_ID)
    values = sh.worksheet("daily_raw_clean").get_all_values()
    df = pd.DataFrame(values[1:], columns=values[0])
    df = df.loc[:, df.columns.str.strip() != ""]
    df = df[df.iloc[:, 0].str.strip() != ""].reset_index(drop=True)
    df = df.rename(columns={"Date":"date","Time":"time","cups":"cups","revenues":"revenue","Week_num":"week_num"})
    df["date"]    = pd.to_datetime(df["date"], format="mixed")
    df["revenue"] = pd.to_numeric(df["revenue"], errors="coerce").fillna(0)
    df["cups"]    = pd.to_numeric(df["cups"],    errors="coerce").fillna(0)
    df["hour"]    = df["time"].apply(lambda v: int(str(v).split(":")[0]) if ":" in str(v) else int(float(v)*24))
    return df


def build_features(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df["weekday"]    = df["date"].dt.dayofweek
    df["is_weekend"] = (df["weekday"] >= 5).astype(int)
    df["is_holiday"] = df["date"].dt.strftime("%Y/%m/%d").isin(HOLIDAYS).astype(int)
 
    # 標記缺失天：某週某星期筆數 < 5 視為資料不完整
    slot_count = df.groupby(["week_num", "weekday"])["revenue"].transform("count")
    df["is_incomplete_day"] = (slot_count < 5).astype(int)
 
    return df[df["revenue"] > 0]


def baseline_predict(train: pd.DataFrame, test: pd.DataFrame) -> list:
    """前兩週同 weekday 同 hour 均值"""
    preds = []
    for _, row in test.iterrows():
        mask = (train["weekday"] == row["weekday"]) & (train["hour"] == row["hour"])
        hist = train[mask]["revenue"]
        preds.append(hist.mean() if not hist.empty else train["revenue"].mean())
    return preds


def run():
    print("\n── ML 模型比較 ────────────────────────────")
    print("讀取 Google Sheets...")
    df = load_data()
    df = build_features(df)

    weeks = sorted(df["week_num"].unique())
    print(f"資料：{len(df)} 筆，{df['date'].nunique()} 天，{len(weeks)} 週（{weeks[0]}～{weeks[-1]}）")

    # 最後一週當測試集，其餘訓練
    test_week  = weeks[-1]
    train_week = weeks[:-1]
    train = df[df["week_num"].isin(train_week)]
    test  = df[df["week_num"] == test_week]

    if len(test) < 10:
        print(f"⚠️  測試集（{test_week}）只有 {len(test)} 筆，結果僅供參考")

    features = ["weekday", "hour", "is_weekend", "is_holiday", "is_incomplete_day"]
    X_train, y_train = train[features], train["revenue"]
    X_test,  y_test  = test[features],  test["revenue"]

    # Baseline
    bl_preds   = baseline_predict(train, test)
    bl_mape    = mean_absolute_percentage_error(y_test, bl_preds) * 100

    # Linear Regression
    lr = LinearRegression()
    lr.fit(X_train, y_train)
    lr_mape = mean_absolute_percentage_error(y_test, lr.predict(X_test)) * 100

    # Random Forest
    rf = RandomForestRegressor(n_estimators=100, random_state=42)
    rf.fit(X_train, y_train)
    rf_preds = rf.predict(X_test)
    rf_mape  = mean_absolute_percentage_error(y_test, rf_preds) * 100

    # Random Forest（平日 / 週末分開訓練）
    def train_split_rf(train, test, features):
        preds = pd.Series(index=test.index, dtype=float)
        # 先用全體訓練一個 fallback 模型
        fallback = RandomForestRegressor(n_estimators=100, random_state=42)
        fallback.fit(train[features], train["revenue"])
 
        for is_wknd in [0, 1]:
            tr = train[train["is_weekend"] == is_wknd]
            te = test[test["is_weekend"]   == is_wknd]
            if len(te) == 0:
                continue          # 測試集這組沒資料，跳過
            if len(tr) < 5:
                # 訓練資料不足，用 fallback
                preds[te.index] = fallback.predict(te[features])
            else:
                m = RandomForestRegressor(n_estimators=100, random_state=42)
                m.fit(tr[features], tr["revenue"])
                preds[te.index] = m.predict(te[features])
        return preds

        # for is_wknd in [0, 1]:
        #     tr = train[train["is_weekend"] == is_wknd]
        #     te = test[test["is_weekend"]   == is_wknd]
        #     if len(tr) < 5 or len(te) == 0:
        #         # 資料太少就 fallback 用全體模型
        #         m = RandomForestRegressor(n_estimators=100, random_state=42)
        #         m.fit(train[features], train["revenue"])
        #         preds[te.index] = m.predict(te[features])
        #     else:
        #         m = RandomForestRegressor(n_estimators=100, random_state=42)
        #         m.fit(tr[features], tr["revenue"])
        #         preds[te.index] = m.predict(te[features])
        # return preds
 
    rf_split_preds = train_split_rf(train, test, features)
    rf_split_mape  = mean_absolute_percentage_error(y_test, rf_split_preds) * 100

    # Feature Importance（用全體 RF）
    fi = pd.Series(rf.feature_importances_, index=features).sort_values(ascending=False)


    # 結果
    improvement_rf       = bl_mape - rf_mape
    improvement_rf_split = bl_mape - rf_split_mape
    best = min(bl_mape, lr_mape, rf_mape, rf_split_mape)
 
    print(f"\n{'='*50}")
    print(f"  測試週：{test_week}")
    print(f"{'='*50}")
    print(f"  Baseline（前兩週均值）      MAPE: {bl_mape:.1f}%")
    print(f"  Linear Regression           MAPE: {lr_mape:.1f}%")
    print(f"  Random Forest               MAPE: {rf_mape:.1f}%  (改善 {improvement_rf:.1f}%)")
    print(f"  Random Forest 平日/週末分開  MAPE: {rf_split_mape:.1f}%  (改善 {improvement_rf_split:.1f}%)")
    print(f"{'='*50}")
    print(f"  最佳模型 MAPE: {best:.1f}%")
 
    print(f"\n  Random Forest 特徵重要度：")
    for feat, imp in fi.items():
        bar = "█" * int(imp * 30)
        print(f"  {feat:<22} {bar} {imp:.3f}")
 

    print(f"\n  ⚠️  資料量建議：目前 {len(weeks)} 週，建議 8+ 週後結果更可靠")
    print("── 完成 ────────────────────────────────────\n")

    return {
        "baseline_mape":    round(bl_mape, 1),
        "lr_mape":          round(lr_mape, 1),
        "rf_mape":          round(rf_mape, 1),
        "rf_split_mape":    round(rf_split_mape, 1),
        "improvement_rf":   round(improvement_rf, 1),
        "improvement_split":round(improvement_rf_split, 1),
        "feature_importance": fi.to_dict(),
    }


if __name__ == "__main__":
    run()
