"""
app.py  ─  門市業績 Dashboard
執行方式：streamlit run app.py
"""

import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import gspread
from google.oauth2.service_account import Credentials

# ── 設定 ─────────────────────────────────────────────────
import os
from dotenv import load_dotenv

load_dotenv()
SPREADSHEET_ID = os.getenv("SPREADSHEET_ID")
SERVICE_ACCOUNT_FILE = os.getenv("SERVICE_ACCOUNT_FILE", "service_account.json")

HOLIDAYS = {
    "2026/02/14": "情人節",
    "2026/02/16": "春節連假", "2026/02/17": "春節連假",
    "2026/02/18": "春節連假", "2026/02/19": "春節連假",
    "2026/02/20": "春節連假", "2026/02/21": "春節連假",
    "2026/02/22": "春節連假",
"2026/02/28": "228和平紀念日","2026/04/04":"清明節","2026/04/05":"兒童節",
"2025/05/01":"勞動節",
}
# ────────────────────────────────────────────────────────

st.set_page_config(
    page_title="門市業績 Dashboard",
    page_icon="📊",
    layout="wide",
)


# ── 讀取資料（cache 5 分鐘）──────────────────────────────
@st.cache_data(ttl=300)
def load_data():
    scopes = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive",
    ]
    creds  = Credentials.from_service_account_file(SERVICE_ACCOUNT_FILE, scopes=scopes)
    client = gspread.authorize(creds)
    sh     = client.open_by_key(SPREADSHEET_ID)

    def read(name):
        values = sh.worksheet(name).get_all_values()
        if len(values) < 2:
            return pd.DataFrame()
        df = pd.DataFrame(values[1:], columns=values[0])
        df = df.loc[:, df.columns.str.strip() != ""]
        df = df[df.iloc[:, 0].str.strip() != ""].reset_index(drop=True)
        return df

    # return read("daily_summary"), read("weekly_summary"), read("daily_raw_clean")
    ml_pred = read("ml_predictions")
    return read("daily_summary"), read("weekly_summary"), read("daily_raw_clean"), ml_pred


# ── 前處理 ───────────────────────────────────────────────
def prep_daily(df):
    df = df.copy()
    df["date"]         = pd.to_datetime(df["date"], format="mixed")
    df["actual_rev"]   = pd.to_numeric(df["actual_rev"],   errors="coerce").fillna(0)
    df["target_rev"]   = pd.to_numeric(df["target_rev"],   errors="coerce").fillna(0)
    df["actual_cups"]  = pd.to_numeric(df["actual_cups"],  errors="coerce").fillna(0)
    df["target_cups"]  = pd.to_numeric(df["target_cups"],  errors="coerce").fillna(0)
    df["achieved_pct"] = pd.to_numeric(df["achieved_pct"], errors="coerce")
    df["holiday"] = df["date"].dt.strftime("%Y/%m/%d").map(HOLIDAYS).fillna("")
    return df


def prep_weekly(df):
    df = df.copy()
    for col in ["actual_rev", "actual_cups", "avg_cups_per_hour"]:
        df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0)
    return df


def prep_raw(df):
    df = df.copy()
    df = df.rename(columns={
        "Date": "date", "Weekday": "weekday", "Week_num": "week_num",
        "Time": "time", "cups": "cups", "revenues": "revenue",
    })
    df["date"]    = pd.to_datetime(df["date"], format="mixed")
    df["cups"]    = pd.to_numeric(df["cups"],    errors="coerce").fillna(0)
    df["revenue"] = pd.to_numeric(df["revenue"], errors="coerce").fillna(0)
    return df


# ════════════════════════════════════════════════════════
st.title("📊 門市業績 Dashboard")

with st.spinner("讀取 Google Sheets..."):
    try:
        daily_raw, weekly_raw, raw_raw, ml_raw = load_data()
        daily  = prep_daily(daily_raw)
        weekly = prep_weekly(weekly_raw)
        raw    = prep_raw(raw_raw)
    except Exception as e:
        st.error(f"讀取失敗：{e}")
        st.stop()

tab_week, tab_day = st.tabs(["📅 每週總覽", "🕐 每日時段"])


