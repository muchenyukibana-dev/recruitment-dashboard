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
# 🔧 核心配置 (时间逻辑已全自动化)
# ==========================================
now = datetime.now()
CURRENT_YEAR = now.year
CURRENT_QUARTER = (now.month - 1) // 3 + 1
CURRENT_Q_STR = f"{CURRENT_YEAR} Q{CURRENT_QUARTER}"

# 动态生成当前季度的月份列表 (例如: ['202601', '202602', '202603'])
start_month_of_q = (CURRENT_QUARTER - 1) * 3 + 1
CURRENT_Q_MONTHS = [f"{CURRENT_YEAR}{m:02d}" for m in range(start_month_of_q, start_month_of_q + 3)]

# 动态计算上一个季度 (用于历史对比展示)
first_day_this_q = datetime(CURRENT_YEAR, start_month_of_q, 1)
last_day_prev_q = first_day_this_q - timedelta(days=1)
PREV_Q_YEAR = last_day_prev_q.year
PREV_Q_NUM = (last_day_prev_q.month - 1) // 3 + 1
PREV_Q_STR = f"{PREV_Q_YEAR} Q{PREV_Q_NUM}"
PREV_Q_MONTHS = [f"{PREV_Q_YEAR}{m:02d}" for m in range((PREV_Q_NUM-1)*3 + 1, (PREV_Q_NUM-1)*3 + 4)]

SALES_SHEET_ID = '1jniQ-GpeMINjQMebniJ_J1eLVLQIR1NGbSjTtOFP9Q8'
SALES_TAB_NAME = 'Positions'
CV_TARGET_QUARTERLY = 87

TEAM_CONFIG = [
    {"name": "Raul Solis", "id": "1vQuN-iNBRUug5J6gBMX-52jp6oogbA77SaeAf9j_zYs", "keyword": "Name", "base_salary": 11000},
    {"name": "Estela Peng", "id": "1sUkffAXzWnpzhhmklqBuwtoQylpR1U18zqBQ-lsp7Z4", "keyword": "姓名", "base_salary": 20800},
    {"name": "Ana Cruz", "id": "1VMVw5YCV12eI8I-VQSXEKg86J2IVZJEgjPJT7ggAFD0", "keyword": "Name", "base_salary": 13000},
    {"name": "Karina Albarran", "id": "1zc4ghvfjIxH0eJ2aXfopOWHqiyTDlD8yFNjBzpH07D8", "keyword": "Name", "base_salary": 15000},
]

st.set_page_config(page_title=f"Management Dashboard {CURRENT_Q_STR}", page_icon="💼", layout="wide")

# --- 🎨 样式 ---
st.markdown("""
    <style>
    .stApp { background-color: #FFFFFF; color: #000000; }
    h3 { border-left: 5px solid #0056b3; padding-left: 10px; margin-top: 20px; }
    .stButton>button { background-color: #0056b3; color: white; border-radius: 4px; }
    div[data-testid="metric-container"] { background-color: #f8f9fa; border: 1px solid #e9ecef; border-radius: 8px; }
    </style>
    """, unsafe_allow_html=True)

# --- 🛠️ 辅助逻辑 (Keep Alive) ---
if 'keep_alive_started' not in st.session_state:
    def keep_alive():
        url = st.secrets.get("public_url")
        while True:
            try: time.sleep(300); requests.get(url, timeout=10) if url else None
            except: time.sleep(60)
    threading.Thread(target=keep_alive, daemon=True).start()
    st.session_state['keep_alive_started'] = True

# --- 🧮 通用计算函数 ---
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

def normalize_text(text):
    return ''.join(c for c in unicodedata.normalize('NFD', str(text)) if unicodedata.category(c) != 'Mn').lower()

# --- 📥 数据获取函数 ---
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

