"""
update_all.py  ─  一鍵更新所有資料
執行方式：python update_all.py

執行順序：
  1. calculate_target  → 算下週每時段目標（前兩週同星期同時段均值）寫回 target sheet
  2. etl               → 算 daily_summary + weekly_summary 寫回 Sheets
"""

import sys
import traceback
from datetime import datetime

# ── 共用設定（兩支腳本都吃這裡）────────────────────────
import os
from dotenv import load_dotenv

load_dotenv()
SPREADSHEET_ID = os.getenv("SPREADSHEET_ID")
SERVICE_ACCOUNT_FILE = os.getenv("SERVICE_ACCOUNT_FILE", "service_account.json")

# ────────────────────────────────────────────────────────


def run_step(name: str, func):
    print(f"\n{'─'*40}")
    print(f"  {name}")
    print(f"{'─'*40}")
    try:
        func()
        print(f"  ✓ 完成")
        return True
    except Exception:
        print(f"  ✗ 失敗：")
        traceback.print_exc()
        return False


# ════════════════════════════════════════════════════════
#  Step 1：calculate_target
# ════════════════════════════════════════════════════════
def step_calculate_target():
    import gspread
    import pandas as pd
    from google.oauth2.service_account import Credentials
    from datetime import timedelta

    SHEET_DAILY_RAW = "daily_raw_clean"
    SHEET_TARGET    = "target"
    HOURS = [f"{h:02d}:00" for h in range(10, 23)]

    scopes = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive",
    ]
    creds  = Credentials.from_service_account_file(SERVICE_ACCOUNT_FILE, scopes=scopes)
    sh     = gspread.authorize(creds).open_by_key(SPREADSHEET_ID)

    # 讀 daily_raw_clean
    values = sh.worksheet(SHEET_DAILY_RAW).get_all_values()
    df = pd.DataFrame(values[1:], columns=values[0])
    df = df.loc[:, df.columns.str.strip() != ""]
    df = df[df.iloc[:, 0].str.strip() != ""].reset_index(drop=True)
    df = df.rename(columns={
        "Date": "date", "Time": "time", "cups": "cups", "revenues": "revenue",
    })
    df["date"]    = pd.to_datetime(df["date"], format="mixed")
    df["cups"]    = pd.to_numeric(df["cups"],    errors="coerce").fillna(0)
    df["revenue"] = pd.to_numeric(df["revenue"], errors="coerce").fillna(0)
    df["time"]    = df["time"].apply(lambda v: f"{int(round(float(v)*24)):02d}:00" if isinstance(v, float) else str(v).strip())
    df["weekday_num"] = df["date"].dt.dayofweek

    # ── 核心修正：對 raw 裡每一天都算 target，不只算下週 ──
    # 找出 raw 裡所有日期，加上下週 7 天，全部都要有 target
    all_dates_in_raw = df["date"].dt.normalize().unique()
    today = pd.Timestamp.today().normalize()
    days_to_monday = (7 - today.dayofweek) % 7 or 7
    next_monday = today + timedelta(days=days_to_monday)
    next_week_dates = [next_monday + timedelta(days=i) for i in range(7)]

    # 合併：raw 裡有的日期 + 下週日期，去重排序
    # all_target_dates = sorted(set(
    #     [pd.Timestamp(d) for d in all_dates_in_raw] + next_week_dates
    # ))

     # 下週只在 raw 最新資料接近今天時才有意義
    # 若 raw 最新日期距今超過 14 天，代表還沒填資料，不加未來日期
    # max_raw_date = pd.Timestamp(max(all_dates_in_raw))
    max_raw_date = pd.Timestamp(pd.Series(all_dates_in_raw).max())
    include_next_week = (today - max_raw_date).days <= 14
    extra = next_week_dates if include_next_week else []
 
    all_target_dates = sorted(set(
        [pd.Timestamp(d) for d in all_dates_in_raw] + extra
    ))


    
    # 只用 raw 實際出現的時段（排除 10:00/22:00 等空時段）
    HOURS = sorted(df["time"].unique())

    # 對每個日期每個時段算前兩週同星期同時段均值
    rows = [["date", "week_num", "time", "target_cups", "target_rev"]]
    for day in all_target_dates:
        wnum = f"W{day.isocalendar()[1]:02d}"
        for hour in HOURS:
            mask = (
                df["date"].isin([day - timedelta(weeks=1), day - timedelta(weeks=2)]) &
                (df["weekday_num"] == day.dayofweek) &
                (df["time"] == hour)
            )
            sub = df[mask]
            if sub.empty:
                continue  # 沒有前兩週資料就不寫，不產生空列
            tc = round(sub["cups"].mean())
            tr = round(sub["revenue"].mean())
            rows.append([day.strftime("%Y/%m/%d"), wnum, hour, tc, tr])
            # tc = round(sub["cups"].mean())    if not sub.empty else ""
            # tr = round(sub["revenue"].mean()) if not sub.empty else ""
            # rows.append([day.strftime("%Y/%m/%d"), wnum, hour, tc, tr])

    # upsert：先讀現有 target，合併後整張重寫（保留舊資料，新資料覆蓋）
    ws = sh.worksheet(SHEET_TARGET)
    existing = ws.get_all_values()
    if len(existing) > 1:
        existing_df = pd.DataFrame(existing[1:], columns=existing[0])
        existing_df = existing_df[existing_df["date"].str.strip() != ""]
        # 把新算的轉成 DataFrame
        new_df = pd.DataFrame(rows[1:], columns=rows[0])
        new_df["date"] = new_df["date"].astype(str)
        existing_df["date"] = existing_df["date"].astype(str)
        # 以 date + time 為 key，新的覆蓋舊的
        merged = pd.concat([existing_df, new_df]).drop_duplicates(
            subset=["date", "time"], keep="last"
        ).sort_values(["date", "time"]).reset_index(drop=True)
        final_rows = [merged.columns.tolist()] + merged.values.tolist()
    else:
        final_rows = rows

    ws.clear()
    ws.update(final_rows, "A1")
    n = len(final_rows) - 1
    print(f"  target sheet：{n} 筆（含歷史 + 下週）")
    print(f"  涵蓋日期：{final_rows[1][0]} ～ {final_rows[-1][0]}")


