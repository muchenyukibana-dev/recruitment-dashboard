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

# 自动计算当前季度的三个月份字符串 (如 ['202601', '202602', '202603'])
start_month = (CURRENT_QUARTER - 1) * 3 + 1
CURRENT_QUARTER_MONTHS = [f"{CURRENT_YEAR}{m:02d}" for m in range(start_month, start_month + 3)]

# ==========================================
# ⚙️ 其他配置
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
    .dataframe { font-size: 13px !important; }
    div[data-testid="metric-container"] { background-color: #f8f9fa; border: 1px solid #e9ecef; padding: 15px; border-radius: 8px; }
    h2 { color: #0056b3 !important; border-bottom: 2px solid #0056b3; padding-bottom: 10px; margin-top: 30px;}
    </style>
    """, unsafe_allow_html=True)

# --- 🧮 核心辅助函数 (同原逻辑) ---
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

def calculate_single_deal_commission(salary, mult):
    if mult == 0: return 0
    if salary < 20000: base = 1000
    elif salary < 30000: base = salary * 0.05
    elif salary < 50000: base = salary * 1.5 * 0.05
    else: base = salary * 2.0 * 0.05
    return base * mult

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

# --- 📊 渲染函数 (用于保持格式一致) ---
def render_recruitment_table(df, title, target_val=CV_TARGET_QUARTERLY):
    st.subheader(title)
    if df.empty:
        st.info("No recruitment data available for this period.")
        return

    # 汇总计算
    summary = df.groupby('Consultant')[['Sent', 'Int', 'Off']].sum().reset_index()
    
    # 匹配 Role
    role_map = {m['name']: st.session_state['role_cache'].get(m['name'], 'Consultant') for m in TEAM_CONFIG}
    summary['Role'] = summary['Consultant'].map(role_map)
    summary['Target'] = target_val
    summary['Activity %'] = (summary['Sent'] / summary['Target']).fillna(0) * 100
    summary['Int Rate'] = (summary['Int'] / summary['Sent']).fillna(0) * 100

    # 合计行
    total_row = pd.DataFrame([{
        'Consultant': 'TOTAL', 'Role': '-', 'Target': summary['Target'].sum(),
        'Sent': summary['Sent'].sum(), 'Activity %': (summary['Sent'].sum() / summary['Target'].sum() * 100),
        'Int': summary['Int'].sum(), 'Off': summary['Off'].sum(), 
        'Int Rate': (summary['Int'].sum() / summary['Sent'].sum() * 100 if summary['Sent'].sum() > 0 else 0)
    }])
    summary = pd.concat([summary, total_row], ignore_index=True)

    st.dataframe(
        summary, use_container_width=True, hide_index=True,
        column_config={
            "Activity %": st.column_config.ProgressColumn("Activity %", format="%.0f%%", min_value=0, max_value=100),
            "Int Rate": st.column_config.NumberColumn("Int/Sent", format="%.1f%%"),
            "Target": st.column_config.NumberColumn("Target (Q)")
        }
    )

# --- 🚀 数据加载 (与原逻辑一致，但针对当前季度优化) ---
def load_all_data(client):
    # 1. 角色缓存
    role_cache = {}
    for conf in TEAM_CONFIG:
        try:
            sheet = safe_api_call(client.open_by_key, conf['id'])
            ws = safe_api_call(sheet.worksheet, 'Credentials')
            role_cache[conf['name']] = safe_api_call(ws.acell, 'B1').value.strip()
        except: role_cache[conf['name']] = "Consultant"
    st.session_state['role_cache'] = role_cache

    # 2. 当前季度招聘数据
    from supervisor import internal_fetch_sheet_data # 假设原有函数逻辑已封装
    rec_stats_curr = []
    for month in CURRENT_QUARTER_MONTHS:
        for conf in TEAM_CONFIG:
            s, i, o, _ = internal_fetch_sheet_data(client, conf, month)
            rec_stats_curr.append({"Consultant": conf['name'], "Month": month, "Sent": s, "Int": i, "Off": o})
    
    # 3. 历史招聘数据 (排除当前季度的月份)
    rec_stats_hist = []
    try:
        sheet = client.open_by_key(TEAM_CONFIG[0]['id'])
        all_tabs = [ws.title for ws in sheet.worksheets() if ws.title.isdigit() and ws.title not in CURRENT_QUARTER_MONTHS]
        for month in all_tabs:
            for conf in TEAM_CONFIG:
                s, i, o, _ = internal_fetch_sheet_data(client, conf, month)
                if s+i+o > 0: rec_stats_hist.append({"Consultant": conf['name'], "Quarter": f"{month[:4]} Q{(int(month[4:])-1)//3+1}", "Sent": s, "Int": i, "Off": o})
    except: pass

    # 4. 销售数据
    from supervisor import fetch_all_sales_data # 假设原有逻辑
    all_sales = fetch_all_sales_data(client)

    return {
        "rec_curr": pd.DataFrame(rec_stats_curr),
        "rec_hist": pd.DataFrame(rec_stats_hist),
        "sales": all_sales,
        "updated": datetime.now().strftime("%H:%M:%S")
    }

# --- 🎬 主页面 ---
def main():
    st.title("💼 Management Dashboard")
    st.caption(f"📅 Current System Time: {datetime.now().strftime('%Y-%m-%d %H:%M')} | Active Quarter: **{CURRENT_Q_STR}**")

    client = connect_to_google()
    if not client: st.error("Google API Connection Failed"); return

    if st.button("🔄 REFRESH ALL DATA", type="primary"):
        with st.spinner("Synchronizing with Google Sheets..."):
            st.session_state['data'] = load_all_data(client)
            st.rerun()

    if 'data' not in st.session_state:
        st.info("Click the button above to load data.")
        return

    data = st.session_state['data']
    tab_rec, tab_fin = st.tabs(["📊 RECRUITMENT STATS", "💰 FINANCIAL STATS"])

    # ==========================================
    # TAB 1: RECRUITMENT
    # ==========================================
    with tab_rec:
        # 上部分：当前季度
        render_recruitment_table(data['rec_curr'], f"Current Quarter Activity ({CURRENT_Q_STR})")
        
        st.write("") # 间距
        
        # 下部分：历史记录 (按季度汇总)
        st.subheader("Historical Recruitment Activity")
        if not data['rec_hist'].empty:
            # 获取历史季度列表
            hist_quarters = sorted(data['rec_hist']['Quarter'].unique(), reverse=True)
            for q in hist_quarters:
                with st.expander(f"📜 View Details: {q}"):
                    q_data = data['rec_hist'][data['rec_hist']['Quarter'] == q]
                    render_recruitment_table(q_data, f"Performance - {q}")
        else:
            st.info("No historical recruitment records found.")

    # ==========================================
    # TAB 2: FINANCIAL
    # ==========================================
    with tab_fin:
        # 预处理销售数据
        sales_df = data['sales']
        if sales_df.empty:
            st.warning("No sales data found.")
        else:
            # 区分当前和历史
            curr_mask = (sales_df['Quarter'] == CURRENT_Q_STR)
            sales_curr = sales_df[curr_mask]
            sales_hist = sales_df[~curr_mask]

            # 1. 当前季度财务表现
            st.subheader(f"Current Financial Performance ({CURRENT_Q_STR})")
            fin_summary = []
            for conf in TEAM_CONFIG:
                c_name = conf['name']
                role = st.session_state['role_cache'].get(c_name, "Consultant")
                is_tl = (role == "Team Lead")
                target_gp = 0 if role == "Intern" else conf['base_salary'] * (4.5 if is_tl else 9.0)
                
                c_sales = sales_curr[sales_curr['Consultant'] == c_name]
                booked_gp = c_sales['GP'].sum()
                paid_gp = c_sales[c_sales['Status'] == 'Paid']['GP'].sum()
                
                fin_summary.append({
                    "Consultant": c_name, "Role": role, "GP Target": target_gp, 
                    "Booked GP": booked_gp, "Paid GP": paid_gp,
                    "Progress": (booked_gp/target_gp*100) if target_gp > 0 else 0
                })
            
            df_fin_curr = pd.DataFrame(fin_summary)
            st.dataframe(
                df_fin_curr, use_container_width=True, hide_index=True,
                column_config={
                    "Progress": st.column_config.ProgressColumn("Target Progress", format="%.0f%%", min_value=0, max_value=100),
                    "GP Target": st.column_config.NumberColumn(format="$%d"),
                    "Booked GP": st.column_config.NumberColumn(format="$%d"),
                    "Paid GP": st.column_config.NumberColumn(format="$%d"),
                }
            )

            st.write("")

            # 2. 历史财务汇总
            st.subheader("Historical Financial Summary (Quarterly)")
            if not sales_hist.empty:
                # 按季度和顾问汇总
                hist_grouped = sales_hist.groupby(['Quarter', 'Consultant'])['GP'].sum().reset_index()
                # 计算季度总计
                q_total = sales_hist.groupby('Quarter')['GP'].sum().reset_index()
                q_total['Consultant'] = "✨ QUARTER TOTAL"
                
                combined_hist = pd.concat([q_total, hist_grouped]).sort_values(['Quarter', 'Consultant'], ascending=[False, True])
                
                st.dataframe(
                    combined_hist, use_container_width=True, hide_index=True,
                    column_config={
                        "GP": st.column_config.NumberColumn("Total GP Generated", format="$%d")
                    }
                )
            else:
                st.info("No historical financial data.")

if __name__ == "__main__":
    main()
