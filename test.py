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
# 🔧 配置区域
# ==========================================
SALES_SHEET_ID = '1jniQ-GpeMINjQMebniJ_J1eLVLQIR1NGbSjTtOFP9Q8'
SALES_TAB_NAME = 'Positions'

now = datetime.now()
CURRENT_YEAR = now.year
CURRENT_QUARTER = (now.month - 1) // 3 + 1
CURRENT_Q_STR = f"{CURRENT_YEAR} Q{CURRENT_QUARTER}"

start_m = (CURRENT_QUARTER - 1) * 3 + 1
end_m = start_m + 2
quarter_months_str = [f"{CURRENT_YEAR}{m:02d}" for m in range(start_m, end_m + 1)]

CV_TARGET_QUARTERLY = 87

TEAM_CONFIG = [
    {"name": "Raul Solis", "id": "1vQuN-iNBRUug5J6gBMX-52jp6oogbA77SaeAf9j_zYs", "keyword": "Name",
     "base_salary": 11000},
    {"name": "Estela Peng", "id": "1sUkffAXzWnpzhhmklqBuwtoQylpR1U18zqBQ-lsp7Z4", "keyword": "姓名",
     "base_salary": 20800},
    {"name": "Ana Cruz", "id": "1VMVw5YCV12eI8I-VQSXEKg86J2IVZJEgjPJT7ggAFD0", "keyword": "Name", "base_salary": 13000},
    {"name": "Karina Albarran", "id": "1zc4ghvfjIxH0eJ2aXfopOWHqiyTDlD8yFNjBzpH07D8", "keyword": "Name",
     "base_salary": 15000},
]

st.set_page_config(page_title="Management Dashboard", page_icon="💼", layout="wide")

st.markdown("""
    <style>
    .stApp { background-color: #FFFFFF; color: #000000; }
    h1, h2, h3, h4 { color: #333333 !important; font-family: 'Arial', sans-serif; }
    .stButton>button { background-color: #0056b3; color: white; border: none; border-radius: 4px; padding: 10px 24px; font-weight: bold; }
    .stButton>button:hover { background-color: #004494; color: white; }
    .dataframe { font-size: 14px !important; border: 1px solid #ddd !important; }
    div[data-testid="metric-container"] { background-color: #f8f9fa; border: 1px solid #e9ecef; padding: 15px; border-radius: 8px; color: #333; box-shadow: 0 2px 4px rgba(0,0,0,0.05); }
    </style>
    """, unsafe_allow_html=True)

# --- 统一表格配置 ---
REC_COL_CONFIG = {
    "Quarter": st.column_config.TextColumn("Quarter", width=100),
    "Consultant": st.column_config.TextColumn("Consultant", width=150),
    "Role": st.column_config.TextColumn("Role", width=100),
    "CV Target": st.column_config.NumberColumn("Target (Q)", format="%d", width=100),
    "Sent": st.column_config.NumberColumn("Sent", format="%d", width=100),
    "Activity %": st.column_config.ProgressColumn("Activity %", format="%.0f%%", min_value=0, max_value=100, width=150),
    "Int": st.column_config.NumberColumn("Int", width=100),
    "Off": st.column_config.NumberColumn("Off", width=80),
    "Int Rate": st.column_config.NumberColumn("Int/Sent", format="%.2f%%", width=120),
}

FIN_COL_CONFIG = {
    "Quarter": st.column_config.TextColumn("Quarter", width=100),
    "Consultant": st.column_config.TextColumn("Consultant", width=150),
    "Role": st.column_config.TextColumn("Role", width=100),
    "GP Target": st.column_config.NumberColumn("GP Target", format="$%d", width=100),
    "Paid GP": st.column_config.NumberColumn("Paid GP", format="$%d", width=100),
    "Fin %": st.column_config.ProgressColumn("Financial % (Booked)", format="%.0f%%", min_value=0, max_value=100,
                                             width=150),
    "Status": st.column_config.TextColumn("Status", width=140),
    "Level": st.column_config.NumberColumn("Level", width=80),
    "Est. Commission": st.column_config.NumberColumn("Payable Comm.", format="$%d", width=130),
}

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