# ════════════════════════════════════════════════════════
#  Step 2：etl
# ════════════════════════════════════════════════════════
def step_etl():
    import gspread
    import pandas as pd
    from google.oauth2.service_account import Credentials

    SHEET_RAW    = "daily_raw_clean"
    SHEET_DAILY  = "daily_summary"
    SHEET_WEEKLY = "weekly_summary"
    SHEET_TARGET = "target"

    scopes = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive",
    ]
    creds  = Credentials.from_service_account_file(SERVICE_ACCOUNT_FILE, scopes=scopes)
    sh     = gspread.authorize(creds).open_by_key(SPREADSHEET_ID)

    def read(name):
        values = sh.worksheet(name).get_all_values()
        if len(values) < 2:
            return pd.DataFrame()
        df = pd.DataFrame(values[1:], columns=values[0])
        df = df.loc[:, df.columns.str.strip() != ""]
        return df[df.iloc[:, 0].str.strip() != ""].reset_index(drop=True)

    def fix_time(v):
        if isinstance(v, float):
            return f"{int(round(v * 24)):02d}:00"
        return str(v).strip()

    # 讀原始資料
    raw = read(SHEET_RAW).rename(columns={
        "Date": "date", "Weekday": "weekday", "Week_num": "week_num",
        "Time": "time", "cups": "cups", "revenues": "revenue",
    })
    raw["date"]    = pd.to_datetime(raw["date"], format="mixed")
    raw["cups"]    = pd.to_numeric(raw["cups"],    errors="coerce").fillna(0).astype(int)
    raw["revenue"] = pd.to_numeric(raw["revenue"], errors="coerce").fillna(0).astype(int)
    raw["time"]    = raw["time"].apply(fix_time)

    # 讀 target
    tgt = read(SHEET_TARGET)
    if not tgt.empty:
        tgt["date"]        = pd.to_datetime(tgt["date"], format="mixed")
        tgt["target_cups"] = pd.to_numeric(tgt["target_cups"], errors="coerce").fillna(0)
        tgt["target_rev"]  = pd.to_numeric(tgt["target_rev"],  errors="coerce").fillna(0)
        tgt["time"]        = tgt["time"].apply(fix_time)

    # daily_summary
    actual = raw.groupby("date").agg(
        weekday=("weekday","first"), week_num=("week_num","first"),
        actual_cups=("cups","sum"), actual_rev=("revenue","sum"),
    ).reset_index()

    if not tgt.empty:
        tgt_day = tgt.groupby("date").agg(
            target_cups=("target_cups","sum"), target_rev=("target_rev","sum"),
        ).reset_index()
        daily = actual.merge(tgt_day, on="date", how="left")
    else:
        daily = actual.copy()
        daily["target_cups"] = 0
        daily["target_rev"]  = 0

    daily["target_cups"] = daily["target_cups"].fillna(0)
    daily["target_rev"]  = daily["target_rev"].fillna(0)
    daily["achieved_pct"] = daily.apply(
        lambda r: round(r["actual_rev"] / r["target_rev"] * 100, 1) if r["target_rev"] > 0 else "",
        axis=1,
    )
    daily = daily.sort_values("date")
    daily["date"] = daily["date"].dt.strftime("%Y/%m/%d")

    # weekly_summary
    base = raw.groupby("week_num").agg(
        actual_cups=("cups","sum"), actual_rev=("revenue","sum"),
    ).reset_index()
    slot_count = raw[raw["cups"] > 0].groupby("week_num").size().rename("slot_count")
    base = base.join(slot_count, on="week_num")
    base["avg_cups_per_hour"] = (base["actual_cups"] / base["slot_count"]).round(1).fillna(0)
    hourly = raw.groupby(["week_num","time"])["cups"].sum().reset_index()
    peak   = hourly.loc[hourly.groupby("week_num")["cups"].idxmax()][["week_num","time"]].rename(columns={"time":"peak_hour"})
    weekly = base.merge(peak, on="week_num", how="left").sort_values("week_num")

    # 寫回
    def write(name, df, cols):
        ws = sh.worksheet(name)
        ws.clear()
        rows = [cols] + [
            ["" if (v is None or (isinstance(v, float) and pd.isna(v))) else v for v in row]
            for row in df[cols].values.tolist()
        ]
        ws.update(rows, "A1")
        print(f"  {name}：{len(df)} 列")

    write(SHEET_DAILY,  daily,  ["date","weekday","week_num","target_cups","target_rev","actual_cups","actual_rev","achieved_pct"])
    write(SHEET_WEEKLY, weekly, ["week_num","actual_cups","actual_rev","avg_cups_per_hour","peak_hour"])