def fetch_recruitment_data(client, conf, months):
    try:
        sheet = safe_api_call(client.open_by_key, conf['id'])
        total_s, total_i, total_o = 0, 0, 0
        for m in months:
            try:
                ws = safe_api_call(sheet.worksheet, m)
                rows = safe_api_call(ws.get_all_values)
                target_key = conf.get('keyword', 'Name')
                for r in rows:
                    if not r: continue
                    if r[0].strip() == target_key:
                        total_s += len([v for v in r[1:] if v.strip()])
                    elif r[0].strip() in ["Stage", "Status", "状态", "阶段"]:
                        for v in r[1:]:
                            s = v.strip().lower()
                            if s:
                                if "offer" in s: total_o += 1
                                if "interview" in s or "面试" in s or "offer" in s: total_i += 1
            except: continue
        return total_s, total_i, total_o
    except: return 0, 0, 0

def fetch_sales_main(client):
    try:
        sheet = safe_api_call(client.open_by_key, SALES_SHEET_ID)
        ws = safe_api_call(sheet.worksheet, SALES_TAB_NAME)
        rows = safe_api_call(ws.get_all_values)
        if not rows: return pd.DataFrame()
        
        header = [x.lower() for x in rows[0]]
        c_idx = next(i for i, v in enumerate(header) if "consultant" in v)
        o_idx = next(i for i, v in enumerate(header) if "onboarding" in v)
        s_idx = next(i for i, v in enumerate(header) if "salary" in v)
        p_idx = next(i for i, v in enumerate(header) if "payment" in v and "onboard" not in v)
        
        data = []
        for r in rows[1:]:
            if len(r) <= max(c_idx, o_idx, s_idx): continue
            # 日期解析
            dt = None
            for fmt in ["%Y-%m-%d", "%d/%m/%Y"]:
                try: dt = datetime.strptime(r[o_idx].strip(), fmt); break
                except: pass
            if not dt: continue
            
            # 顾问匹配
            matched = "Unknown"
            for conf in TEAM_CONFIG:
                if normalize_text(conf['name']) in normalize_text(r[c_idx]): matched = conf['name']; break
            if matched == "Unknown": continue

            try: sal = float(r[s_idx].replace(',','').replace('$','').strip())
            except: sal = 0
            
            data.append({
                "Consultant": matched, "GP": sal * (1.5 if sal >= 20000 else 1.0),
                "Candidate Salary": sal, "Onboard Date": dt, 
                "Status": "Paid" if len(r[p_idx]) > 5 else "Pending",
                "Quarter": get_quarter_str(dt)
            })
        return pd.DataFrame(data)
    except: return pd.DataFrame()

# --- 📊 统一渲染组件 ---
def render_recruitment_table(df):
    if df.empty: st.info("No data found."); return
    df['Activity %'] = (df['Sent'] / CV_TARGET_QUARTERLY).fillna(0) * 100
    df['Int Rate'] = (df['Int'] / df['Sent']).fillna(0) * 100
    st.dataframe(
        df, use_container_width=True, hide_index=True,
        column_config={
            "Activity %": st.column_config.ProgressColumn(format="%.0f%%", min_value=0, max_value=100),
            "Int Rate": st.column_config.NumberColumn("Int/Sent", format="%.2f%%"),
            "Sent": st.column_config.NumberColumn(help="Target: 87")
        }
    )