# ════════════════════════════════════════════════════════
#  週報
# ════════════════════════════════════════════════════════
with tab_week:

    weeks = sorted(daily["week_num"].unique())
    sel_wk = st.selectbox("選擇週別", weeks, index=len(weeks)-1, key="wk")

    wdf = daily[daily["week_num"] == sel_wk].sort_values("date")
    wdf["label"] = wdf.apply(
        lambda r: r["date"].strftime("%m/%d(%a)") + (" ★" if r["holiday"] else ""), axis=1
    )

     # 週別日期範圍標示
    if not wdf.empty:
        w_start = wdf["date"].min().strftime("%m/%d")
        w_end   = wdf["date"].max().strftime("%m/%d")
        w_label = f"{sel_wk}　{w_start} ～ {w_end}"
        st.markdown(f"<h4 style='margin:0 0 12px;color:var(--text-color)'>{w_label}</h4>", unsafe_allow_html=True)
    wdf["label"] = wdf.apply(
        lambda r: r["date"].strftime("%m/%d(%a)") + (" ★" if r["holiday"] else ""), axis=1
    )

    total_rev  = int(wdf["actual_rev"].sum())
    total_cups = int(wdf["actual_cups"].sum())
    total_trev = int(wdf["target_rev"].sum())
    achieved   = round(total_rev / total_trev * 100, 1) if total_trev > 0 else None
    n_days     = len(wdf)

    wow_str = ""
    prev_idx = weeks.index(sel_wk) - 1
    if prev_idx >= 0:
        prev_rev = int(daily[daily["week_num"] == weeks[prev_idx]]["actual_rev"].sum())
        diff = total_rev - prev_rev
        wow_str = f"{'↑' if diff >= 0 else '↓'} ${abs(diff):,} vs {weeks[prev_idx]}"

    # KPI 卡
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("週總營業額", f"${total_rev:,}", wow_str)
    c2.metric("週總杯數", f"{total_cups:,}", f"均 {total_cups // n_days if n_days else 0} 杯/日")
    c3.metric("目標達成率", f"{achieved}%" if achieved else "—")
    c4.metric("營業天數", f"{n_days} 天", f"日均 ${total_rev // n_days if n_days else 0:,}")

    st.divider()

    col_l, col_r = st.columns([3, 2])

    with col_l:
        fig = go.Figure()
        fig.add_bar(x=wdf["label"], y=wdf["actual_rev"], name="實際", marker_color="#378ADD")
        fig.add_scatter(
            x=wdf["label"], y=wdf["target_rev"].replace(0, None),
            name="目標", mode="lines+markers",
            line=dict(color="#E24B4A", width=2, dash="dot"), marker=dict(size=6),
        )
        fig.update_layout(
            title="每日營業額：實際 vs 目標", height=300,
            margin=dict(t=40, b=20, l=0, r=80),
            # legend=dict(orientation="h", y=1.15),
            legend=dict(orientation="v", x=1.12, y=0.5, xanchor="left", yanchor="middle"),
            yaxis=dict(tickprefix="$", tickformat=","),
        )
        st.plotly_chart(fig, use_container_width=True)

    with col_r:
        bar_colors = wdf["achieved_pct"].apply(
            lambda v: "#639922" if pd.notna(v) and v >= 100
            else "#BA7517" if pd.notna(v) and v >= 80
            else "#E24B4A"
        ).tolist()
        fig2 = go.Figure(go.Bar(
            x=wdf["label"], y=wdf["achieved_pct"],
            marker_color=bar_colors,
            text=wdf["achieved_pct"].apply(lambda v: f"{v}%" if pd.notna(v) else "—"),
            textposition="outside",
        ))
        fig2.add_hline(y=100, line_dash="dash", line_color="#aaa", line_width=1)
        max_pct = wdf["achieved_pct"].max()
        fig2.update_layout(
            title="每日達成率", height=300,
            margin=dict(t=40, b=20, l=0, r=0),
            yaxis=dict(ticksuffix="%", range=[0, max(150, (max_pct + 20) if pd.notna(max_pct) else 150)]),
        )
        st.plotly_chart(fig2, use_container_width=True)

    # 熱力圖
    st.subheader("時段杯數熱力圖")
    wraw = raw[raw["week_num"] == sel_wk].copy()
    if not wraw.empty:
        wraw["label"] = wraw["date"].apply(
            lambda d: d.strftime("%m/%d(%a)") + (" ★" if HOLIDAYS.get(d.strftime("%Y/%m/%d")) else "")
        )
        pivot = wraw.pivot_table(index="time", columns="label", values="cups", aggfunc="sum").fillna(0)
        hours_order = [f"{h:02d}:00" for h in range(10, 23)]
        pivot = pivot.reindex([h for h in hours_order if h in pivot.index])
        fig3 = px.imshow(
            pivot, color_continuous_scale=["#EAF3DE", "#97C459", "#185FA5"],
            aspect="auto", labels=dict(color="杯數"),
        )
        fig3.update_layout(height=320, margin=dict(t=10, b=20, l=0, r=0), xaxis_title="", yaxis_title="")
        st.plotly_chart(fig3, use_container_width=True)
    else:
        st.info("此週無時段資料")

    # 跨週趨勢
    st.subheader("跨週營業額趨勢")
    fig4 = go.Figure(go.Scatter(
        x=weekly["week_num"], y=weekly["actual_rev"],
        mode="lines+markers+text",
        text=weekly["actual_rev"].apply(lambda v: f"${v/1000:.0f}K"),
        textposition="top center",
        line=dict(color="#378ADD", width=2),
        marker=dict(
            size=weekly["week_num"].apply(lambda w: 12 if w == sel_wk else 6),
            color=weekly["week_num"].apply(lambda w: "#185FA5" if w == sel_wk else "#378ADD"),
        ),
    ))
    fig4.update_layout(
        height=220, margin=dict(t=30, b=20, l=0, r=0),
        yaxis=dict(tickprefix="$", tickformat=","),
    )
    st.plotly_chart(fig4, use_container_width=True)

     # ── ML 預測區塊 ──────────────────────────────────────
    st.divider()
    st.subheader("🤖 ML 模型預測比較（Walk-Forward Validation）")
 
    if ml_raw.empty:
        st.info("尚無 ML 預測資料，請先執行 update_all.py")
    else:
        # 解析 ml_predictions sheet
        # 摘要列（#MAPE_AVG, #MAPE_WEEK）和明細列分開
        mape_avg  = ml_raw[ml_raw["date"] == "#MAPE_AVG"]
        mape_week = ml_raw[ml_raw["date"] == "#MAPE_WEEK"]
        detail    = ml_raw[~ml_raw["date"].str.startswith("#")].copy()
 
        # 整體 MAPE 卡
        if not mape_avg.empty:
            avg_row = mape_avg.iloc[1] if len(mape_avg) > 1 else None
            try:
                avg_bl = float(ml_raw[ml_raw["date"]=="#MAPE_VALUE"]["week_num"].values[0])
                avg_lr = float(ml_raw[ml_raw["date"]=="#MAPE_VALUE"]["time"].values[0])
                avg_rf = float(ml_raw[ml_raw["date"]=="#MAPE_VALUE"]["actual"].values[0])
                col_m1, col_m2, col_m3 = st.columns(3)
                col_m1.metric("Baseline 平均 MAPE", f"{avg_bl}%")
                col_m2.metric("Linear Regression 平均 MAPE", f"{avg_lr}%")
                col_m3.metric("Random Forest 平均 MAPE", f"{avg_rf}%",
                              f"比 Baseline 改善 {round(avg_bl-avg_rf,1)}%")
                st.caption("Walk-Forward Validation：每週用前面所有週訓練，預測下一週，數字越小越準")
            except Exception:
                pass
 
        # 每週 MAPE 折線圖
        if not mape_week.empty:
            wm = mape_week.copy()
            wm.columns = ml_raw.columns
            wm = wm.rename(columns={"week_num":"week","time":"bl","actual":"lr","baseline_pred":"rf"})
            for c in ["bl","lr","rf"]:
                wm[c] = pd.to_numeric(wm[c], errors="coerce")
 
            fig_mape = go.Figure()
            fig_mape.add_scatter(x=wm["week"], y=wm["bl"],
                                 name="Baseline", mode="lines+markers",
                                 line=dict(color="#B4B2A9", dash="dot"), marker=dict(size=6))
            fig_mape.add_scatter(x=wm["week"], y=wm["lr"],
                                 name="Linear Regression", mode="lines+markers",
                                 line=dict(color="#BA7517", dash="dash"), marker=dict(size=6))
            fig_mape.add_scatter(x=wm["week"], y=wm["rf"],
                                 name="Random Forest", mode="lines+markers",
                                 line=dict(color="#1D9E75", width=2), marker=dict(size=7))
            fig_mape.update_layout(
                title="各週 MAPE 趨勢（越低越準）",
                height=260, margin=dict(t=40,b=20,l=0,r=0),
                yaxis=dict(ticksuffix="%"),
                legend=dict(orientation="h", x=1.0, y=1.0, xanchor="right", yanchor="bottom"),
            )
            st.plotly_chart(fig_mape, use_container_width=True)
 
        # 每日實際 vs 預測折線圖（選週別）
        if not detail.empty:
            for c in ["actual","baseline_pred","lr_pred","rf_pred"]:
                detail[c] = pd.to_numeric(detail[c], errors="coerce").fillna(0)
            detail["date_dt"] = pd.to_datetime(detail["date"], format="mixed")
 
            ml_weeks = sorted(detail["week_num"].unique())
            sel_ml_wk = st.selectbox("ML 預測週別", ml_weeks,
                                      index=len(ml_weeks)-1, key="ml_wk")
 
            wdet = detail[detail["week_num"] == sel_ml_wk]
            daily_cmp = wdet.groupby("date_dt").agg(
                actual      = ("actual",       "sum"),
                baseline    = ("baseline_pred", "sum"),
                lr          = ("lr_pred",       "sum"),
                rf          = ("rf_pred",       "sum"),
            ).reset_index()
            daily_cmp["label"] = daily_cmp["date_dt"].apply(
                lambda d: d.strftime("%m/%d(%a)") + (" ★" if HOLIDAYS.get(d.strftime("%Y/%m/%d")) else "")
            )
 
            fig_ml = go.Figure()
            fig_ml.add_scatter(x=daily_cmp["label"], y=daily_cmp["actual"],
                               name="實際", mode="lines+markers",
                               line=dict(color="#378ADD", width=2), marker=dict(size=7))
            fig_ml.add_scatter(x=daily_cmp["label"], y=daily_cmp["baseline"],
                               name="Baseline", mode="lines+markers",
                               line=dict(color="#B4B2A9", width=1.5, dash="dot"), marker=dict(size=5))
            fig_ml.add_scatter(x=daily_cmp["label"], y=daily_cmp["lr"],
                               name="Linear Regression", mode="lines+markers",
                               line=dict(color="#BA7517", width=2, dash="dash"), marker=dict(size=6))
            fig_ml.add_scatter(x=daily_cmp["label"], y=daily_cmp["rf"],
                               name="Random Forest", mode="lines+markers",
                               line=dict(color="#1D9E75", width=2, dash="dash"), marker=dict(size=6))
            fig_ml.update_layout(
                title=f"每日營業額：實際 vs 預測（{sel_ml_wk}）",
                height=300, margin=dict(t=40,b=20,l=0,r=0),
                yaxis=dict(tickprefix="$", tickformat=","),
                legend=dict(orientation="h", x=1.0, y=1.0, xanchor="right", yanchor="bottom"),
            )
            st.plotly_chart(fig_ml, use_container_width=True)
