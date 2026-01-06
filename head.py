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
# 🔧 配置区域 (已更新为 2026 Q1)
# ==========================================
SALES_SHEET_ID = '1jniQ-GpeMINjQMebniJ_J1eLVLQIR1NGbSjTtOFP9Q8'
SALES_TAB_NAME = 'Positions'

# 📅 当前时间定义
CURRENT_YEAR = 2026
CURRENT_QUARTER = 1
CURRENT_Q_STR = f"{CURRENT_YEAR} Q{CURRENT_QUARTER}"
CURRENT_Q_MONTHS = ["202601", "202602", "202603"]

# 🎯 简历目标设置 (季度)
CV_TARGET_QUARTERLY = 87

TEAM_CONFIG = [
    {"name": "Raul Solis", "id": "1vQuN-iNBRUug5J6gBMX-52jp6oogbA77SaeAf9j_zYs", "keyword": "Name", "base_salary": 11000},
    {"name": "Estela Peng", "id": "1sUkffAXzWnpzhhmklqBuwtoQylpR1U18zqBQ-lsp7Z4", "keyword": "姓名", "base_salary": 20800},
    {"name": "Ana Cruz", "id": "1VMVw5YCV12eI8I-VQSXEKg86J2IVZJEgjPJT7ggAFD0", "keyword": "Name", "base_salary": 13000},
    {"name": "Karina Albarran", "id": "1zc4ghvfjIxH0eJ2aXfopOWHqiyTDlD8yFNjBzpH07D8", "keyword": "Name", "base_salary": 15000},
]

st.set_page_config(page_title="2026 Management Dashboard", page_icon="💼", layout="wide")

# --- 🎨 样式 ---
st.markdown("""
    <style>
    .stApp { background-color: #FFFFFF; color: #000000; }
    h1, h2, h3, h4 { color: #333333 !important; font-family: 'Arial', sans-serif; }
    .stButton>button { background-color: #0056b3; color: white; border: none; border-radius: 4px; padding: 10px 24px; font-weight: bold; }
    .dataframe { font-size: 14px !important; }
    div[data-testid="metric-container"] { background-color: #f8f9fa; border: 1px solid #e9ecef; padding: 15px; border-radius: 8px; }
    </style>
    """, unsafe_allow_html=True)

# --- 🛡️ Keep Alive (防止休眠) ---
if 'keep_alive_started' not in st.session_state:
    def keep_alive_worker():
        app_url = st.secrets.get("public_url", None)
        while True:
            try:
                time.sleep(300)
                if app_url: requests.get(app_url, timeout=30)
            except: time.sleep(60)
    threading.Thread(target=keep_alive_worker, daemon=True).start()
    st.session_state['keep_alive_started'] = True

# --- 🧮 核心辅助函数 ---
def get_quarter_str(date_obj):
    if pd.isna(date_obj): return "Unknown"
    q = (date_obj.month - 1) // 3 + 1
    return f"{date_obj.year} Q{q}"

def calculate_commission_tier(total_gp, base_salary, is_tl=False):
    t1, t2, t3 = (4.5, 6.75, 11.25) if is_tl else (9.0, 13.5, 22.5)
    if total_gp < t1 * base_salary: return 0, 0
    elif total_gp < t2 * base_salary: return 1, 1
    elif total_gp < t3 * base_salary: return 2, 2
    else: return 3, 3

def calculate_single_deal_commission(cand_sal, mult):
    if mult == 0: return 0
    if cand_sal < 20000: b = 1000
    elif cand_sal < 30000: b = cand_sal * 0.05
    elif cand_sal < 50000: b = cand_sal * 1.5 * 0.05
    else: b = cand_sal * 2.0 * 0.05
    return b * mult

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

# --- 📥 数据抓取逻辑 ---
def fetch_personal_data(client, conf, tab_name):
    """抓取个人月度简历数据"""
    try:
        sheet = safe_api_call(client.open_by_key, conf['id'])
        ws = safe_api_call(sheet.worksheet, tab_name)
        rows = safe_api_call(ws.get_all_values)
        cs, ci, co = 0, 0, 0
        target_key = conf.get('keyword', 'Name')
        for r in rows:
            if not r: continue
            if r[0].strip() == target_key:
                for v in r[1:]:
                    if v.strip(): cs += 1
            elif r[0].strip() in ["Stage", "Status", "状态", "阶段"]:
                for v in r[1:]:
                    s = v.strip().lower()
                    if s:
                        if "offer" in s: co += 1
                        if "interview" in s or "面试" in s or "offer" in s: ci += 1
        return cs, ci, co
    except: return 0, 0, 0

