"""
etl.py  ─  一次計算所有彙總，寫回 Google Sheets
執行順序：
  1. 讀 daily_raw + target
  2. 算 daily_summary（target + actual + achieved%）
  3. 算 weekly_summary（補 avg_cups_per_hour + peak_hour）
  4. 全部寫回對應 sheet

每次有新資料填進 daily_raw 後，跑一次這支腳本就好。
"""

import gspread
import pandas as pd
from google.oauth2.service_account import Credentials

# ── 設定區（只改這裡）────────────────────────────────────
import os
from dotenv import load_dotenv

load_dotenv()
SPREADSHEET_ID = os.getenv("SPREADSHEET_ID")
SERVICE_ACCOUNT_FILE = os.getenv("SERVICE_ACCOUNT_FILE", "service_account.json")


SHEET_RAW    = "daily_raw_clean"
SHEET_DAILY  = "daily_summary"
SHEET_WEEKLY = "weekly_summary"
SHEET_TARGET = "target"
# ────────────────────────────────────────────────────────


def connect():
    scopes = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive",
    ]
    creds = Credentials.from_service_account_file(SERVICE_ACCOUNT_FILE, scopes=scopes)
    return gspread.authorize(creds).open_by_key(SPREADSHEET_ID)


def fix_time(v):
    """Google Sheets 時間欄有時是浮點數，統一轉成 HH:MM 字串"""
    if isinstance(v, float):
        return f"{int(round(v * 24)):02d}:00"
    return str(v).strip()


def read_sheet(sh, sheet_name: str) -> pd.DataFrame:
    """
    用 get_all_values() 讀取，避免 get_all_records() 遇到空白 header 報錯。
    自動移除空白欄位和空白列。
    """
    values = sh.worksheet(sheet_name).get_all_values()
    if len(values) < 2:
        return pd.DataFrame()
    headers = values[0]
    df = pd.DataFrame(values[1:], columns=headers)
    df = df.loc[:, df.columns.str.strip() != ""]   # 移除空白欄名
    df = df[df.iloc[:, 0].str.strip() != ""]       # 移除第一欄是空的列
    df = df.reset_index(drop=True)
    return df

def load_raw(sh) -> pd.DataFrame:
    df = read_sheet(sh, SHEET_RAW)
    if df.empty:
        raise ValueError("daily_raw 是空的，請先填入資料")
 
    df = df.rename(columns={
        "Date": "date", "Weekday": "weekday", "Week_num": "week_num",
        "Time": "time", "order_counts": "order_counts",
        "cups": "cups", "revenues": "revenue",
    })
    df["date"]    = pd.to_datetime(df["date"], format="mixed")
    df["cups"]    = pd.to_numeric(df["cups"],    errors="coerce").fillna(0).astype(int)
    df["revenue"] = pd.to_numeric(df["revenue"], errors="coerce").fillna(0).astype(int)
    df["time"]    = df["time"].apply(fix_time)
    return df

# def load_raw(sh) -> pd.DataFrame:
#     df = pd.DataFrame(sh.worksheet(SHEET_RAW).get_all_records())
#     if df.empty:
#         raise ValueError("daily_raw 是空的")
#     df = df.rename(columns={
#         "Date": "date", "Weekday": "weekday", "Week_num": "week_num",
#         "Time": "time", "order_counts": "order_counts",
#         "cups": "cups", "revenues": "revenue",
#     })
#     df["date"]    = pd.to_datetime(df["date"], format="mixed")
#     df["cups"]    = pd.to_numeric(df["cups"],    errors="coerce").fillna(0).astype(int)
#     df["revenue"] = pd.to_numeric(df["revenue"], errors="coerce").fillna(0).astype(int)
#     df["time"]    = df["time"].apply(fix_time)
#     return df


def load_target(sh) -> pd.DataFrame:
    df = pd.DataFrame(sh.worksheet(SHEET_TARGET).get_all_records())
    if df.empty:
        return pd.DataFrame(columns=["date", "time", "target_cups", "target_rev"])
    df["date"]        = pd.to_datetime(df["date"], format="mixed")
    df["target_cups"] = pd.to_numeric(df["target_cups"], errors="coerce").fillna(0)
    df["target_rev"]  = pd.to_numeric(df["target_rev"],  errors="coerce").fillna(0)
    df["time"]        = df["time"].apply(fix_time)
    return df