# ════════════════════════════════════════════════════════
#  日報
# ════════════════════════════════════════════════════════
with tab_day:

    all_dates = sorted(daily["date"].dt.strftime("%Y/%m/%d").unique(), reverse=True)
    sel_date  = st.selectbox("選擇日期", all_dates, key="dt")
    date_ts   = pd.to_datetime(sel_date)
    holiday   = HOLIDAYS.get(sel_date, "")

   # 日期和節日標示放大
    holiday_badge = f"　<span style='background:#FAEEDA;color:#633806;padding:2px 10px;border-radius:4px;font-size:14px'>★ {holiday}</span>" if holiday else ""
    st.markdown(
        f"<div style='font-size:22px;font-weight:500;margin-bottom:8px'>"
        f"{date_ts.strftime('%Y/%m/%d')}　{date_ts.strftime('%A')}{holiday_badge}</div>",
        unsafe_allow_html=True
    )
 
    drow = daily[daily["date"] == date_ts]
    if not drow.empty:
        r = drow.iloc[0]
        d1, d2, d3 = st.columns(3)
        d1.metric("當日營業額", f"${int(r['actual_rev']):,}", f"目標 ${int(r['target_rev']):,}")
        d2.metric("當日杯數",   f"{int(r['actual_cups'])}",  f"目標 {int(r['target_cups'])}")
        d3.metric("達成率",     f"{r['achieved_pct']}%" if pd.notna(r["achieved_pct"]) else "—")
 
    st.divider()

    hour_df = raw[raw["date"] == date_ts].sort_values("time")
    if not hour_df.empty:
        fig5 = go.Figure()
        fig5.add_bar(x=hour_df["time"], y=hour_df["revenue"],
                     name="營業額", marker_color="#378ADD", yaxis="y")
        fig5.add_scatter(x=hour_df["time"], y=hour_df["cups"],
                         name="杯數", mode="lines+markers",
                         line=dict(color="#1D9E75", width=2),
                         marker=dict(size=6), yaxis="y2")
        fig5.update_layout(
            title="時段營業額 & 杯數", height=340,
            margin=dict(t=40, b=20, l=0, r=60),
            yaxis =dict(tickprefix="$", tickformat=",", title="營業額"),
            yaxis2=dict(title="杯數", overlaying="y", side="right"),
            legend=dict(orientation="v", x=1.12, y=0.5, xanchor="left", yanchor="middle"),            
        )
        st.plotly_chart(fig5, use_container_width=True)

        peak = hour_df.loc[hour_df["cups"].idxmax()]
        st.caption(f"高峰時段：{peak['time']}（{int(peak['cups'])} 杯　${int(peak['revenue']):,}）")
    else:
        st.info("此日無時段資料")


# ── 重新讀取 ─────────────────────────────────────────────
st.divider()
if st.button("🔄 重新讀取資料"):
    st.cache_data.clear()
    st.rerun()
