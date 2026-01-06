import streamlit as st
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from gspread.exceptions import APIError
import pandas as pd
import os
import time
import random
from datetime import datetime, timedelta
import unicodedata
import threading
import requests

# ==========================================
# 🔧 配置区域 (已更新至 2026 Q1)
# ==========================================
SALES_SHEET_ID = '1jniQ-GpeMINjQMebniJ_J1eLVLQIR1NGbSjTtOFP9Q8'
SALES_TAB_NAME = 'Positions'

# 定义当前季度
CURRENT_YEAR = 2026
CURRENT_QUARTER = 1
CURRENT_Q_STR = f"{CURRENT_YEAR} Q{CURRENT_QUARTER}"

# 🎯 简历目标设置 (季度)
CV_TARGET_QUARTERLY = 87

TEAM_CONFIG = [
    {"name": "Raul Solis", "id": "1vQuN-iNBRUug5J6gBMX-52jp6oogbA77SaeAf9j_zYs", "keyword": "Name", "base_salary": 11000},
    {"name": "Estela Peng", "id": "1sUkffAXzWnpzhhmklqBuwtoQylpR1U18zqBQ-lsp7Z4", "keyword": "姓名", "base_salary": 20800},
    {"name": "Ana Cruz", "id": "1VMVw5YCV12eI8I-VQSXEKg86J2IVZJEgjPJT7ggAFD0", "keyword": "Name", "base_salary": 13000},
    {"name": "Karina Albarran", "id": "1zc4ghvfjIxH0eJ2aXfopOWHqiyTDlD8yFNjBzpH07D8", "keyword": "Name", "base_salary": 15000},
]

st.set_page_config(page_title="Management Dashboard 2026", page_icon="💼", layout="wide")

# --- 🎨 样式 ---
st.markdown("""
    <style>
    .stApp { background-color: #FFFFFF; color: #000000; }
    h1, h2, h3, h4 { color: #333333 !important; font-family: 'Arial', sans-serif; }
    .section-head { background-color: #f0f2f6; padding: 10px; border-radius: 5px; margin-top: 20px; border-left: 5px solid #0056b3; }
    .stButton>button { background-color: #0056b3; color: white; }
    div[data-testid="metric-container"] { background-color: #f8f9fa; border: 1px solid #e9ecef; padding: 15px; border-radius: 8px; }
    </style>
    """, unsafe_allow_html=True)

# --- 🧮 辅助函数 ---
def get_quarter_str(date_obj):
    if pd.isna(date_obj): return "Unknown"
    q = (date_obj.month - 1) // 3 + 1
    return f"{date_obj.year} Q{q}"

def calculate_commission_tier(total_gp, base_salary, is_team_lead=False):
    t1, t2, t3 = (4.5, 6.75, 11.25) if is_team_lead else (9.0, 13.5, 22.5)
    if total_gp < t1 * base_salary: return 0, 0
    elif total_gp < t2 * base_salary: return 1, 1
    elif total_gp < t3 * base_salary: return 2, 2
    else: return 3, 3

def calculate_single_deal_commission(candidate_salary, multiplier):
    if multiplier == 0: return 0
    if candidate_salary < 20000: base_comm = 1000
    elif candidate_salary < 30000: base_comm = candidate_salary * 0.05
    elif candidate_salary < 50000: base_comm = candidate_salary * 1.5 * 0.05
    else: base_comm = candidate_salary * 2.0 * 0.05
    return base_comm * multiplier