def fetch_all_sales(client):
    """抓取主销售表 GP 数据"""
    try:
        sheet = safe_api_call(client.open_by_key, SALES_SHEET_ID)
        ws = safe_api_call(sheet.worksheet, SALES_TAB_NAME)
        rows = safe_api_call(ws.get_all_values)
        data = []
        # 简单列查找逻辑
        header = [x.lower() for x in rows[0]]
        c_idx = next(i for i, v in enumerate(header) if "consultant" in v)
        o_idx = next(i for i, v in enumerate(header) if "onboarding" in v)
        s_idx = next(i for i, v in enumerate(header) if "salary" in v)
        p_idx = next(i for i, v in enumerate(header) if "payment" in v and "onboard" not in v)
        
        for r in rows[1:]:
            if len(r) <= max(c_idx, o_idx, s_idx): continue
            name = r[c_idx].strip()
            if not name: continue
            
            # 日期转换
            dt = None
            for fmt in ["%Y-%m-%d", "%d/%m/%Y"]:
                try: dt = datetime.strptime(r[o_idx].strip(), fmt); break
                except: pass
            if not dt: continue
            
            # 顾问匹配
            matched = "Unknown"
            for conf in TEAM_CONFIG:
                if normalize_text(conf['name']) in normalize_text(name): matched = conf['name']; break
            if matched == "Unknown": continue

            try: sal = float(r[s_idx].replace(',','').replace('$','').strip())
            except: sal = 0
            
            gp = sal * (1.5 if sal >= 20000 else 1.0)
            status = "Paid" if len(r[p_idx]) > 5 else "Pending"
            
            data.append({
                "Consultant": matched, "GP": gp, "Candidate Salary": sal,
                "Onboard Date": dt, "Status": status, "Quarter": get_quarter_str(dt)
            })
        return pd.DataFrame(data)
    except: return pd.DataFrame()

# --- 📊 统一渲染组件 (格式完全一致) ---
def render_recruitment_ui(df, team_data, title_prefix=""):
    if df.empty:
        st.info(f"No recruitment data for {title_prefix}")
        return

    summary = df.groupby('Consultant')[['Sent', 'Int', 'Off']].sum().reset_index()
    # 合并角色和目标
    roles_map = {t['name']: t.get('role', 'Consultant') for t in team_data}
    summary['Role'] = summary['Consultant'].map(roles_map)
    summary['CV Target'] = CV_TARGET_QUARTERLY
    summary['Activity %'] = (summary['Sent'] / summary['CV Target']).fillna(0) * 100
    summary['Int Rate'] = (summary['Int'] / summary['Sent']).fillna(0) * 100

    st.dataframe(
        summary, use_container_width=True, hide_index=True,
        column_config={
            "Activity %": st.column_config.ProgressColumn(format="%.0f%%", min_value=0, max_value=100),
            "Int Rate": st.column_config.NumberColumn("Int/Sent", format="%.2f%%"),
            "Sent": st.column_config.NumberColumn(help="Total CVs Sent")
        }
    )

def render_financial_ui(sales_df, rec_df, team_data, title_prefix=""):
    fin_list = []
    for conf in team_data:
        c_name = conf['name']
        role = conf.get('role', 'Consultant')
        base = conf['base_salary']
        is_tl = (role == "Team Lead")
        is_in = (role == "Intern")
        
        target_gp = 0 if is_in else base * (4.5 if is_tl else 9.0)
        
        c_sales = sales_df[sales_df['Consultant'] == c_name] if not sales_df.empty else pd.DataFrame()
        booked_gp = c_sales['GP'].sum()
        paid_gp = c_sales[c_sales['Status'] == 'Paid']['GP'].sum()
        
        sent = rec_df[rec_df['Consultant'] == c_name]['Sent'].sum() if not rec_df.empty else 0
        rec_pct = (sent / CV_TARGET_QUARTERLY * 100)
        fin_pct = (booked_gp / target_gp * 100) if target_gp > 0 else 0
        
        # 达标逻辑
        met = (rec_pct >= 100) if is_in else (fin_pct >= 100 or rec_pct >= 100)
        
        # 佣金
        comm = 0
        if not is_in and met:
            _, mult = calculate_commission_tier(paid_gp, base, is_tl)
            paid_deals = c_sales[c_sales['Status'] == 'Paid']
            for _, row in paid_deals.iterrows():
                comm += calculate_single_deal_commission(row['Candidate Salary'], mult)

        fin_list.append({
            "Consultant": c_name, "Role": role, "GP Target": target_gp, "Paid GP": paid_gp,
            "Fin %": fin_pct, "Status": "Met" if met else "In Progress", "Est. Commission": comm
        })

    df_fin = pd.DataFrame(fin_list).sort_values("Paid GP", ascending=False)
    st.dataframe(
        df_fin, use_container_width=True, hide_index=True,
        column_config={
            "GP Target": st.column_config.NumberColumn(format="$%d"),
            "Paid GP": st.column_config.NumberColumn(format="$%d"),
            "Fin %": st.column_config.ProgressColumn("Financial % (Booked)", format="%.0f%%", min_value=0, max_value=100),
            "Est. Commission": st.column_config.NumberColumn("Payable Comm.", format="$%d")
        }
    )