# ════════════════════════════════════════════════════════
#  Step 3：ML 預測 → 寫回 ml_predictions sheet
# ════════════════════════════════════════════════════════
def step_ml_predictions():
    import gspread
    import pandas as pd
    import numpy as np
    from google.oauth2.service_account import Credentials
    from sklearn.ensemble import RandomForestRegressor
    from sklearn.linear_model import LinearRegression
    from sklearn.metrics import mean_absolute_percentage_error
 
    SHEET_RAW     = "daily_raw_clean"
    SHEET_ML      = "ml_predictions"
    HOLIDAYS_LIST = [
        "2026/02/14","2026/02/16","2026/02/17","2026/02/18",
        "2026/02/19","2026/02/20","2026/02/21","2026/02/22",
    ]
 
    scopes = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive",
    ]
    creds  = Credentials.from_service_account_file(SERVICE_ACCOUNT_FILE, scopes=scopes)
    sh     = gspread.authorize(creds).open_by_key(SPREADSHEET_ID)
 
    # 讀 raw
    values = sh.worksheet(SHEET_RAW).get_all_values()
    df = pd.DataFrame(values[1:], columns=values[0])
    df = df.loc[:, df.columns.str.strip() != ""]
    df = df[df.iloc[:, 0].str.strip() != ""].reset_index(drop=True)
    df = df.rename(columns={"Date":"date","Time":"time","cups":"cups","revenues":"revenue","Week_num":"week_num"})
    df["date"]    = pd.to_datetime(df["date"], format="mixed")
    df["revenue"] = pd.to_numeric(df["revenue"], errors="coerce").fillna(0)
    df["hour"]    = df["time"].apply(lambda v: int(str(v).split(":")[0]) if ":" in str(v) else int(float(v)*24))
    df["weekday"]    = df["date"].dt.dayofweek
    df["is_weekend"] = (df["weekday"] >= 5).astype(int)
    df["is_holiday"] = df["date"].dt.strftime("%Y/%m/%d").isin(HOLIDAYS_LIST).astype(int)
    df = df[df["revenue"] > 0]
 
    weeks = sorted(df["week_num"].unique())
    if len(weeks) < 3:
        print("  ⚠️  資料不足 3 週，跳過 ML 計算")
        return
 
    # Train = 除最後一週，Test = 最後一週
    test_week = weeks[-1]
    train = df[df["week_num"] != test_week]
    test  = df[df["week_num"] == test_week].copy()
 
    features = ["weekday", "hour", "is_weekend", "is_holiday"]
    X_train, y_train = train[features], train["revenue"]
    X_test           = test[features]
 
    # Baseline：同 weekday 同 hour 均值
    baseline_preds = []
    for _, row in test.iterrows():
        mask = (train["weekday"] == row["weekday"]) & (train["hour"] == row["hour"])
        hist = train[mask]["revenue"]
        baseline_preds.append(hist.mean() if not hist.empty else y_train.mean())
 
    # Linear Regression
    lr = LinearRegression()
    lr.fit(X_train, y_train)
    lr_preds = lr.predict(X_test)
 
    # Random Forest
    rf = RandomForestRegressor(n_estimators=100, random_state=42)
    rf.fit(X_train, y_train)
    rf_preds = rf.predict(X_test)
 
    # MAPE
    y_test = test["revenue"]
    bl_mape = round(mean_absolute_percentage_error(y_test, baseline_preds) * 100, 1)
    lr_mape = round(mean_absolute_percentage_error(y_test, lr_preds) * 100, 1)
    rf_mape = round(mean_absolute_percentage_error(y_test, rf_preds) * 100, 1)
 
    # 組成寫回的 DataFrame
    test = test.copy()
    test["baseline_pred"] = [round(v) for v in baseline_preds]
    test["lr_pred"]       = [round(v) for v in lr_preds]
    test["rf_pred"]       = [round(v) for v in rf_preds]
    test["date_str"]      = test["date"].dt.strftime("%Y/%m/%d")
 
    # MAPE 摘要列
    summary_rows = [
        ["#MAPE", "baseline", "lr", "rf", "", "", "", ""],
        ["#MAPE_VALUE", bl_mape, lr_mape, rf_mape, "", "", "", ""],
    ]
 
    # 明細列
    cols = ["date_str", "week_num", "time", "revenue", "baseline_pred", "lr_pred", "rf_pred", "is_holiday"]
    detail_rows = test[cols].values.tolist()
    detail_rows = [[str(v) for v in row] for row in detail_rows]
 
    # 寫回
    ws = sh.worksheet(SHEET_ML)
    ws.clear()
    header = [["date","week_num","time","actual","baseline_pred","lr_pred","rf_pred","is_holiday"]]
    ws.update(header + summary_rows + detail_rows, "A1")
 
    print(f"  ml_predictions：{len(detail_rows)} 筆（測試週 {test_week}）")
    print(f"  MAPE → Baseline: {bl_mape}%  LR: {lr_mape}%  RF: {rf_mape}%")



# ════════════════════════════════════════════════════════
#  主程式
# ════════════════════════════════════════════════════════
def main():
    start = datetime.now()
    print(f"\n{'═'*40}")
    print(f"  update_all  {start.strftime('%Y-%m-%d %H:%M')}")
    print(f"{'═'*40}")

    results = [
        run_step("Step 1 / 3  Calculate target", step_calculate_target),
        run_step("Step 2 / 3  ETL → Sheets",     step_etl),
        run_step("Step 3 / 3  ML predictions",   step_ml_predictions),
    ]

    elapsed = (datetime.now() - start).seconds
    print(f"\n{'═'*40}")
    if all(results):
        print(f"  全部完成！耗時 {elapsed} 秒")
        print(f"  重開 Streamlit 或按「重新讀取資料」即可看到更新")
    else:
        print(f"  有步驟失敗，請查看上方錯誤訊息")
    print(f"{'═'*40}\n")
    sys.exit(0 if all(results) else 1)


if __name__ == "__main__":
    main()