def render_financial_table(sales_df, rec_df, team_data):
    rows = []
    for conf in team_data:
        c_name = conf['name']
        role = conf.get('role', 'Consultant')
        is_tl = (role == "Team Lead")
        base = conf['base_salary']
        
        target_gp = 0 if role == "Intern" else base * (4.5 if is_tl else 9.0)
        c_sales = sales_df[sales_df['Consultant'] == c_name] if not sales_df.empty else pd.DataFrame()
        booked = c_sales['GP'].sum()
        paid = c_sales[c_sales['Status'] == 'Paid']['GP'].sum()
        
        sent = rec_df[rec_df['Consultant'] == c_name]['Sent'].sum() if not rec_df.empty else 0
        met = (sent >= CV_TARGET_QUARTERLY) or (booked >= target_gp and target_gp > 0)
        
        comm = 0
        if met and role != "Intern":
            _, mult = calculate_commission_tier(paid, base, is_tl)
            for _, row in c_sales[c_sales['Status'] == 'Paid'].iterrows():
                comm += calculate_single_deal_commission(row['Candidate Salary'], mult)

        rows.append({
            "Consultant": c_name, "Role": role, "GP Target": target_gp, "Paid GP": paid,
            "Fin %": (booked / target_gp * 100) if target_gp > 0 else 0,
            "Status": "Met" if met else "In Progress", "Est. Commission": comm
        })
    
    st.dataframe(
        pd.DataFrame(rows).sort_values("Paid GP", ascending=False), use_container_width=True, hide_index=True,
        column_config={
            "GP Target": st.column_config.NumberColumn(format="$%d"),
            "Paid GP": st.column_config.NumberColumn(format="$%d"),
            "Fin %": st.column_config.ProgressColumn("Fin % (Booked)", format="%.0f%%", min_value=0, max_value=100),
            "Est. Commission": st.column_config.NumberColumn("Payable Comm.", format="$%d")
        }
    )

# --- 🚀 主页面 ---
def main():
    st.subheader(f"📊 Dashboard Period: {CURRENT_Q_STR}")
    client = connect_to_google()
    if not client: st.error("Please configure Google Secrets."); return

    if st.button("🔄 REFRESH ALL DATA", type="primary"):
        with st.spinner("Syncing with Google Sheets..."):
            # 获取角色并抓取数据
            team = []
            cur_stats, prev_stats = [], []
            for c in TEAM_CONFIG:
                role = fetch_personal_data_role = "Consultant"
                try:
                    sheet = client.open_by_key(c['id'])
                    role = sheet.worksheet('Credentials').acell('B1').value.strip()
                except: pass
                
                c_data = c.copy(); c_data['role'] = role; team.append(c_data)
                
                # 抓取当前季度数据
                s, i, o = fetch_recruitment_data(client, c, CURRENT_Q_MONTHS)
                cur_stats.append({"Consultant": c['name'], "Sent": s, "Int": i, "Off": o, "Role": role})
                
                # 抓取上个季度数据 (历史)
                ps, pi, po = fetch_recruitment_data(client, c, PREV_Q_MONTHS)
                prev_stats.append({"Consultant": c['name'], "Sent": ps, "Int": pi, "Off": po, "Role": role})

            st.session_state['data'] = {
                "team": team, "cur_rec": pd.DataFrame(cur_stats), "prev_rec": pd.DataFrame(prev_stats),
                "sales_all": fetch_sales_main(client), "upd": datetime.now().strftime("%H:%M")
            }
            st.rerun()

    if 'data' not in st.session_state: st.info("Click Refresh to load data."); st.stop()
    cache = st.session_state['data']

    # --- 第一部分: Recruitment ---
    st.markdown(f"### 🎯 Recruitment Stats ({CURRENT_Q_STR})")
    render_recruitment_table(cache['cur_rec'])
    
    with st.expander(f"📜 Historical Recruitment ({PREV_Q_STR} Identical Format)"):
        render_recruitment_table(cache['prev_rec'])

    st.divider()

    # --- 第二部分: Financial ---
    st.markdown(f"### 💰 Financial Performance ({CURRENT_Q_STR})")
    cur_sales = cache['sales_all'][cache['sales_all']['Quarter'] == CURRENT_Q_STR] if not cache['sales_all'].empty else pd.DataFrame()
    render_financial_table(cur_sales, cache['cur_rec'], cache['team'])
    
    with st.expander("📜 Historical Financial (Other Quarters Identical Format)"):
        if not cache['sales_all'].empty:
            hist_qs = sorted([q for q in cache['sales_all']['Quarter'].unique() if q != CURRENT_Q_STR], reverse=True)
            for q in hist_qs:
                st.write(f"**{q}**")
                h_sales = cache['sales_all'][cache['sales_all']['Quarter'] == q]
                h_rec = cache['prev_rec'] if q == PREV_Q_STR else pd.DataFrame()
                render_financial_table(h_sales, h_rec, cache['team'])

if __name__ == "__main__":
    main()
