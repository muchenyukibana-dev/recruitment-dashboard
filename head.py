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
# 🔧 1. 实时时间与配置
# ==========================================
now = datetime.now()
CURRENT_YEAR = now.year
CURRENT_QUARTER = (now.month - 1) // 3 + 1
CURRENT_Q_STR = f"{CURRENT_YEAR} Q{CURRENT_QUARTER}"

# 自动计算当前季度的月份列表 (例如 202601, 202602, 202603)
start_month_val = (CURRENT_QUARTER - 1) * 3 + 1
CURRENT_QUARTER_MONTHS = [f"{CURRENT_YEAR}{m:02d}" for m in range(start_month_val, start_month_val + 3)]

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
    h1, h2, h3 { color: #0056b3 !important; font-family: 'Arial', sans-serif; }
    .dataframe { font-size: 13px !important; }
    div[data-testid="metric-container"] { background-color: #f8f9fa; border: 1px solid #e9ecef; border-radius: 8px; }
    </style>
    """, unsafe_allow_html=True)

# ==========================================
# 🧮 2. 核心辅助函数 (保持原逻辑)
# ==========================================
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
        creds = ServiceAccountCredentials.from_json_keyfile_dict(dict(st.secrets["gcp_service_account"]), scope)
        return gspread.authorize(creds)
    return None

# ==========================================
# 📥 3. 数据抓取逻辑 (针对顾问个人表和主表)
# ==========================================
def internal_fetch_sheet_data(client, conf, tab):
    try:
        sheet = safe_api_call(client.open_by_key, conf['id'])
        ws = safe_api_call(sheet.worksheet, tab)
        rows = safe_api_call(ws.get_all_values)
        cs, ci, co = 0, 0, 0
        target_key = conf.get('keyword', 'Name')
        for r in rows:
            if not r: continue
            row_str = " ".join(r).lower()
            if target_key.lower() in row_str: # 寻找发人名字行
                for v in r[1:]:
                    if v.strip(): cs += 1
            if any(k in row_str for k in ["stage", "status", "状态", "阶段"]): # 寻找状态行
                for v in r[1:]:
                    val = v.lower()
                    if "interview" in val or "面试" in val: ci += 1
                    if "offer" in val: ci += 1; co += 1
        return cs, ci, co
    except: return 0, 0, 0

def fetch_all_recruitment_data(client):
    """同时抓取当前和历史所有招聘数据"""
    current_stats = []
    historical_stats = []
    
    for conf in TEAM_CONFIG:
        # 获取该顾问表中所有的月份页签
        try:
            sheet = safe_api_call(client.open_by_key, conf['id'])
            all_ws = [ws.title for ws in sheet.worksheets() if ws.title.isdigit() and len(ws.title) == 6]
            for tab in all_ws:
                s, i, o = internal_fetch_sheet_data(client, conf, tab)
                q_label = f"{tab[:4]} Q{(int(tab[4:])-1)//3+1}"
                record = {"Consultant": conf['name'], "Quarter": q_label, "Sent": s, "Int": i, "Off": o}
                if tab in CURRENT_QUARTER_MONTHS:
                    current_stats.append(record)
                else:
                    historical_stats.append(record)
        except: continue
        
    return pd.DataFrame(current_stats), pd.DataFrame(historical_stats)

def fetch_sales_from_master(client):
    """从主表 1jniQ... 抓取财务数据"""
    try:
        sheet = safe_api_call(client.open_by_key, SALES_SHEET_ID)
        ws = safe_api_call(sheet.worksheet, SALES_TAB_NAME)
        rows = safe_api_call(ws.get_all_values)
        # 这里复用你原有的 fetch_all_sales_data 逻辑进行解析 (简化版)
        data = []
        # 寻找表头
        header = [x.lower() for x in rows[0]]
        # ... (此处省略复杂的列索引匹配逻辑，假设已获取) ...
        # 为了演示，直接返回已包含 Quarter 字段的 DataFrame (即你原有的逻辑输出)
        from supervisor import fetch_all_sales_data # 引用你原文件里的成熟逻辑
        return fetch_all_sales_data(client)
    except: return pd.DataFrame()

# ==========================================
# 📊 4. UI 渲染辅助
# ==========================================
def render_stats_table(df, title):
    st.subheader(title)
    if df.empty:
        st.info("No data available.")
        return
    
    # 汇总计算
    summary = df.groupby(['Quarter', 'Consultant'])[['Sent', 'Int', 'Off']].sum().reset_index()
    summary['Target'] = CV_TARGET_QUARTERLY
    summary['Activity %'] = (summary['Sent'] / summary['Target']).fillna(0) * 100
    summary['Int Rate'] = (summary['Int'] / summary['Sent']).fillna(0) * 100
    
    st.dataframe(
        summary.sort_values(['Quarter', 'Sent'], ascending=[False, False]),
        use_container_width=True, hide_index=True,
        column_config={
            "Activity %": st.column_config.ProgressColumn(format="%.0f%%", min_value=0, max_value=100),
            "Int Rate": st.column_config.NumberColumn("Int/Sent", format="%.1f%%")
        }
    )

# ==========================================
# 🚀 5. 主程序
# ==========================================
def main():
    st.title("💼 LinkEazi Management Dashboard")
    st.caption(f"📅 系统当前识别：{CURRENT_Q_STR} | 自动抓取月份：{', '.join(CURRENT_QUARTER_MONTHS)}")

    client = connect_to_google()
    if not client: st.error("❌ Google API Connection Error"); return

    if st.button("🔄 刷新全量数据 (REFRESH ALL DATA)", type="primary"):
        with st.spinner("正在从 5 张 Google Sheets 抓取数据..."):
            # 获取 Role
            roles = {}
            for conf in TEAM_CONFIG:
                roles[conf['name']] = fetch_role_from_personal_sheet(client, conf['id'])
            
            curr_rec, hist_rec = fetch_all_recruitment_data(client)
            sales_all = fetch_sales_from_master(client)
            
            st.session_state['data'] = {
                "roles": roles, "curr_rec": curr_rec, "hist_rec": hist_rec, 
                "sales_all": sales_all, "updated": datetime.now().strftime("%H:%M:%S")
            }
            st.rerun()

    if 'data' not in st.session_state:
        st.info("👋 欢迎！点击上方按钮开始加载数据。")
        return

    db = st.session_state['data']
    tab_rec, tab_fin = st.tabs(["📊 RECRUITMENT STATS", "💰 FINANCIAL STATS"])

    # ------------------------------------------
    # Tab 1: Recruitment (招聘数据)
    # ------------------------------------------
    with tab_rec:
        # 上部分：当前季度
        render_stats_table(db['curr_rec'], f"🎯 当前季度招聘表现 ({CURRENT_Q_STR})")
        
        st.divider()
        
        # 下部分：历史季度汇总
        render_stats_table(db['hist_rec'], "📜 历史季度招聘表现汇总")

    # ------------------------------------------
    # Tab 2: Financial (财务数据)
    # ------------------------------------------
    with tab_fin:
        # 1. 当前季度财务表现
        st.subheader(f"💰 当前季度财务表现 ({CURRENT_Q_STR})")
        sales_curr = db['sales_all'][db['sales_all']['Quarter'] == CURRENT_Q_STR] if not db['sales_all'].empty else pd.DataFrame()
        
        fin_summary = []
        for conf in TEAM_CONFIG:
            c_name = conf['name']
            role = db['roles'].get(c_name, "Consultant")
            base = conf['base_salary']
            is_tl = (role == "Team Lead")
            
            target_gp = 0 if role == "Intern" else base * (4.5 if is_tl else 9.0)
            
            # 过滤个人销售
            c_sales = sales_curr[sales_curr['Consultant'] == c_name]
            booked_gp = c_sales['GP'].sum()
            paid_gp = c_sales[c_sales['Status'] == 'Paid']['GP'].sum()
            
            # 简化版佣金计算展示
            level, mult = calculate_commission_tier(paid_gp, base, is_tl)
            
            fin_summary.append({
                "Consultant": c_name, "Role": role, "GP Target": target_gp,
                "Booked GP": booked_gp, "Paid GP": paid_gp, 
                "Achieve %": (booked_gp/target_gp*100) if target_gp > 0 else 0,
                "Level": level
            })
            
        st.dataframe(pd.DataFrame(fin_summary), use_container_width=True, hide_index=True,
                     column_config={
                         "Achieve %": st.column_config.ProgressColumn(format="%.0f%%", min_value=0, max_value=100),
                         "GP Target": st.column_config.NumberColumn(format="$%d"),
                         "Booked GP": st.column_config.NumberColumn(format="$%d"),
                         "Paid GP": st.column_config.NumberColumn(format="$%d")
                     })

        st.divider()

        # 2. 历史财务汇总 (按季度展示)
        st.subheader("📜 历史季度财务指标汇总")
        if not db['sales_all'].empty:
            hist_sales = db['sales_all'][db['sales_all']['Quarter'] != CURRENT_Q_STR]
            if not hist_sales.empty:
                # 按季度+顾问分组汇总
                q_fin = hist_sales.groupby(['Quarter', 'Consultant'])['GP'].sum().reset_index()
                # 同时也增加一个季度总计行
                q_total = hist_sales.groupby('Quarter')['GP'].sum().reset_index()
                q_total['Consultant'] = "✨ QUARTER TOTAL"
                
                combined_fin = pd.concat([q_total, q_fin]).sort_values(['Quarter', 'Consultant'], ascending=[False, True])
                
                st.dataframe(combined_fin, use_container_width=True, hide_index=True,
                             column_config={"GP": st.column_config.NumberColumn("Total GP", format="$%d")})
        else:
            st.info("No historical financial data found.")

# 为了保持代码运行，这里需要包含你原有的 fetch_role 函数
def fetch_role_from_personal_sheet(client, sheet_id):
    try:
        sheet = safe_api_call(client.open_by_key, sheet_id)
        ws = safe_api_call(sheet.worksheet, 'Credentials')
        return safe_api_call(ws.acell, 'B1').value.strip()
    except: return "Consultant"

if __name__ == "__main__":
    main()
