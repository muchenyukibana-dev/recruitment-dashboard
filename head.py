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

# ==========================================
# 🔧 1. 自动时间配置 (实时变更)
# ==========================================
now = datetime.now()
CURRENT_YEAR = now.year
CURRENT_QUARTER = (now.month - 1) // 3 + 1
CURRENT_Q_STR = f"{CURRENT_YEAR} Q{CURRENT_QUARTER}"

# 自动计算当前季度的月份列表 (例如 202601, 202602, 202603)
start_month_val = (CURRENT_QUARTER - 1) * 3 + 1
CURRENT_QUARTER_MONTHS = [f"{CURRENT_YEAR}{m:02d}" for m in range(start_month_val, start_month_val + 3)]

# ==========================================
# ⚙️ 2. 基础配置
# ==========================================
SALES_SHEET_ID = '1jniQ-GpeMINjQMebniJ_J1eLVLQIR1NGbSjTtOFP9Q8'
SALES_TAB_NAME = 'Positions'
CV_TARGET_QUARTERLY = 87

TEAM_CONFIG = [
    {"name": "Raul Solis", "id": "1vQuN-iNBRUug5J6gBMX-52jp6oogbA77SaeAf9j_zYs", "keyword": "Name", "base_salary": 11000},
    {"name": "Estela Peng", "id": "1sUkffAXzWnpzhhmklqBuwtoQylpR1U18zqBQ-lsp7Z4", "keyword": "姓名", "base_salary": 20800},
    {"name": "Ana Cruz", "id": "1VMVw5YCV12eI8I-VQSXEKg86J2IVZJEgjPJT7ggAFD0", "keyword": "Name", "base_salary": 13000},
    {"name": "Karina Albarran", "id": "1zc4ghvfjIxH0eJ2aXfopOWHqiyTDlD8yFNjBzpH07D8", "keyword": "Name", "base_salary": 15000},
]

st.set_page_config(page_title="Management Dashboard", page_icon="💼", layout="wide")

# --- 🎨 样式 ---
st.markdown("""
    <style>
    .stApp { background-color: #FFFFFF; color: #000000; }
    h2 { color: #0056b3 !important; border-bottom: 2px solid #eee; padding-bottom: 10px; margin-top: 20px;}
    .dataframe { font-size: 12px !important; }
    </style>
    """, unsafe_allow_html=True)

# ==========================================
# 🧮 3. 核心工具函数 (从原 supervisor.py 搬运并优化)
# ==========================================
def get_quarter_str(date_obj):
    if pd.isna(date_obj): return "Unknown"
    q = (date_obj.month - 1) // 3 + 1
    return f"{date_obj.year} Q{q}"

def normalize_text(text):
    return ''.join(c for c in unicodedata.normalize('NFD', str(text)) if unicodedata.category(c) != 'Mn').lower()

def safe_api_call(func, *args, **kwargs):
    for i in range(5):
        try: return func(*args, **kwargs)
        except Exception as e:
            if "429" in str(e): time.sleep(2 * (2 ** i))
            else: raise e
    return None

def connect_to_google():
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    if "gcp_service_account" in st.secrets:
        try:
            creds = ServiceAccountCredentials.from_json_keyfile_dict(dict(st.secrets["gcp_service_account"]), scope)
            return gspread.authorize(creds)
        except: return None
    return None

# ==========================================
# 📥 4. 数据抓取核心逻辑
# ==========================================

def internal_fetch_sheet_data(client, conf, tab_name):
    """抓取单个顾问在特定月份的面试/发人数据"""
    try:
        sheet = safe_api_call(client.open_by_key, conf['id'])
        ws = safe_api_call(sheet.worksheet, tab_name)
        rows = safe_api_call(ws.get_all_values)
        
        cs, ci, co = 0, 0, 0
        target_key = conf.get('keyword', 'Name')
        
        # 简化的状态统计逻辑
        for r in rows:
            if not r: continue
            row_str = " ".join(r).lower()
            if target_key.lower() in row_str: # 发现人名行
                for val in r[1:]:
                    if val.strip(): cs += 1 # 只要有名字就算 Sent
            if "stage" in row_str or "status" in row_str or "状态" in row_str: # 发现状态行
                for val in r[1:]:
                    v = val.lower()
                    if "interview" in v or "面试" in v: ci += 1
                    if "offer" in v: ci += 1; co += 1
        return cs, ci, co
    except: return 0, 0, 0

