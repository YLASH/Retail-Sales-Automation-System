"""
calculate_target.py

讀取 Google Sheets daily_raw → 計算前兩週同星期同時段均值 → 寫回 target sheet
"""

import gspread
import pandas as pd
from google.oauth2.service_account import Credentials
from datetime import datetime, timedelta
from typing import List, Dict

# ─── 設定區（只需改這裡）────────────────────────────────
import os
from dotenv import load_dotenv
load_dotenv()
SPREADSHEET_ID = os.getenv("SPREADSHEET_ID")
SERVICE_ACCOUNT_FILE = os.getenv("SERVICE_ACCOUNT_FILE", "service_account.json")


SHEET_DAILY_RAW = "daily_raw_clean"
SHEET_TARGET    = "target"

HOURS = ["10:00","11:00","12:00","13:00","14:00",
         "15:00","16:00","17:00","18:00","19:00",
         "20:00","21:00","22:00"]
# ────────────────────────────────────────────────────────


def connect_sheets():
    """建立 Google Sheets 連線"""
    scopes = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive",
    ]
    creds = Credentials.from_service_account_file(
        SERVICE_ACCOUNT_FILE, scopes=scopes
    )
    client = gspread.authorize(creds)
    return client.open_by_key(SPREADSHEET_ID)

def load_daily_raw(sheet) -> pd.DataFrame:
    """讀取 daily_raw sheet，回傳清理好的 DataFrame"""
    ws = sheet.worksheet(SHEET_DAILY_RAW)
    all_values = ws.get_all_values()
    # print(len(all_values[0]))
    data = ws.get_all_records()
    df = pd.DataFrame(data)

    if df.empty:
        raise ValueError("daily_raw 是空的，請先填入資料")

    # 欄位名稱對應（對應你 Google Sheet 的實際欄位名）
    col_map = {
        "Date":         "date",
        "Weekday":      "weekday",
        "Week_num":     "week_num",
        "Time":         "time",
        "order_counts": "order_counts",
        "cups":         "cups",
        "revenues":      "revenues",
    }
    df = df.rename(columns={k: v for k, v in col_map.items() if k in df.columns})

    # 日期轉換（支援 yyyy/mm/dd 和 yyyy-mm-dd）
    df["date"] = pd.to_datetime(df["date"], format="mixed")

    # time 欄：Google Sheets 有時會讀成浮點數，統一轉成 HH:MM 字串
    def fix_time(val):
        if isinstance(val, (int, float)):
            # Sheets 時間是當天的小數比例，乘以 24 = 小時
            hours = int(round(val * 24))
            return f"{hours:02d}:00"
        return str(val).strip()

    df["time"] = df["time"].apply(fix_time)

    # 數值欄轉型
    for col in ["order_counts", "cups", "revenues"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0)

    # 加上輔助欄位
    df["weekday_num"] = df["date"].dt.dayofweek   # 0=Monday, 6=Sunday

    return df


def calc_target_for_date(df: pd.DataFrame, target_date: pd.Timestamp) -> List[Dict]:
    """
    計算 target_date 這天每個時段的預期目標
    邏輯：前兩週中，同一 weekday + 同一 time 的均值
    
    回傳：list of dict，每個 time 一筆
    """
    target_weekday = target_date.dayofweek

    # 前兩週的同星期日期
    prev_week1 = target_date - timedelta(weeks=1)
    prev_week2 = target_date - timedelta(weeks=2)

    results = []
    for hour in HOURS:
        # 找前兩週同星期同時段的資料
        mask = (
            (df["date"].isin([prev_week1, prev_week2])) &
            (df["weekday_num"] == target_weekday) &
            (df["time"] == hour)
        )
        subset = df[mask]

        if subset.empty:
            # 資料不足，用 None（之後在 Sheet 顯示為空）
            target_cups = None
            target_rev  = None
        else:
            target_cups = round(subset["cups"].mean())
            target_rev  = round(subset["revenues"].mean())

        results.append({
            "date":        target_date.strftime("%Y/%m/%d"),
            "week_num":    f"W{target_date.isocalendar()[1]:02d}",
            "time":        hour,
            "target_cups": target_cups,
            "target_rev":  target_rev,
        })

    return results


def calc_targets_for_week(df: pd.DataFrame, week_start: pd.Timestamp) -> pd.DataFrame:
    """
    計算某週（7天）每天每時段的 target
    week_start：該週的第一天（通常是週一）
    """
    all_rows = []
    week_start =df['date'].min() + pd.Timedelta(days=7) 
    week_end =df['date'].max() + pd.Timedelta(days=7) 
    duration = week_end - week_start
    days_count = duration.days

    for day_offset in range(days_count):
        day = week_start + timedelta(days=day_offset)
        rows = calc_target_for_date(df, day)
        all_rows.extend(rows)

    return pd.DataFrame(all_rows)


def write_targets_to_sheet(sheet, target_df: pd.DataFrame, clear_first: bool = True):
    """將計算好的 target 寫回 Google Sheets target sheet"""
    ws = sheet.worksheet(SHEET_TARGET)

    if clear_first:
        print(clear_first)
        # ws.clear() 是否清除整個工作表內容？如果只想清除特定範圍，可以改成 ws.batch_clear(["A2:E1000"]) 之類的

    # 寫入標題列
    headers = ["date", "week_num", "time", "target_cups", "target_rev"]
    rows = [headers]

    for _, row in target_df.iterrows():
        rows.append([
            row["date"],
            row["week_num"],
            row["time"],
            row["target_cups"] if pd.notna(row.get("target_cups")) else "",
            row["target_rev"]  if pd.notna(row.get("target_rev"))  else "",
        ])

    ws.update(rows, "A1")
    print(f"✓ 已寫入 {len(target_df)} 筆 target 資料到 '{SHEET_TARGET}' sheet")


def get_next_week_start() -> pd.Timestamp:
    """取得下週一的日期"""
    today = pd.Timestamp.today().normalize()
    days_until_monday = (7 - today.dayofweek) % 7
    if days_until_monday == 0:
        days_until_monday = 7
    return today + timedelta(days=days_until_monday)


def main():
    print("── 業績 Target 計算器 ──────────────────────")

    # 1. 連線
    print("連接 Google Sheets...")
    sheet = connect_sheets()

    # 2. 讀取原始資料
    print("讀取 daily_raw...")
    df = load_daily_raw(sheet)
    print(f"  共讀取 {len(df)} 筆時段資料，涵蓋 {df['date'].nunique()} 天")

    # 3. 決定要算哪週的 target
    #    預設算「下週」，也可以改成指定日期
    # week_start = get_next_week_start()
    # week_start =df['date'].min() + pd.Timedelta(days=7) #資料有限所以目前手動增加
    # week_start =df['date'].max() + pd.Timedelta(days=1) #從資料的下一天開始算
    week_start =df['date'].max() 
    print(f"計算目標週：{week_start.strftime('%Y/%m/%d')} (週一) 起的一週")

    # 若資料不足兩週，給出警告
    available_days = df["date"].nunique()
    if available_days < 14:
        print(f"  ⚠️  目前只有 {available_days} 天資料（建議至少 14 天）")
        print(f"  ⚠️  資料不足的時段 target 會顯示為空白")

    # 4. 計算
    target_df = calc_targets_for_week(df, week_start)

    # 5. 印出預覽
    print("\n預覽（前 5 筆）：")
    print(target_df.tail().to_string(index=False))

    # 6. 寫回 Sheet
    write_targets_to_sheet(sheet, target_df)
    print("\n完成！請到 Google Sheets 的 target sheet 確認結果")


if __name__ == "__main__":
    main()