# --- 🚀 主页面 ---
def main():
    st.title(f"💼 Management Dashboard - {CURRENT_Q_STR}")
    
    client = connect_to_google()
    if not client: st.error("API Connection Failed"); return

    if st.button("🔄 REFRESH 2026 Q1 DATA", type="primary"):
        with st.spinner("Fetching Live Data..."):
            # 1. 更新角色
            team = []
            for c in TEAM_CONFIG:
                m = c.copy(); m['role'] = fetch_personal_data_role = fetch_role_from_personal_sheet(client, c['id'])
                team.append(m)
            
            # 2. 抓取 Q1 数据
            stats_q1 = []
            for m in CURRENT_Q_MONTHS:
                for c in team:
                    s, i, o = fetch_personal_data(client, c, m)
                    stats_q1.append({"Consultant": c['name'], "Month": m, "Sent": s, "Int": i, "Off": o, "Quarter": CURRENT_Q_STR})
            
            # 3. 抓取历史数据 (例如 2025 Q4)
            stats_hist = []
            for m in ["202510", "202511", "202512"]:
                for c in team:
                    s, i, o = fetch_personal_data(client, c, m)
                    stats_hist.append({"Consultant": c['name'], "Month": m, "Sent": s, "Int": i, "Off": o, "Quarter": "2025 Q4"})

            st.session_state['data_2026'] = {
                "team": team, 
                "stats_q1": pd.DataFrame(stats_q1),
                "stats_hist": pd.DataFrame(stats_hist),
                "sales_all": fetch_all_sales(client),
                "last_upd": datetime.now().strftime("%H:%M:%S")
            }
            st.rerun()

    if 'data_2026' not in st.session_state:
        st.info("Click Refresh to load 2026 Q1 report."); st.stop()

    cache = st.session_state['data_2026']
    
    tab_dash, tab_det = st.tabs(["📊 DASHBOARD", "📝 DETAILS"])

    with tab_dash:
        # --- Recruitment Section ---
        st.subheader(f"🎯 Recruitment Stats ({CURRENT_Q_STR})")
        render_recruitment_ui(cache['stats_q1'], cache['team'])
        
        with st.expander("📜 Historical Recruitment (2025 Q4 & Older)"):
            for q in cache['stats_hist']['Quarter'].unique():
                st.write(f"**{q}**")
                render_recruitment_ui(cache['stats_hist'][cache['stats_hist']['Quarter'] == q], cache['team'])

        st.divider()

        # --- Financial Section ---
        st.subheader(f"💰 Financial Performance ({CURRENT_Q_STR})")
        q1_sales = cache['sales_all'][cache['sales_all']['Quarter'] == CURRENT_Q_STR] if not cache['sales_all'].empty else pd.DataFrame()
        render_financial_ui(q1_sales, cache['stats_q1'], cache['team'])
        
        with st.expander("📜 Historical Financial (2025 & Older)"):
            if not cache['sales_all'].empty:
                hist_qs = sorted([q for q in cache['sales_all']['Quarter'].unique() if q != CURRENT_Q_STR], reverse=True)
                for q in hist_qs:
                    st.write(f"**{q}**")
                    h_sales = cache['sales_all'][cache['sales_all']['Quarter'] == q]
                    # 历史对比时，如果找不到对应的简历数据，传空表
                    h_rec = cache['stats_hist'][cache['stats_hist']['Quarter'] == q] if q == "2025 Q4" else pd.DataFrame()
                    render_financial_ui(h_sales, h_rec, cache['team'])

    with tab_det:
        st.write("Detailed recruitment logs per consultant:")
        # 这里可以放置原来的具体日志代码...

def fetch_role_from_personal_sheet(client, sheet_id):
    try:
        sheet = safe_api_call(client.open_by_key, sheet_id)
        ws = safe_api_call(sheet.worksheet, 'Credentials')
        return safe_api_call(ws.acell, 'B1').value.strip()
    except: return "Consultant"

if __name__ == "__main__":
    main()