def fetch_all_sales_data(client):
    """从主表中获取所有销售数据"""
    try:
        sheet = safe_api_call(client.open_by_key, SALES_SHEET_ID)
        ws = safe_api_call(sheet.worksheet, SALES_TAB_NAME)
        rows = safe_api_call(ws.get_all_values)
        
        # 寻找表头索引
        header = [r.lower() for r in rows[0]]
        col_cons = next(i for i, v in enumerate(header) if "consultant" in v)
        col_onboard = next(i for i, v in enumerate(header) if "onboarding" in v)
        col_sal = next(i for i, v in enumerate(header) if "salary" in v)
        col_pay = next(i for i, v in enumerate(header) if "payment" in v)
        
        sales_records = []
        for row in rows[1:]:
            if len(row) < 5 or not row[col_cons]: continue
            
            # 名字模糊匹配
            matched = "Unknown"
            c_norm = normalize_text(row[col_cons])
            for conf in TEAM_CONFIG:
                if normalize_text(conf['name']) in c_norm: matched = conf['name']; break
            
            if matched == "Unknown": continue
            
            # 日期转换
            try: 
                ob_date = pd.to_datetime(row[col_onboard])
                sal = float(str(row[col_sal]).replace(',','').replace('$','').strip())
            except: continue

            calc_gp = sal * (1.0 if sal < 20000 else 1.5)
            status = "Paid" if len(row[col_pay].strip()) > 5 else "Pending"
            
            sales_records.append({
                "Consultant": matched, "GP": calc_gp, "Status": status,
                "Quarter": get_quarter_str(ob_date), "Date": ob_date
            })
        return pd.DataFrame(sales_records)
    except: return pd.DataFrame()

def load_data_package(client):
    """一键加载所有数据包"""
    # 1. 获取 Role
    role_map = {}
    for conf in TEAM_CONFIG:
        try:
            s = client.open_by_key(conf['id'])
            role_map[conf['name']] = s.worksheet('Credentials').acell('B1').value.strip()
        except: role_map[conf['name']] = "Consultant"
    
    # 2. 当前季度招聘
    rec_curr = []
    for m in CURRENT_QUARTER_MONTHS:
        for conf in TEAM_CONFIG:
            s, i, o = internal_fetch_sheet_data(client, conf, m)
            rec_curr.append({"Consultant": conf['name'], "Sent": s, "Int": i, "Off": o})
    
    # 3. 历史招聘 (抓取所有 6 位数字的页签，排除当前的)
    rec_hist = []
    try:
        ref_sheet = client.open_by_key(TEAM_CONFIG[0]['id'])
        all_tabs = [ws.title for ws in ref_sheet.worksheets() if ws.title.isdigit() and len(ws.title)==6]
        hist_tabs = [t for t in all_tabs if t not in CURRENT_QUARTER_MONTHS]
        for t in hist_tabs:
            q_label = f"{t[:4]} Q{(int(t[4:])-1)//3+1}"
            for conf in TEAM_CONFIG:
                s, i, o = internal_fetch_sheet_data(client, conf, t)
                if s+i+o > 0: rec_hist.append({"Consultant": conf['name'], "Quarter": q_label, "Sent": s, "Int": i, "Off": o})
    except: pass

    # 4. 销售数据
    sales_all = fetch_all_sales_data(client)

    return {
        "roles": role_map,
        "rec_curr": pd.DataFrame(rec_curr),
        "rec_hist": pd.DataFrame(rec_hist),
        "sales": sales_all,
        "ts": datetime.now().strftime("%H:%M:%S")
    }