# ── 計算 daily_summary ────────────────────────────────────
def calc_daily_summary(raw: pd.DataFrame, target: pd.DataFrame) -> pd.DataFrame:

    actual = (
        raw.groupby("date")
        .agg(
            weekday     = ("weekday",  "first"),
            week_num    = ("week_num", "first"),
            actual_cups = ("cups",     "sum"),
            actual_rev  = ("revenue",  "sum"),
        )
        .reset_index()
    )

    tgt_day = (
        target.groupby("date")
        .agg(
            target_cups = ("target_cups", "sum"),
            target_rev  = ("target_rev",  "sum"),
        )
        .reset_index()
    )

    df = actual.merge(tgt_day, on="date", how="left")
    df["target_cups"] = df["target_cups"].fillna(0)
    df["target_rev"]  = df["target_rev"].fillna(0)

    df["achieved_pct"] = df.apply(
        lambda r: round(r["actual_rev"] / r["target_rev"] * 100, 1)
        if r["target_rev"] > 0 else None,
        axis=1,
    )

    df = df.sort_values("date")
    df["date"] = df["date"].dt.strftime("%Y/%m/%d")
    return df[[
        "date", "weekday", "week_num",
        "target_cups", "target_rev",
        "actual_cups", "actual_rev",
        "achieved_pct",
    ]]


# ── 計算 weekly_summary ───────────────────────────────────
def calc_weekly_summary(raw: pd.DataFrame) -> pd.DataFrame:

    base = (
        raw.groupby("week_num")
        .agg(
            actual_cups = ("cups",    "sum"),
            actual_rev  = ("revenue", "sum"),
        )
        .reset_index()
    )

    # avg_cups_per_hour：有資料的時段才算
    slot_count = (
        raw[raw["cups"] > 0]
        .groupby("week_num").size()
        .rename("slot_count")
    )
    base = base.join(slot_count, on="week_num")
    base["avg_cups_per_hour"] = (
        base["actual_cups"] / base["slot_count"]
    ).round(1).fillna(0)

    # peak_hour：每週哪個時段杯數加總最高
    hourly = raw.groupby(["week_num", "time"])["cups"].sum().reset_index()
    peak   = (
        hourly.loc[hourly.groupby("week_num")["cups"].idxmax()]
        [["week_num", "time"]]
        .rename(columns={"time": "peak_hour"})
    )
    base = base.merge(peak, on="week_num", how="left")

    return base.sort_values("week_num")[[
        "week_num", "actual_cups", "actual_rev",
        "avg_cups_per_hour", "peak_hour",
    ]]


# ── 寫回 Sheet ───────────────────────────────────────────
def write_sheet(sh, name: str, df: pd.DataFrame):
    ws = sh.worksheet(name)
    ws.clear()
    rows = [df.columns.tolist()]
    for _, row in df.iterrows():
        rows.append([
            "" if (v is None or (isinstance(v, float) and pd.isna(v))) else v
            for v in row.tolist()
        ])
    ws.update(rows, "A1")
    print(f"  ✓ {name}：{len(df)} 列")


# ── 主程式 ───────────────────────────────────────────────
def main():
    print("── ETL 開始 ───────────────────────────")

    sh = connect()
    print("連線成功")

    raw    = load_raw(sh)
    target = load_target(sh)
    print(f"daily_raw：{len(raw)} 筆，{raw['date'].nunique()} 天")
    print(f"target：{len(target)} 筆")

    daily  = calc_daily_summary(raw, target)
    weekly = calc_weekly_summary(raw)

    print("寫回 Sheets...")
    write_sheet(sh, SHEET_DAILY,  daily)
    write_sheet(sh, SHEET_WEEKLY, weekly)

    print("\n── daily_summary 預覽（最後 5 天）──")
    print(daily.tail(5).to_string(index=False))

    print("\n── weekly_summary ──")
    print(weekly.to_string(index=False))

    print("\n完成！")


if __name__ == "__main__":
    main()
