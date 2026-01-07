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
# 🔧 1. 自动化配置区域 (2026 Q1 自动生效)
# ==========================================
now = datetime.now()
CURRENT_YEAR = now.year
CURRENT_QUARTER = (now.month - 1) // 3 + 1
CURRENT_Q_STR = f"{CURRENT_YEAR} Q{CURRENT_QUARTER}"

# 自动计算当前季度的起始和结束月份 (Q1: 1-3, Q2: 4-6...)
start_m = (CURRENT_QUARTER - 1) * 3 + 1
end_m = start_m + 2
quarter_months_str = [f"{CURRENT_YEAR}{m:02d}" for m in range(start_m, end_m + 1)]

SALES_SHEET_ID = '1jniQ-GpeMINjQMebniJ_J1eLVLQIR1NGbSjTtOFP9Q8'
SALES_TAB_NAME = 'Positions'
CV_TARGET_QUARTERLY = 87

TEAM_CONFIG = [
    {"name": "Raul Solis", "id": "1vQuN-iNBRUug5J6gBMX-52jp6oogbA77SaeAf9j_zYs", "keyword": "Name", "base_salary": 11000},
    {"name": "Estela Peng", "id": "1sUkffAXzWnpzhhmklqBuwtoQylpR1U18zqBQ-lsp7Z4", "keyword": "姓名", "base_salary": 20800},
    {"name": "Ana Cruz", "id": "1VMVw5YCV12eI8I-VQSXEKg86J2IVZJEgjPJT7ggAFD0", "keyword": "Name", "base_salary": 13000},
    {"name": "Karina Albarran", "id": "1zc4ghvfjIxH0eJ2aXfopOWHqiyTDlD8yFNjBzpH07D8", "keyword": "Name", "base_salary": 15000},
]

st.set_page_config(page_title=f"Dashboard {CURRENT_Q_STR}", page_icon="💼", layout="wide")

# --- 🎨 样式 ---
st.markdown("""
    <style>
    .stApp { background-color: #FFFFFF; color: #000000; }
    h3 { color: #0056b3 !important; border-bottom: 2px solid #eee; padding-bottom: 10px; }
    .stButton>button { background-color: #0056b3; color: white; border-radius: 4px; font-weight: bold; }
    div[data-testid="metric-container"] { background-color: #f8f9fa; border: 1px solid #e9ecef; border-radius: 8px; padding: 15px; }
    </style>
    """, unsafe_allow_html=True)

# --- 🛠️ 辅助计算函数 ---
def get_quarter_str(date_obj):
    if pd.isna(date_obj): return "Unknown"
    return f"{date_obj.year} Q{(date_obj.month - 1) // 3 + 1}"

def calculate_commission_tier(total_gp, base_salary, is_tl=False):
    t1, t2, t3 = (4.5, 6.75, 11.25) if is_tl else (9.0, 13.5, 22.5)
    if total_gp < t1 * base_salary: return 0, 0
    elif total_gp < t2 * base_salary: return 1, 1
    elif total_gp < t3 * base_salary: return 2, 2
    return 3, 3

def calculate_single_deal_commission(cand_sal, mult):
    if mult == 0: return 0
    if cand_sal < 20000: b = 1000
    elif cand_sal < 30000: b = cand_sal * 0.05
    elif cand_sal < 50000: b = cand_sal * 1.5 * 0.05
    else: b = cand_sal * 2.0 * 0.05
    return b * mult

