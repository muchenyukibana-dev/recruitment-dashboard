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
# 🔧 1. 自动化配置区域
# ==========================================
now = datetime.now()
CURRENT_YEAR = now.year
CURRENT_QUARTER = (now.month - 1) // 3 + 1
CURRENT_Q_STR = f"{CURRENT_YEAR} Q{CURRENT_QUARTER}"

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

st.set_page_config(page_title="2026 Management Dashboard", page_icon="🎯", layout="wide")

# --- 🎨 样式 ---
st.markdown("""
    <style>
    .stApp { background-color: #FFFFFF; color: #000000; }
    h3 { color: #0056b3 !important; border-bottom: 2px solid #eee; padding-bottom: 10px; }
    .stButton>button { background-color: #0056b3; color: white; border-radius: 4px; font-weight: bold; }
    </style>
    """, unsafe_allow_html=True)

# --- 🧮 辅助函数 ---
def get_quarter_str(date_obj):
    if pd.isna(date_obj): return "Unknown"
    return f"{date_obj.year} Q{(date_obj.month - 1) // 3 + 1}"

def calculate_commission_tier(total_gp, base_salary, is_tl=False):
    """
    返回: (Level等级, Multiplier倍数)
    """
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

# --- 📥 数据抓取 ---
def connect_to_google():
    try:
        scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
        creds = ServiceAccountCredentials.from_json_keyfile_dict(dict(st.secrets["gcp_service_account"]), scope)
        return gspread.authorize(creds)
    except: return None

def fetch_all_sales_data(client):
    try:
        ws = client.open_by_key(SALES_SHEET_ID).worksheet(SALES_TAB_NAME)
        rows = ws.get_all_values()
        header = [x.lower().strip() for x in rows[0]]
        
        # 精确列定位
        col_cons = next(i for i, v in enumerate(header) if "linkeazi" in v and "consultant" in v)
        col_onboard = next(i for i, v in enumerate(header) if "onboarding" in v and "date" in v)
        col_sal = next(i for i, v in enumerate(header) if "candidate" in v and "salary" in v)
        # 排除包含 salary 的列来找人名
        col_cand = next(i for i, v in enumerate(header) if ("candidate" in v or "候选人" in v) and "salary" not in v)
        col_comp = next(i for i, v in enumerate(header) if "company" in v or "client" in v or "公司" in v or "客户" in v)
        col_pay = next(i for i, v in enumerate(header) if "payment" in v and "onboard" not in v)
        col_pct = next((i for i, v in enumerate(header) if "percentage" in v or v == "%"), -1)

        data = []
        for r in rows[1:]:
            if len(r) <= max(col_cons, col_onboard, col_sal): continue
            name = r[col_cons].strip()
            if not name: continue
            
            dt = None
            for fmt in ["%Y-%m-%d", "%d/%m/%Y", "%Y/%m/%d", "%m/%d/%Y"]:
                try: dt = datetime.strptime(r[col_onboard].strip(), fmt); break
                except: pass
            if not dt: continue
            
            matched = "Unknown"
            for conf in TEAM_CONFIG:
                if normalize_text(conf['name']) in normalize_text(name): matched = conf['name']; break
            if matched == "Unknown": continue

            try: sal = float(r[col_sal].replace(',','').replace('$','').strip())
            except: sal = 0
            
            pct = 1.0
            if col_pct != -1:
                try:
                    pv = float(r[col_pct].replace('%','').strip())
                    pct = pv/100 if pv > 1 else pv
                except: pass

            data.append({
                "Consultant": matched, "Company": r[col_comp], "Candidate Name": r[col_cand],
                "GP": sal * (1.5 if sal >= 20000 else 1.0) * pct, "Candidate Salary": sal, "Percentage": pct,
                "Onboard Date": dt, "Onboard Date Str": dt.strftime("%Y-%m-%d"),
                "Status": "Paid" if len(r[col_pay].strip()) > 5 else "Pending",
                "Payment Date Obj": dt if len(r[col_pay].strip()) > 5 else None,
                "Quarter": get_quarter_str(dt)
            })
        return pd.DataFrame(data)
    except Exception as e:
        st.error(f"Error fetching sales: {e}")
        return pd.DataFrame()