def get_commission_pay_date(payment_date):
    if pd.isna(payment_date) or not payment_date: return None
    try:
        year = payment_date.year + (payment_date.month // 12)
        month = (payment_date.month % 12) + 1
        return datetime(year, month, 15)
    except: return None

def normalize_text(text):
    return ''.join(c for c in unicodedata.normalize('NFD', str(text)) if unicodedata.category(c) != 'Mn').lower()

def safe_api_call(func, *args, **kwargs):
    for i in range(5):
        try: return func(*args, **kwargs)
        except APIError as e:
            if "429" in str(e): time.sleep(2**i + random.random())
            else: raise e
    return None

def connect_to_google():
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    if "gcp_service_account" in st.secrets:
        creds = ServiceAccountCredentials.from_json_keyfile_dict(dict(st.secrets["gcp_service_account"]), scope)
        return gspread.authorize(creds)
    return None

# --- 数据获取逻辑 ---
def fetch_role(client, sheet_id):
    try:
        ws = client.open_by_key(sheet_id).worksheet('Credentials')
        return ws.acell('B1').value.strip()
    except: return "Consultant"

def internal_fetch_sheet_data(client, conf, tab):
    try:
        sheet = client.open_by_key(conf['id'])
        ws = sheet.worksheet(tab)
        rows = ws.get_all_values()
        details, cs, ci, co = [], 0, 0, 0
        target_key = conf.get('keyword', 'Name')
        # 简化逻辑：匹配行
        current_comp, current_pos = "Unk", "Unk"
        for r in rows:
            if not r or not r[0]: continue
            f = r[0].strip()
            if f in ["Company", "Client", "公司"]: current_comp = r[1] if len(r)>1 else "Unk"
            elif f in ["Position", "职位"]: current_pos = r[1] if len(r)>1 else "Unk"
            elif f == target_key:
                for idx, v in enumerate(r[1:], 1):
                    if v.strip():
                        cs += 1
                        details.append({"Consultant": conf['name'], "Month": tab, "Company": current_comp, "Position": current_pos, "Status": "Sent", "Count": 1})
        return cs, ci, co, details
    except: return 0,0,0,[]

def fetch_all_data(client, live_months):
    # 1. 团队角色
    team = []
    for c in TEAM_CONFIG:
        c['role'] = fetch_role(client, c['id'])
        team.append(c)

    # 2. 招聘数据 (Live + Historical)
    rec_stats, rec_details = [], []
    # 尝试获取所有月份
    all_months_found = []
    try:
        main_sheet = client.open_by_key(TEAM_CONFIG[0]['id'])
        all_months_found = [ws.title for ws in main_sheet.worksheets() if ws.title.isdigit()]
    except: all_months_found = live_months

    for m in all_months_found:
        for c in team:
            s, i, o, d = internal_fetch_sheet_data(client, c, m)
            rec_stats.append({"Consultant": c['name'], "Month": m, "Year": m[:4], "Sent": s, "Int": i, "Off": o})
            rec_details.extend(d)
    
    # 3. 销售数据
    sales_records = []
    try:
        ws = client.open_by_key(SALES_SHEET_ID).worksheet(SALES_TAB_NAME)
        rows = ws.get_all_values()
        # 寻找表头逻辑 (简化)
        header = rows[0] # 假设第一行或根据关键词定位
        for row in rows[1:]:
            if len(row) < 5 or not row[0]: continue
            # 简单解析逻辑 (需匹配原件列索引)
            # 假设 Col 0: LinkEazi, Col 1: Onboard, Col 2: Salary, Col 4: Payment
            try:
                dt = datetime.strptime(row[1], "%Y-%m-%d")
                sal = float(row[2].replace(',',''))
                sales_records.append({
                    "Consultant": row[0], "GP": sal * 1.5, "Candidate Salary": sal, 
                    "Onboard Date": dt, "Status": "Paid" if len(row[4])>5 else "Pending",
                    "Payment Date": row[4], "Percentage": 1.0, "Quarter": get_quarter_str(dt), "Year": str(dt.year)
                })
            except: continue
    except: pass

    return pd.DataFrame(team), pd.DataFrame(rec_stats), pd.DataFrame(rec_details), pd.DataFrame(sales_records)

# --- 🚀 主界面 ---
def main():
    st.title("💼 Executive Management System - 2026")
    
    client = connect_to_google()
    if not client: st.error("Authentication Failed"); return

    live_months = ["202601", "202602", "202603"]

    if st.button("🔄 REFRESH ALL DATA"):
        with st.spinner("Syncing Live & Historical Records..."):
            t, rs, rd, s = fetch_all_data(client, live_months)
            st.session_state['t'], st.session_state['rs'], st.session_state['rd'], st.session_state['s'] = t, rs, rd, s
            st.session_state['last_upd'] = datetime.now().strftime("%Y-%m-%d %H:%M")
            st.rerun()

    if 't' not in st.session_state:
        st.info("Please refresh data to begin."); return

    team_df, rec_df, rec_details_df, sales_df = st.session_state['t'], st.session_state['rs'], st.session_state['rd'], st.session_state['s']

    tab1, tab2 = st.tabs(["📊 DASHBOARD", "🔍 DRILL DOWN DETAILS"])

    # ==========================================
    # Tab 1: Dashboard
    # ==========================================
    with tab1:
        # --- 1. Recruitment Stats ---
        st.markdown("<div class='section-head'><h3>🎯 Recruitment Stats</h3></div>", unsafe_allow_html=True)
        col_r1, col_r2 = st.columns(2)
        
        with col_r1:
            st.subheader("Live: 2026 Q1")
            live_rec = rec_df[rec_df['Month'].isin(live_months)].groupby('Consultant')[['Sent', 'Int', 'Off']].sum().reset_index()
            live_rec['Target'] = CV_TARGET_QUARTERLY
            live_rec['%'] = (live_rec['Sent'] / live_rec['Target'] * 100).round(1)
            st.dataframe(live_rec, hide_index=True, use_container_width=True)

        with col_r2:
            st.subheader("Historical & Annual Totals")
            hist_rec = rec_df[~rec_df['Month'].isin(live_months)].copy()
            if not hist_rec.empty:
                # 按年和季度汇总
                hist_rec['Q'] = hist_rec['Month'].apply(lambda x: f"Q{(int(x[4:6])-1)//3 + 1}")
                summary = hist_rec.groupby(['Year', 'Consultant'])[['Sent', 'Int']].sum().reset_index()
                st.dataframe(summary, hide_index=True, use_container_width=True)

        # --- 2. Financial Performance ---
        st.markdown("<div class='section-head'><h3>💰 Financial Performance</h3></div>", unsafe_allow_html=True)
        col_f1, col_f2 = st.columns(2)

        with col_f1:
            st.subheader(f"Live: {CURRENT_Q_STR}")
            live_sales = sales_df[sales_df['Quarter'] == CURRENT_Q_STR]
            live_fin = live_sales.groupby('Consultant')['GP'].sum().reset_index()
            st.dataframe(live_fin, hide_index=True, use_container_width=True, column_config={"GP": st.column_config.NumberColumn(format="$%d")})

        with col_f2:
            st.subheader("Historical Performance (Yearly Sum)")
            if not sales_df.empty:
                hist_fin = sales_df[sales_df['Quarter'] != CURRENT_Q_STR].groupby(['Year', 'Consultant'])['GP'].sum().reset_index()
                st.dataframe(hist_fin, hide_index=True, use_container_width=True, column_config={"GP": st.column_config.NumberColumn(format="$%d")})

    # ==========================================
    # Tab 2: Details
    # ==========================================
    with tab2:
        for _, member in team_df.iterrows():
            c_name = member['name']
            with st.expander(f"👤 {c_name} - {member['role']}"):
                d_col1, d_col2 = st.columns(2)
                
                with d_col1:
                    st.markdown("#### 🟢 Live (Current Month & Payouts)")
                    # 本月佣金 (2026-01)
                    this_month_deals = sales_df[(sales_df['Consultant'] == c_name) & (sales_df['Onboard Date'].dt.month == 1) & (sales_df['Onboard Date'].dt.year == 2026)]
                    
                    # 上个季度未结算 (2025 Q4 且 Status=Paid 且 支付日在最近)
                    prev_q_pending = sales_df[(sales_df['Consultant'] == c_name) & (sales_df['Quarter'] == "2025 Q4")]
                    
                    st.write(f"**Current Month GP:** ${this_month_deals['GP'].sum():,.2f}")
                    st.write(f"**Prev Q4 Total GP:** ${prev_q_pending['GP'].sum():,.2f}")
                    
                    if not this_month_deals.empty:
                        st.caption("Live Month Deals")
                        st.dataframe(this_month_deals[['Onboard Date', 'GP', 'Status']], hide_index=True)

                with d_col2:
                    st.markdown("#### 📜 Historical Logs")
                    hist_deals = sales_df[(sales_df['Consultant'] == c_name) & (sales_df['Year'] < "2026")]
                    if not hist_deals.empty:
                        st.dataframe(hist_deals.groupby('Quarter')['GP'].sum(), use_container_width=True)
                    
                    st.markdown("---")
                    st.caption("Recruitment History")
                    c_rec = rec_df[rec_df['Consultant'] == c_name].sort_values('Month', ascending=False)
                    st.dataframe(c_rec[['Month', 'Sent', 'Int', 'Off']], hide_index=True)

    st.divider()
    st.caption(f"Last Updated: {st.session_state.get('last_upd', 'Never')}")

if __name__ == "__main__":
    main()