# ==========================================
# 📊 5. 页面渲染逻辑
# ==========================================

def render_rec_table(df, title):
    st.subheader(title)
    if df.empty: st.info("No records."); return
    
    summary = df.groupby('Consultant')[['Sent', 'Int', 'Off']].sum().reset_index()
    summary['Target'] = CV_TARGET_QUARTERLY
    summary['Activity %'] = (summary['Sent'] / summary['Target'] * 100).clip(0, 100)
    summary['Int Rate'] = (summary['Int'] / summary['Sent'] * 100).fillna(0)
    
    st.dataframe(summary, use_container_width=True, hide_index=True,
                 column_config={
                     "Activity %": st.column_config.ProgressColumn(format="%.0f%%"),
                     "Int Rate": st.column_config.NumberColumn(format="%.1f%%")
                 })

def main():
    st.title("💼 Management Dashboard")
    st.caption(f"System Date: {datetime.now().strftime('%Y-%m-%d')} | Active Quarter: **{CURRENT_Q_STR}**")

    client = connect_to_google()
    if not client: st.error("API Connection Error"); return

    if st.button("🔄 REFRESH DATA", type="primary"):
        with st.spinner("Loading..."):
            st.session_state['db'] = load_data_package(client)
            st.rerun()

    if 'db' not in st.session_state:
        st.info("Please Refresh Data to start.")
        return

    db = st.session_state['db']
    tab_rec, tab_fin = st.tabs(["📊 RECRUITMENT", "💰 FINANCIAL"])

    # --- TAB 1: RECRUITMENT ---
    with tab_rec:
        render_rec_table(db['rec_curr'], f"Current Quarter Activity ({CURRENT_Q_STR})")
        
        st.markdown("### Historical Quarters")
        if not db['rec_hist'].empty:
            q_list = sorted(db['rec_hist']['Quarter'].unique(), reverse=True)
            for q in q_list:
                with st.expander(f"📜 {q} Details"):
                    render_rec_table(db['rec_hist'][db['rec_hist']['Quarter'] == q], f"Stats - {q}")
        else: st.write("No history.")

    # --- TAB 2: FINANCIAL ---
    with tab_fin:
        # 当前季度财务
        st.subheader(f"Current Financials ({CURRENT_Q_STR})")
        sales_curr = db['sales'][db['sales']['Quarter'] == CURRENT_Q_STR] if not db['sales'].empty else pd.DataFrame()
        
        fin_list = []
        for conf in TEAM_CONFIG:
            role = db['roles'].get(conf['name'], "Consultant")
            target = 0 if role == "Intern" else conf['base_salary'] * (4.5 if role == "Team Lead" else 9.0)
            booked = sales_curr[sales_curr['Consultant'] == conf['name']]['GP'].sum() if not sales_curr.empty else 0
            fin_list.append({
                "Consultant": conf['name'], "Role": role, "Target": target, 
                "Booked GP": booked, "Progress": (booked/target*100 if target>0 else 0)
            })
        
        st.dataframe(pd.DataFrame(fin_list), use_container_width=True, hide_index=True,
                     column_config={"Progress": st.column_config.ProgressColumn(format="%.0f%%"),
                                   "Target": st.column_config.NumberColumn(format="$%d"),
                                   "Booked GP": st.column_config.NumberColumn(format="$%d")})

        # 历史财务
        st.markdown("### Historical Financials")
        if not db['sales'].empty:
            hist_sales = db['sales'][db['sales']['Quarter'] != CURRENT_Q_STR]
            if not hist_sales.empty:
                hist_fin = hist_sales.groupby(['Quarter', 'Consultant'])['GP'].sum().reset_index()
                st.dataframe(hist_fin.sort_values(['Quarter', 'Consultant'], ascending=[False, True]), 
                             use_container_width=True, hide_index=True,
                             column_config={"GP": st.column_config.NumberColumn(format="$%d")})

if __name__ == "__main__":
    main()