def get_commission_pay_date(payment_date):
    if pd.isna(payment_date): return None
    try:
        y, m = payment_date.year + (payment_date.month // 12), (payment_date.month % 12) + 1
        return datetime(y, m, 15)
    except: return None

def get_payout_date_from_month_key(month_key):
    try:
        dt = datetime.strptime(str(month_key), "%Y-%m")
        y, m = dt.year + (dt.month // 12), (dt.month % 12) + 1
        return datetime(y, m, 15)
    except: return None

def normalize_text(text):
    return ''.join(c for c in unicodedata.normalize('NFD', str(text)) if unicodedata.category(c) != 'Mn').lower()

# --- 📊 统一渲染函数 (确保格式 100% 一致) ---
def render_recruitment_table(df, team_data):
    if df.empty: st.warning("No data found."); return
    summary = df.groupby('Consultant')[['Sent', 'Int', 'Off']].sum().reset_index()
    roles = {t['name']: t.get('role', 'Consultant') for t in team_data}
    summary['Role'] = summary['Consultant'].map(roles)
    summary['CV Target'] = CV_TARGET_QUARTERLY
    summary['Activity %'] = (summary['Sent'] / summary['CV Target']).fillna(0) * 100
    summary['Int Rate'] = (summary['Int'] / summary['Sent']).fillna(0) * 100
    
    # Total Row
    total = pd.DataFrame([{
        'Consultant': 'TOTAL', 'Role': '-', 'CV Target': summary['CV Target'].sum(),
        'Sent': summary['Sent'].sum(), 'Int': summary['Int'].sum(), 'Off': summary['Off'].sum(),
        'Activity %': (summary['Sent'].sum() / summary['CV Target'].sum() * 100) if summary['CV Target'].sum() > 0 else 0,
        'Int Rate': (summary['Int'].sum() / summary['Sent'].sum() * 100) if summary['Sent'].sum() > 0 else 0
    }])
    summary = pd.concat([summary, total], ignore_index=True)
    st.dataframe(summary, use_container_width=True, hide_index=True, column_config={
        "Activity %": st.column_config.ProgressColumn(format="%.0f%%", min_value=0, max_value=100),
        "Int Rate": st.column_config.NumberColumn("Int/Sent", format="%.2f%%")
    })

def render_financial_performance(sales_df, rec_stats_df, team_data):
    financial_summary, updated_sales, tl_overrides = [], [], []
    
    # --- 🛡️ 保护逻辑：如果 sales_df 为空，给它预设列名，防止 KeyError ---
    if sales_df.empty:
        # 创建一个带有必要列名的空 DataFrame
        sales_df = pd.DataFrame(columns=['Consultant', 'GP', 'Status', 'Candidate Salary', 'Percentage', 'Payment Date Obj'])
    # -------------------------------------------------------------

    for conf in team_data:
        c_name, base, role = conf['name'], conf['base_salary'], conf.get('role', 'Consultant')
        is_tl, is_in = (role == "Team Lead"), (role == "Intern")
        gp_target = 0 if is_in else base * (4.5 if is_tl else 9.0)
        
        # 即使 sales_df 没数据，现在 c_sales 也会包含正确的列名，不会报错
        c_sales = sales_df[sales_df['Consultant'] == c_name].copy()
        
        sent = rec_stats_df[rec_stats_df['Consultant'] == c_name]['Sent'].sum() if not rec_stats_df.empty else 0
        
        # 这里是之前报错的地方，现在加了判断
        booked_gp = c_sales['GP'].sum() if 'GP' in c_sales.columns else 0
        fin_pct = (booked_gp / gp_target * 100) if gp_target > 0 else 0
        rec_pct = (sent / CV_TARGET_QUARTERLY * 100)
        met = (rec_pct >= 100) if is_in else (fin_pct >= 100 or rec_pct >= 100)
        
        # --- # Comm Calculation --- (这里是之后的提成计算)
        comm, paid_gp, level = 0, 0, 0
        if not is_in and not c_sales.empty:
            # 确保列名存在
            for col in ['Applied Level', 'Final Comm', 'Commission Day']:
                if col not in c_sales.columns: c_sales[col] = 0
            
            paid = c_sales[c_sales['Status'] == 'Paid'].copy()
            if not paid.empty:
                paid['Payment Date Obj'] = pd.to_datetime(paid['Payment Date Obj'])
                paid = paid.sort_values('Payment Date Obj')
                paid['MonthKey'] = paid['Payment Date Obj'].dt.to_period('M')
                run_gp = 0; pending_idx = []
                for m_key in sorted(paid['MonthKey'].unique()):
                    m_deals = paid[paid['MonthKey'] == m_key]
                    run_gp += m_deals['GP'].sum(); pending_idx.extend(m_deals.index.tolist())
                    lvl, mult = calculate_commission_tier(run_gp, base, is_tl)
                    if lvl > 0:
                        p_date = get_payout_date_from_month_key(str(m_key))
                        for idx in pending_idx:
                            row = paid.loc[idx]
                            deal_comm = calculate_single_deal_commission(row['Candidate Salary'], mult) * row['Percentage']
                            paid.at[idx, 'Applied Level'] = lvl
                            paid.at[idx, 'Commission Day Obj'] = p_date
                            paid.at[idx, 'Final Comm'] = deal_comm if met else 0
                        pending_idx = []
                paid_gp, (level, _) = run_gp, calculate_commission_tier(run_gp, base, is_tl)
                for _, row in paid.iterrows():
                    # 只有达标且到了发放日期的才汇总
                    if met and pd.notnull(row.get('Commission Day Obj')) and row['Commission Day Obj'] <= datetime.now() + timedelta(days=20):
                        comm += row['Final Comm']
                c_sales.update(paid)
            updated_sales.append(c_sales)
            
        financial_summary.append({
            "Consultant": c_name, "Role": role, "GP Target": gp_target, "Paid GP": paid_gp, 
            "Fin %": fin_pct, "Status": "Met" if met else "In Progress", "Level": level, "Est. Commission": comm
        })

# 渲染汇总表
df_fin = pd.DataFrame(financial_summary).sort_values('Paid GP', ascending=False)
    st.dataframe(df_fin, use_container_width=True, hide_index=True, column_config={
        "GP Target": st.column_config.NumberColumn(format="$%d"),
        "Paid GP": st.column_config.NumberColumn(format="$%d"),
        "Fin %": st.column_config.ProgressColumn("Fin % (Booked)", format="%.0f%%", min_value=0, max_value=100),
        "Est. Commission": st.column_config.NumberColumn("Payable Comm.", format="$%d")
    })
    return pd.concat(updated_sales) if updated_sales else pd.DataFrame()

# --- 📥 数据获取逻辑 (优化提速) ---
def safe_api_call(func, *args, **kwargs):
    for i in range(5):
        try: return func(*args, **kwargs)
        except APIError as e:
            if "429" in str(e): time.sleep(2**i + random.random())
            else: raise e
    return None

def connect_to_google():
    try:
        scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
        creds = ServiceAccountCredentials.from_json_keyfile_dict(dict(st.secrets["gcp_service_account"]), scope)
        return gspread.authorize(creds)
    except: return None

def fetch_recruitment_stats(client, months):
    all_stats = []
    for m in months:
        for c in TEAM_CONFIG:
            s, i, o, _ = internal_fetch_sheet_data(client, c, m)
            all_stats.append({"Consultant": c['name'], "Month": m, "Sent": s, "Int": i, "Off": o})
    return pd.DataFrame(all_stats)

def fetch_historical_recruitment_stats(client, exclude_months):
    all_stats = []
    try:
        sheet = client.open_by_key(TEAM_CONFIG[0]['id'])
        # 🚀 提速关键：只搜索最近6个月的历史记录
        all_ws = [ws.title for ws in sheet.worksheets() if ws.title.isdigit() and len(ws.title)==6]
        hist_months = sorted([m for m in all_ws if m not in exclude_months], reverse=True)[:6]
        for m in hist_months:
            for c in TEAM_CONFIG:
                s, i, o, _ = internal_fetch_sheet_data(client, c, m)
                if s+i+o > 0: all_stats.append({"Consultant": c['name'], "Month": m, "Sent": s, "Int": i, "Off": o})
        return pd.DataFrame(all_stats)
    except: return pd.DataFrame()

def internal_fetch_sheet_data(client, conf, tab):
    try:
        sheet = safe_api_call(client.open_by_key, conf['id'])
        ws = safe_api_call(sheet.worksheet, tab)
        rows = safe_api_call(ws.get_all_values)
        cs, ci, co = 0, 0, 0
        target = conf.get('keyword', 'Name')
        for r in rows:
            if not r: continue
            if r[0].strip() == target:
                cs += len([v for v in r[1:] if v.strip()])
            elif r[0].strip() in ["Stage", "Status", "状态", "阶段"]:
                for v in r[1:]:
                    s = v.strip().lower()
                    if s:
                        if "offer" in s: co += 1
                        if "interview" in s or "面试" in s or "offer" in s: ci += 1
        return cs, ci, co, []
    except: return 0, 0, 0, []

def fetch_all_sales_data(client):
    try:
        sheet = client.open_by_key(SALES_SHEET_ID)
        ws = sheet.worksheet(SALES_TAB_NAME)
        rows = ws.get_all_values()
        header = [x.lower() for x in rows[0]]
        c_idx = next(i for i,v in enumerate(header) if "consultant" in v)
        o_idx = next(i for i,v in enumerate(header) if "onboarding" in v)
        s_idx = next(i for i,v in enumerate(header) if "salary" in v)
        p_idx = next(i for i,v in enumerate(header) if "payment" in v and "onboard" not in v)
        pct_idx = next((i for i,v in enumerate(header) if "percentage" in v or v=="%"), -1)
        
        data = []
        for r in rows[1:]:
            if len(r) <= max(c_idx, o_idx, s_idx): continue
            dt = None
            for fmt in ["%Y-%m-%d", "%d/%m/%Y"]:
                try: dt = datetime.strptime(r[o_idx].strip(), fmt); break
                except: pass
            if not dt: continue
            
            matched = "Unknown"
            for conf in TEAM_CONFIG:
                if normalize_text(conf['name']) in normalize_text(r[c_idx]): matched = conf['name']; break
            if matched == "Unknown": continue

            try: sal = float(r[s_idx].replace(',','').replace('$','').strip())
            except: sal = 0
            
            pct = 1.0
            if pct_idx != -1:
                try: 
                    p = float(r[pct_idx].replace('%','').strip())
                    pct = p/100.0 if p > 1.0 else p
                except: pct = 1.0

            data.append({
                "Consultant": matched, "GP": sal * (1.5 if sal >= 20000 else 1.0) * pct, "Percentage": pct,
                "Candidate Salary": sal, "Onboard Date": dt, "Status": "Paid" if len(r[p_idx]) > 5 else "Pending",
                "Payment Date Obj": dt if len(r[p_idx]) > 5 else None, "Quarter": get_quarter_str(dt)
            })
        return pd.DataFrame(data)
    except: return pd.DataFrame()

def load_data_from_api(client, months):
    team = []
    for c in TEAM_CONFIG:
        m = c.copy(); m['role'] = fetch_role_from_personal_sheet(client, c['id'])
        team.append(m); time.sleep(0.4)
    rec_stats = fetch_recruitment_stats(client, months)
    rec_hist = fetch_historical_recruitment_stats(client, months)
    sales = fetch_all_sales_data(client)
    return {"team": team, "rec_stats": rec_stats, "rec_hist": rec_hist, "sales": sales, "upd": datetime.now().strftime("%H:%M")}

def fetch_role_from_personal_sheet(client, sid):
    try:
        sheet = client.open_by_key(sid); ws = sheet.worksheet('Credentials')
        return ws.acell('B1').value.strip()
    except: return "Consultant"

# --- 🚀 主程序 ---
def main():
    st.title(f"💼 Management Dashboard - {CURRENT_Q_STR}")
    client = connect_to_google()
    if not client: st.error("API Error"); return

    if st.button("🔄 REFRESH DATA", type="primary"):
        with st.spinner("⏳ Syncing Google Sheets..."):
            cache = load_data_from_api(client, quarter_months_str)
            st.session_state['data_cache'] = cache
            st.rerun()

    if 'data_cache' not in st.session_state:
        st.info(f"👋 Welcome! Click REFRESH to load {CURRENT_Q_STR} report."); st.stop()

    cache = st.session_state['data_cache']
    all_sales = cache['sales']
    
    # --- 数据分拣 (2026 Q1) ---
    if not all_sales.empty:
        all_sales['Onboard Date'] = pd.to_datetime(all_sales['Onboard Date'])
        mask = (all_sales['Onboard Date'].dt.year == CURRENT_YEAR) & (all_sales['Onboard Date'].dt.month >= start_m) & (all_sales['Onboard Date'].dt.month <= end_m)
        sales_cur = all_sales[mask].copy()
        sales_hist = all_sales[~mask].copy()
    else: sales_cur = sales_hist = pd.DataFrame()

    tab_dash, tab_det = st.tabs(["📊 DASHBOARD", "📝 DETAILS"])

    with tab_dash:
        # --- Recruitment Section ---
        st.markdown(f"### 🎯 Recruitment Stats ({CURRENT_Q_STR})")
        render_recruitment_table(cache['rec_stats'], cache['team'])
        with st.expander("📜 Historical Recruitment (Identical Format)"):
            render_recruitment_table(cache['rec_hist'], cache['team'])

        st.divider()

        # --- Financial Section ---
        st.markdown(f"### 💰 Financial Performance ({CURRENT_Q_STR})")
        # 调试诊断信息
        if sales_cur.empty: st.warning(f"No 2026 Q1 records found in master sheet (Target: {start_m}-{end_m}月)")
        else: st.write(f"DEBUG: Found {len(sales_cur)} records for {CURRENT_Q_STR}")
        
        final_sales_df = render_financial_performance(sales_cur, cache['rec_stats'], cache['team'])

        with st.expander("📜 Historical Financial (Identical Format)"):
            if not sales_hist.empty:
                for q in sorted(sales_hist['Quarter'].unique(), reverse=True):
                    st.write(f"**{q}**")
                    render_financial_performance(sales_hist[sales_hist['Quarter']==q], pd.DataFrame(), cache['team'])
            else: st.info("No historical sales data.")

    with tab_det:
        st.markdown("### 🔍 Details per Consultant")
        for conf in cache['team']:
            with st.expander(f"👤 {conf['name']}"):
                if not final_sales_df.empty:
                    my_sales = final_sales_df[final_sales_df['Consultant'] == conf['name']]
                    if not my_sales.empty: st.dataframe(my_sales, use_container_width=True)
                st.info("Logs below...")

if __name__ == "__main__":
    main()