# --- 📊 核心计算逻辑 ---
def process_commission_retroactive(all_sales_df, team_data, rec_stats_df):
    """
    全量追溯提成逻辑：计算季度总GP，确定最高阶梯，回溯每一单
    """
    if all_sales_df.empty: return pd.DataFrame()
    
    processed_list = []
    # 按照 季度 + 顾问 分组
    for (q_label, c_name), group in all_sales_df.groupby(['Quarter', 'Consultant']):
        # 获取该顾问的底薪配置
        conf = next((item for item in team_data if item["name"] == c_name), None)
        if not conf: continue
        
        base = conf['base_salary']
        is_tl = (conf.get('role') == "Team Lead")
        
        # 1. 计算该季度已付款的总GP
        paid_deals = group[group['Status'] == 'Paid']
        total_q_paid_gp = paid_deals['GP'].sum()
        
        # 2. 确定该季度最终达到的最高阶梯 (Level & Multiplier)
        final_level, final_mult = calculate_commission_tier(total_q_paid_gp, base, is_tl)
        
        # 3. 检查招聘目标达标情况 (如果是当前季度)
        # 简化：如果是历史记录，默认视为达标以便显示潜在佣金
        is_met = True
        if q_label == CURRENT_Q_STR:
            sent = rec_stats_df[rec_stats_df['Consultant'] == c_name]['Sent'].sum() if not rec_stats_df.empty else 0
            is_met = (sent >= CV_TARGET_QUARTERLY) or (total_q_paid_gp >= (base * 9.0))

        # 4. 追溯应用倍数到每一单
        group['Applied Tier'] = final_level
        group['Final Comm'] = 0.0
        group['Commission Day'] = ""
        
        for idx in group.index:
            if group.loc[idx, 'Status'] == 'Paid':
                # 无论第一单还是最后一单，全部使用最终确定的 final_mult
                comm = calculate_single_deal_commission(group.loc[idx, 'Candidate Salary'], final_mult) * group.loc[idx, 'Percentage']
                group.at[idx, 'Final Comm'] = comm if is_met else 0
                
                # 预计发放日期 (简化为次月15号)
                group.at[idx, 'Commission Day'] = (group.loc[idx, 'Onboard Date'] + timedelta(days=45)).replace(day=15).strftime("%Y-%m-%d")

        processed_list.append(group)
        
    return pd.concat(processed_list) if processed_list else pd.DataFrame()

# --- 🚀 主页面 ---
def main():
    st.subheader(f"📊 Dashboard Period: {CURRENT_Q_STR}")
    client = connect_to_google()
    if not client: st.error("Please configure Google Secrets."); return

    if st.button("🔄 REFRESH ALL DATA", type="primary"):
        with st.spinner("Syncing..."):
            # 抓取角色
            updated_team = []
            for c in TEAM_CONFIG:
                try:
                    role = client.open_by_key(c['id']).worksheet('Credentials').acell('B1').value.strip()
                except: role = "Consultant"
                updated_team.append({**c, "role": role})
            
            # 抓取招聘数据
            stats_list = []
            for m in quarter_months_str:
                for c in updated_team:
                    try:
                        rows = client.open_by_key(c['id']).worksheet(m).get_all_values()
                        sent = sum(1 for r in rows if r[0] == c['keyword'] for v in r[1:] if v.strip())
                        stats_list.append({"Consultant": c['name'], "Sent": sent})
                    except: stats_list.append({"Consultant": c['name'], "Sent": 0})
            
            # 抓取销售明细并计算追溯佣金
            raw_sales = fetch_all_sales_data(client)
            processed_sales = process_commission_retroactive(raw_sales, updated_team, pd.DataFrame(stats_list))
            
            st.session_state['data'] = {
                "team": updated_team, "stats": pd.DataFrame(stats_list),
                "sales": processed_sales, "upd": datetime.now().strftime("%H:%M")
            }
            st.rerun()

    if 'data' not in st.session_state: st.stop()
    cache = st.session_state['data']

    tab_dash, tab_details = st.tabs(["📊 DASHBOARD", "📝 DETAILS"])

    with tab_dash:
        # 汇总表
        st.markdown(f"### 💰 Financial Performance ({CURRENT_Q_STR})")
        summary_rows = []
        for c in cache['team']:
            q_sales = cache['sales'][(cache['sales']['Consultant'] == c['name']) & (cache['sales']['Quarter'] == CURRENT_Q_STR)]
            paid_gp = q_sales[q_sales['Status'] == 'Paid']['GP'].sum()
            booked_gp = q_sales['GP'].sum()
            comm = q_sales['Final Comm'].sum()
            level = q_sales['Applied Tier'].max() if not q_sales.empty else 0
            
            target = c['base_salary'] * (4.5 if c['role'] == "Team Lead" else 9.0)
            summary_rows.append({
                "Consultant": c['name'], "Role": c['role'], "Paid GP": paid_gp,
                "Fin %": (booked_gp / target * 100) if target > 0 else 0,
                "Level": int(level), "Est. Commission": comm
            })
        
        st.dataframe(pd.DataFrame(summary_rows).sort_values("Paid GP", ascending=False), use_container_width=True, hide_index=True, column_config={
            "Paid GP": st.column_config.NumberColumn(format="$%d"),
            "Fin %": st.column_config.ProgressColumn(format="%.0f%%", min_value=0, max_value=100),
            "Est. Commission": st.column_config.NumberColumn(format="$%d")
        })

    with tab_details:
        st.markdown("### 🔍 Full History Details (Retroactive Applied)")
        for c in cache['team']:
            with st.expander(f"👤 {c['name']} ({c['role']})"):
                c_deals = cache['sales'][cache['sales']['Consultant'] == c['name']].copy()
                if not c_deals.empty:
                    # 格式化显示
                    display_cols = ['Onboard Date Str', 'Company', 'Candidate Name', 'Status', 'Candidate Salary', 'GP', 'Applied Tier', 'Commission Day', 'Final Comm']
                    st.dataframe(c_deals[display_cols].sort_values('Onboard Date Str', ascending=False), use_container_width=True, hide_index=True, column_config={
                        "Candidate Salary": st.column_config.NumberColumn(format="$%d"),
                        "GP": st.column_config.NumberColumn(format="$%d"),
                        "Final Comm": st.column_config.NumberColumn("Comm ($)", format="$%.2f"),
                        "Applied Tier": st.column_config.NumberColumn("Tier Level")
                    })
                else: st.info("No records.")

if __name__ == "__main__":
    main()