def get_payout_date_from_month_key(month_key):
    try:
        dt = datetime.strptime(str(month_key), "%Y-%m")
        year = dt.year + (dt.month // 12)
        month = (dt.month % 12) + 1
        return datetime(year, month, 15)
    except: return None

def normalize_text(text):
    return ''.join(c for c in unicodedata.normalize('NFD', str(text)) if unicodedata.category(c) != 'Mn').lower()

def safe_api_call(func, *args, **kwargs):
    for i in range(5):
        try: return func(*args, **kwargs)
        except Exception as e:
            if "429" in str(e): time.sleep(2 * (2 ** i)); continue
            raise e
    return None

def connect_to_google():
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    try:
        if "gcp_service_account" in st.secrets:
            creds = ServiceAccountCredentials.from_json_keyfile_dict(dict(st.secrets["gcp_service_account"]), scope)
            return gspread.authorize(creds)
        return None
    except: return None

def fetch_role_from_personal_sheet(client, sheet_id):
    try:
        sheet = safe_api_call(client.open_by_key, sheet_id)
        ws = safe_api_call(sheet.worksheet, 'Credentials')
        role = safe_api_call(ws.acell, 'B1').value
        return role.strip() if role else "Consultant"
    except: return "Consultant"

def internal_fetch_sheet_data(client, conf, tab):
    try:
        sheet = safe_api_call(client.open_by_key, conf['id'])
        ws = safe_api_call(sheet.worksheet, tab)
        rows = safe_api_call(ws.get_all_values)
        details, cs, ci, co = [], 0, 0, 0
        target_key = conf.get('keyword', 'Name')
        block = {"c": "Unk", "p": "Unk", "cands": {}}

        def flush(b):
            res = []
            nonlocal cs, ci, co
            for _, c_data in b['cands'].items():
                if not c_data.get('n'): continue
                stage = str(c_data.get('s', 'Sent')).lower()
                is_off = "offer" in stage
                is_int = ("interview" in stage) or ("面试" in stage) or is_off
                if is_off: co += 1
                if is_int: ci += 1
                cs += 1
                stat = "Offered" if is_off else ("Interviewed" if is_int else "Sent")
                res.append({"Consultant": conf['name'], "Month": tab, "Company": b['c'], "Position": b['p'], "Status": stat, "Count": 1})
            return res

        for r in rows:
            if not r: continue
            fc = r[0].strip()
            if fc in ["Company", "Client", "Cliente", "公司", "客户"]:
                details.extend(flush(block))
                block = {"c": r[1] if len(r) > 1 else "Unk", "p": "Unk", "cands": {}}
            elif fc in ["Position", "Role", "职位"]:
                block['p'] = r[1] if len(r) > 1 else "Unk"
            elif fc == target_key:
                for idx, v in enumerate(r[1:], 1):
                    if v.strip():
                        if idx not in block['cands']: block['cands'][idx] = {}
                        block['cands'][idx]['n'] = v.strip()
            elif fc in ["Stage", "Status", "Step", "阶段", "状态"]:
                for idx, v in enumerate(r[1:], 1):
                    if v.strip():
                        if idx not in block['cands']: block['cands'][idx] = {}
                        block['cands'][idx]['s'] = v.strip()
        details.extend(flush(block))
        return cs, ci, co, details
    except: return 0, 0, 0, []

def fetch_recruitment_stats(client, months):
    all_stats, all_details = [], []
    for month in months:
        for consultant in TEAM_CONFIG:
            s, i, o, d = internal_fetch_sheet_data(client, consultant, month)
            all_stats.append({"Consultant": consultant['name'], "Month": month, "Sent": s, "Int": i, "Off": o})
            if d: all_details.extend(d)
    return pd.DataFrame(all_stats), pd.DataFrame(all_details)

def fetch_historical_recruitment_stats(client, exclude_months):
    all_stats = []
    try:
        sheet = safe_api_call(client.open_by_key, TEAM_CONFIG[0]['id'])
        worksheets = safe_api_call(sheet.worksheets)
        hist_months = [ws.title.strip() for ws in worksheets if ws.title.strip().isdigit() and len(ws.title.strip()) == 6 and ws.title.strip() not in exclude_months]
        for month in hist_months:
            for consultant in TEAM_CONFIG:
                s, i, o, _ = internal_fetch_sheet_data(client, consultant, month)
                if s + i + o > 0: all_stats.append({"Consultant": consultant['name'], "Month": month, "Sent": s, "Int": i, "Off": o})
        return pd.DataFrame(all_stats)
    except: return pd.DataFrame()

def fetch_all_sales_data(client):
    try:
        sheet = safe_api_call(client.open_by_key, SALES_SHEET_ID)
        ws = safe_api_call(sheet.worksheet, SALES_TAB_NAME)
        rows = safe_api_call(ws.get_all_values)
        col_cons, col_onboard, col_pay, col_sal, col_pct, col_company, col_cand = -1, -1, -1, -1, -1, -1, -1
        sales_records, found_header = [], False
        date_formats = ["%Y-%m-%d", "%d/%m/%Y", "%Y/%m/%d", "%m/%d/%Y", "%d-%b-%y", "%Y.%m.%d"]
        for row in rows:
            if not any(cell.strip() for cell in row): continue
            row_lower = [str(x).strip().lower() for x in row]
            if not found_header:
                if any("linkeazi" in c and "consultant" in c for c in row_lower):
                    for idx, cell in enumerate(row_lower):
                        if "linkeazi" in cell and "consultant" in cell: col_cons = idx
                        if "onboarding" in cell and "date" in cell: col_onboard = idx
                        if "candidate" in cell and "salary" in cell: col_sal = idx
                        if "payment" in cell and "onboard" not in cell: col_pay = idx
                        if "percentage" in cell or cell == "%": col_pct = idx
                        if "company" in cell or "client" in cell or "客户" in cell or "公司" in cell: col_company = idx
                        if "candidate" in cell or "候选人" in cell or "上岗" in cell: col_cand = idx
                    found_header = True; continue
            if found_header:
                if len(row) <= max(col_cons, col_onboard, col_sal): continue
                c_name = row[col_cons].strip()
                if not c_name: continue
                onboard_date = None
                for fmt in date_formats:
                    try: onboard_date = datetime.strptime(row[col_onboard].strip(), fmt); break
                    except: pass
                if not onboard_date: continue
                matched = "Unknown"
                c_norm = normalize_text(c_name)
                for conf in TEAM_CONFIG:
                    conf_norm = normalize_text(conf['name'])
                    if conf_norm in c_norm or c_norm in conf_norm: matched = conf['name']; break
                if matched == "Unknown": continue
                try: salary = float(str(row[col_sal]).replace(',', '').replace('$', '').strip())
                except: salary = 0
                pct = 1.0
                if col_pct != -1 and len(row) > col_pct:
                    try:
                        pv = float(str(row[col_pct]).replace('%', '').strip())
                        pct = pv / 100 if pv > 1 else pv
                    except: pass
                calc_gp = salary * (1.0 if salary < 20000 else 1.5) * pct
                pay_date_obj, status = None, "Pending"
                if col_pay != -1 and len(row) > col_pay:
                    if len(row[col_pay].strip()) > 5:
                        status = "Paid"
                        for fmt in date_formats:
                            try: pay_date_obj = datetime.strptime(row[col_pay].strip(), fmt); break
                            except: pass
                sales_records.append({
                    "Consultant": matched, "Company": row[col_company] if col_company != -1 else "Unk",
                    "Cdd Placed": row[col_cand] if col_cand != -1 else "Unk",
                    "GP": calc_gp, "Candidate Salary": salary, "Percentage": pct,
                    "Onboard Date": onboard_date, "Onboard Date Str": onboard_date.strftime("%Y-%m-%d"),
                    "Payment Date": row[col_pay] if col_pay != -1 else "",
                    "Payment Date Obj": pay_date_obj, "Status": status, "Quarter": get_quarter_str(onboard_date)
                })
        return pd.DataFrame(sales_records)
    except: return pd.DataFrame()

def load_data_from_api(client, quarter_months_str):
    team_data = []
    for conf in TEAM_CONFIG:
        member = conf.copy()
        member['role'] = fetch_role_from_personal_sheet(client, conf['id'])
        team_data.append(member)
    rec_stats, rec_details = fetch_recruitment_stats(client, quarter_months_str)
    rec_hist = fetch_historical_recruitment_stats(client, exclude_months=quarter_months_str)
    all_sales = fetch_all_sales_data(client)
    return {
        "team_data": team_data, "rec_stats": rec_stats, "rec_details": rec_details,
        "rec_hist": rec_hist, "sales_all": all_sales, "last_updated": datetime.now().strftime("%H:%M:%S")
    }

# --- 🚀 主程序 ---
def main():
    st.title("💼 Management Dashboard")
    client = connect_to_google()
    if not client: st.error("❌ API Error"); return

    col1, _ = st.columns([1, 5])
    with col1:
        if st.button("🔄 REFRESH DATA", type="primary"):
            with st.spinner("⏳ Fetching live data..."):
                st.session_state['data_cache'] = load_data_from_api(client, quarter_months_str)
                st.rerun()

    if 'data_cache' not in st.session_state:
        st.info("👋 Welcome! Click 'REFRESH DATA' to load report."); st.stop()

    cache = st.session_state['data_cache']
    dynamic_team_config = cache['team_data']
    rec_stats_df, rec_details_df, rec_hist_df, all_sales_df = cache['rec_stats'], cache['rec_details'], cache['rec_hist'], cache['sales_all']

    if not all_sales_df.empty:
        curr_mask = (all_sales_df['Onboard Date'].dt.year == CURRENT_YEAR) & (all_sales_df['Onboard Date'].dt.month >= start_m) & (all_sales_df['Onboard Date'].dt.month <= end_m)
        sales_df_current = all_sales_df[curr_mask].copy()
        sales_df_hist = all_sales_df[~curr_mask].copy()
    else:
        sales_df_current = sales_df_hist = pd.DataFrame()

    # --- 核心逻辑处理：计算佣金与达标状态 ---
    financial_summary_list = []
    updated_sales_all_list = []
    
    # 获取当前季度的所有单子（用于后续 Lead Override 计算）
    q_sales_base = all_sales_df[all_sales_df['Quarter'] == CURRENT_Q_STR].copy() if not all_sales_df.empty else pd.DataFrame()

    for conf in dynamic_team_config:
        c_name, base, role = conf['name'], conf['base_salary'], conf.get('role', 'Consultant')
        is_intern, is_lead = (role == "Intern"), (role == "Team Lead")
        
        # 1. 基础数据
        sent_count = rec_stats_df[rec_stats_df['Consultant'] == c_name]['Sent'].sum() if not rec_stats_df.empty else 0
        gp_target = 0 if is_intern else base * (4.5 if is_lead else 9.0)
        c_q_sales = q_sales_base[q_sales_base['Consultant'] == c_name].copy() if not q_sales_base.empty else pd.DataFrame()
        booked_gp = c_q_sales['GP'].sum() if not c_q_sales.empty else 0
        
        # 2. 进度计算
        rec_pct = (sent_count / CV_TARGET_QUARTERLY * 100)
        fin_pct = (booked_gp / gp_target * 100) if gp_target > 0 else 0
        
        # 3. 达标判断 (Target Met) 核心逻辑
        achieved = []
        is_target_met = False
        if is_intern:
            if rec_pct >= 100: achieved.append("Activity"); is_target_met = True
        else:
            if fin_pct >= 100: achieved.append("Financial"); is_target_met = True
            if rec_pct >= 100: achieved.append("Activity"); is_target_met = True
        status_text = " & ".join(achieved) if achieved else "In Progress"

        # 4. 佣金计算逻辑
        total_comm = 0
        current_level = 0
        paid_gp = 0

        if not is_intern and not c_q_sales.empty:
            c_q_sales['Final Comm'] = 0.0
            c_q_sales['Commission Day'] = ""
            paid_sales = c_q_sales[c_q_sales['Status'] == 'Paid'].copy()
            
            if not paid_sales.empty:
                paid_sales['Payment Date Obj'] = pd.to_datetime(paid_sales['Payment Date Obj'])
                paid_sales = paid_sales.sort_values('Payment Date Obj')
                paid_sales['Pay_Month_Key'] = paid_sales['Payment Date Obj'].dt.to_period('M')
                running_gp = 0
                
                for month_key in sorted(paid_sales['Pay_Month_Key'].unique()):
                    m_deals = paid_sales[paid_sales['Pay_Month_Key'] == month_key]
                    running_gp += m_deals['GP'].sum()
                    level, mult = calculate_commission_tier(running_gp, base, is_lead)
                    p_date = get_payout_date_from_month_key(str(month_key))
                    
                    for idx in m_deals.index:
                        # 只有达标 (Target Met) 才计算佣金，否则为0
                        comm = calculate_single_deal_commission(m_deals.loc[idx, 'Candidate Salary'], mult) * m_deals.loc[idx, 'Percentage'] if is_target_met else 0
                        paid_sales.at[idx, 'Final Comm'] = comm
                        paid_sales.at[idx, 'Commission Day'] = p_date.strftime("%Y-%m-%d") if p_date else ""
                
                total_comm = paid_sales['Final Comm'].sum()
                paid_gp = running_gp
                current_level, _ = calculate_commission_tier(paid_gp, base, is_lead)
                c_q_sales.update(paid_sales)

            # 5. Team Lead Override 逻辑
            if is_lead and is_target_met:
                # 规则：已付款单子，排除自己，排除 Estela Peng，每笔奖 1000
                override_mask = (q_sales_base['Status'] == 'Paid') & (q_sales_base['Consultant'] != c_name) & (q_sales_base['Consultant'] != "Estela Peng")
                team_deals_count = q_sales_base[override_mask].shape[0]
                total_comm += (team_deals_count * 1000)

            updated_sales_all_list.append(c_q_sales)

        financial_summary_list.append({
            "Quarter": CURRENT_Q_STR, "Consultant": c_name, "Role": role, "GP Target": gp_target,
            "Paid GP": paid_gp, "Fin %": fin_pct, "Status": status_text,
            "Level": current_level, "Est. Commission": total_comm
        })

    final_sales_df = pd.concat(updated_sales_all_list) if updated_sales_all_list else pd.DataFrame()
    df_fin = pd.DataFrame(financial_summary_list)

    # --- UI Tabs 渲染 ---
    tab_dash, tab_details, tab_historylogs = st.tabs(["📊 DASHBOARD", "📝 DETAILS", "🕕 HISTORY LOGS"])

    with tab_dash:
        st.markdown(f"### 🎯 Recruitment Stats ({CURRENT_Q_STR})")
        curr_rec = []
        for conf in dynamic_team_config:
            name = conf['name']
            row = rec_stats_df[rec_stats_df['Consultant'] == name] if not rec_stats_df.empty else pd.DataFrame()
            s, i, o = row['Sent'].sum(), row['Int'].sum(), row['Off'].sum()
            curr_rec.append({
                "Quarter": CURRENT_Q_STR, "Consultant": name, "Role": conf['role'],
                "CV Target": CV_TARGET_QUARTERLY, "Sent": s, "Int": i, "Off": o,
                "Activity %": (s / CV_TARGET_QUARTERLY * 100),
                "Int Rate": (i / s * 100) if s > 0 else 0
            })
        st.dataframe(pd.DataFrame(curr_rec), use_container_width=True, hide_index=True, column_config=REC_COL_CONFIG)

        with st.expander("📜 Historical Recruitment Data"):
            if not rec_hist_df.empty:
                rec_hist_df['Quarter'] = rec_hist_df['Month'].apply(lambda x: f"{x[:4]} Q{(int(x[4:]) - 1) // 3 + 1}")
                u_q = sorted(rec_hist_df['Quarter'].unique(), reverse=True)
                hist_rec_full = []
                for q in u_q:
                    for conf in dynamic_team_config:
                        name = conf['name']
                        q_data = rec_hist_df[(rec_hist_df['Quarter'] == q) & (rec_hist_df['Consultant'] == name)]
                        s, i, o = q_data['Sent'].sum(), q_data['Int'].sum(), q_data['Off'].sum()
                        hist_rec_full.append({"Quarter": q, "Consultant": name, "Role": conf['role'], "CV Target": CV_TARGET_QUARTERLY, "Sent": s, "Int": i, "Off": o, "Activity %": (s / CV_TARGET_QUARTERLY * 100), "Int Rate": (i / s * 100) if s > 0 else 0})
                st.dataframe(pd.DataFrame(hist_rec_full), use_container_width=True, hide_index=True, column_config=REC_COL_CONFIG)

        st.divider()
        st.markdown(f"### 💰 Financial Performance ({CURRENT_Q_STR})")
        st.dataframe(df_fin.sort_values('Paid GP', ascending=False), use_container_width=True, hide_index=True, column_config=FIN_COL_CONFIG)

        with st.expander("📜 Historical GP Summary"):
            if not sales_df_hist.empty:
                u_q_hist = sorted(sales_df_hist['Quarter'].unique(), reverse=True)
                hist_fin_full = []
                for q in u_q_hist:
                    for conf in dynamic_team_config:
                        name, base, role = conf['name'], conf['base_salary'], conf.get('role', 'Consultant')
                        gp_target = base * (4.5 if role == "Team Lead" else 9.0)
                        q_sales = sales_df_hist[(sales_df_hist['Quarter'] == q) & (sales_df_hist['Consultant'] == name)]
                        paid_gp = q_sales['GP'].sum() if not q_sales.empty else 0
                        hist_fin_full.append({"Quarter": q, "Consultant": name, "Role": role, "GP Target": gp_target, "Paid GP": paid_gp, "Fin %": (paid_gp / gp_target * 100) if gp_target > 0 else 0, "Status": "Past Record", "Level": 0, "Est. Commission": 0})
                st.dataframe(pd.DataFrame(hist_fin_full), use_container_width=True, hide_index=True, column_config=FIN_COL_CONFIG)

    with tab_details:
        st.markdown("### 🔍 Drill Down Details (Current Quarter)")
        for conf in dynamic_team_config:
            c_name = conf['name']
            member_fin_rows = df_fin[df_fin['Consultant'] == c_name]
            if member_fin_rows.empty: continue
            member_fin = member_fin_rows.iloc[0]
            with st.expander(f"👤 {c_name} ({member_fin['Role']})"):
                if member_fin['Role'] != "Intern":
                    st.markdown("#### 💸 Deal & Commission Breakdown")
                    if not final_sales_df.empty:
                        c_view = final_sales_df[final_sales_df['Consultant'] == c_name].copy()
                        if not c_view.empty:
                            cols_to_show = ['Onboard Date Str', 'Company', 'Cdd Placed', 'Status', 'Candidate Salary', 'GP', 'Commission Day', 'Final Comm']
                            for col in cols_to_show:
                                if col not in c_view.columns: c_view[col] = ""
                            st.dataframe(c_view[cols_to_show].sort_values('Onboard Date Str', ascending=False), use_container_width=True, hide_index=True,
                                         column_config={"Onboard Date Str": st.column_config.TextColumn("Date"), "Candidate Salary": st.column_config.NumberColumn("Salary", format="$%d"), "Final Comm": st.column_config.NumberColumn("Comm ($)", format="$%.2f")})
                        else: st.info("No deals recorded this quarter.")

    with tab_historylogs:
        st.markdown("🕕 RECRUITMENT ACTIVITY LOGS")
        for conf in dynamic_team_config:
            c_name = conf['name']
            if not rec_details_df.empty:
                c_logs = rec_details_df[rec_details_df['Consultant'] == c_name]
                if not c_logs.empty:
                    with st.expander(f"Log: {c_name}"):
                        st.dataframe(c_logs.groupby(['Month', 'Company', 'Position', 'Status'])['Count'].sum().reset_index().sort_values('Month', ascending=False), use_container_width=True, hide_index=True)

if __name__ == "__main__":
    main()
