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
# 🔧 1. 配置与实时环境
# ==========================================
now = datetime.now()
CURRENT_YEAR = now.year
CURRENT_QUARTER = (now.month - 1) // 3 + 1
CURRENT_Q_STR = f"{CURRENT_YEAR} Q{CURRENT_QUARTER}"

SALES_SHEET_ID = '1jniQ-GpeMINjQMebniJ_J1eLVLQIR1NGbSjTtOFP9Q8'
SALES_TAB_NAME = 'Positions'
CV_TARGET_QUARTERLY = 87

TEAM_CONFIG = [
    {"name": "Raul Solis", "id": "1vQuN-iNBRUug5J6gBMX-52jp6oogbA77SaeAf9j_zYs", "keyword": "Name", "base_salary": 11000},
    {"name": "Estela Peng", "id": "1sUkffAXzWnpzhhmklqBuwtoQylpR1U18zqBQ-lsp7Z4", "keyword": "姓名", "base_salary": 20800},
    {"name": "Ana Cruz", "id": "1VMVw5YCV12eI8I-VQSXEKg86J2IVZJEgjPJT7ggAFD0", "keyword": "Name", "base_salary": 13000},
    {"name": "Karina Albarran", "id": "1zc4ghvfjIxH0eJ2aXfopOWHqiyTDlD8yFNjBzpH07D8", "keyword": "Name", "base_salary": 15000},
]

st.set_page_config(page_title="Executive Management Dashboard", page_icon="💼", layout="wide")

# --- 🎨 样式 ---
st.markdown("""
    <style>
    .stApp { background-color: #FFFFFF; color: #000000; }
    h1, h2, h3, h4 { color: #333333 !important; font-family: 'Arial', sans-serif; }
    .stButton>button { background-color: #0056b3; color: white; border-radius: 4px; font-weight: bold; }
    .dataframe { font-size: 13px !important; }
    div[data-testid="metric-container"] { background-color: #f8f9fa; border: 1px solid #e9ecef; border-radius: 8px; padding: 10px; }
    </style>
    """, unsafe_allow_html=True)

# ==========================================
# 🧮 2. 核心逻辑辅助函数
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
            if "429" in str(e): time.sleep(2 * (2 ** i)); continue
            raise e
    return None

def connect_to_google():
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    if "gcp_service_account" in st.secrets:
        creds = ServiceAccountCredentials.from_json_keyfile_dict(dict(st.secrets["gcp_service_account"]), scope)
        return gspread.authorize(creds)
    return None

# ==========================================
# 📥 3. 数据抓取
# ==========================================
def fetch_role(client, sheet_id):
    try:
        sheet = safe_api_call(client.open_by_key, sheet_id)
        ws = safe_api_call(sheet.worksheet, 'Credentials')
        return safe_api_call(ws.acell, 'B1').value.strip() or "Consultant"
    except: return "Consultant"

def internal_fetch_sheet_data(client, conf, tab):
    try:
        sheet = safe_api_call(client.open_by_key, conf['id'])
        ws = safe_api_call(sheet.worksheet, tab)
        rows = safe_api_call(ws.get_all_values)
        details, cs, ci, co = [], 0, 0, 0
        target_key = conf.get('keyword', 'Name')
        COMPANY_KEYS = ["Company", "Client", "Cliente", "公司", "客户", "公司名称", "客户名称"]
        POSITION_KEYS = ["Position", "Role", "Posición", "职位", "岗位"]
        STAGE_KEYS = ["Stage", "Status", "Step", "阶段", "状态"]
        block = {"c": "Unk", "p": "Unk", "cands": {}}

        def flush(b):
            res = []
            nonlocal cs, ci, co
            for _, c_data in b['cands'].items():
                name = c_data.get('n')
                if not name: continue
                stage = str(c_data.get('s', 'Sent')).lower()
                is_off = "offer" in stage
                is_int = ("interview" in stage) or ("面试" in stage) or is_off
                if is_off: co += 1
                if is_int: ci += 1
                cs += 1
                res.append({
                    "Consultant": conf['name'], "Month": tab, "Year": tab[:4], "Company": b['c'], 
                    "Position": b['p'], "Status": "Offered" if is_off else ("Interviewed" if is_int else "Sent"), "Count": 1
                })
            return res

        for r in rows:
            if not r: continue
            fc = r[0].strip()
            if fc in COMPANY_KEYS:
                details.extend(flush(block))
                block = {"c": r[1] if len(r) > 1 else "Unk", "p": "Unk", "cands": {}}
            elif fc in POSITION_KEYS: block['p'] = r[1] if len(r) > 1 else "Unk"
            elif fc == target_key:
                for idx, v in enumerate(r[1:], 1):
                    if v.strip():
                        if idx not in block['cands']: block['cands'][idx] = {}
                        block['cands'][idx]['n'] = v.strip()
            elif fc in STAGE_KEYS:
                for idx, v in enumerate(r[1:], 1):
                    if v.strip():
                        if idx not in block['cands']: block['cands'][idx] = {}
                        block['cands'][idx]['s'] = v.strip()
        details.extend(flush(block))
        return cs, ci, co, details
    except: return 0, 0, 0, []

def fetch_all_sales_data(client):
    try:
        sheet = safe_api_call(client.open_by_key, SALES_SHEET_ID)
        ws = safe_api_call(sheet.worksheet, SALES_TAB_NAME)
        rows = safe_api_call(ws.get_all_values)
        col_cons, col_onboard, col_pay, col_sal, col_pct = -1, -1, -1, -1, -1
        sales_records = []
        found_header = False
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
                        if "percentage" in cell or cell == "%" or "pct" in cell: col_pct = idx
                    found_header = True; continue
            if found_header:
                if "POSITION" in " ".join(row_lower).upper() and "PLACED" not in " ".join(row_lower).upper(): break
                if len(row) <= max(col_cons, col_onboard, col_sal): continue
                onboard_date = None
                for fmt in date_formats:
                    try: onboard_date = datetime.strptime(row[col_onboard].strip(), fmt); break
                    except: pass
                if not onboard_date: continue
                matched = "Unknown"
                c_norm = normalize_text(row[col_cons].strip())
                for conf in TEAM_CONFIG:
                    conf_norm = normalize_text(conf['name'])
                    if conf_norm in c_norm or c_norm in conf_norm or conf_norm.split()[0] in c_norm: matched = conf['name']; break
                if matched == "Unknown": continue
                try: salary = float(str(row[col_sal]).replace(',', '').replace('$', '').strip())
                except: salary = 0
                pct = 1.0
                if col_pct != -1 and len(row) > col_pct:
                    try:
                        p_float = float(str(row[col_pct]).replace('%', '').strip())
                        pct = p_float / 100.0 if p_float > 1.0 else p_float
                    except: pct = 1.0
                calc_gp = salary * (1.0 if salary < 20000 else 1.5) * pct
                pay_date_obj, status = None, "Pending"
                if col_pay != -1 and len(row) > col_pay:
                    pay_str = row[col_pay].strip()
                    if len(pay_str) > 5:
                        status = "Paid"
                        for fmt in date_formats:
                            try: pay_date_obj = datetime.strptime(pay_str, fmt); break
                            except: pass
                sales_records.append({
                    "Consultant": matched, "GP": calc_gp, "Candidate Salary": salary, "Percentage": pct,
                    "Onboard Date": onboard_date, "Onboard Date Str": onboard_date.strftime("%Y-%m-%d"),
                    "Payment Date": row[col_pay].strip() if col_pay != -1 and len(row) > col_pay else "",
                    "Payment Date Obj": pay_date_obj, "Status": status, "Quarter": get_quarter_str(onboard_date)
                })
        return pd.DataFrame(sales_records)
    except: return pd.DataFrame()

# ==========================================
# 📊 4. 计算引擎
# ==========================================
def calculate_financial_summary(sales_df, rec_df, q_str, team_data):
    summary, details_map, overrides_map = [], {}, {}
    q_sales = sales_df[sales_df['Quarter'] == q_str].copy() if not sales_df.empty else pd.DataFrame()
    q_rec = rec_df[rec_df['Quarter'] == q_str] if not rec_df.empty else pd.DataFrame()

    for conf in team_data:
        c_name, base, role = conf['name'], conf['base_salary'], conf.get('role', 'Consultant')
        is_tl, is_int = (role == "Team Lead"), (role == "Intern")
        target_gp = 0 if is_int else base * (4.5 if is_tl else 9.0)

        c_sales = q_sales[q_sales['Consultant'] == c_name].copy() if not q_sales.empty else pd.DataFrame()
        for col in ['Comm ($)', 'Applied Level', 'Comm. Date']: 
            if col not in c_sales.columns: c_sales[col] = 0.0 if "Comm" in col else 0

        sent_count = q_rec[q_rec['Consultant'] == c_name]['Sent'].sum() if not q_rec.empty else 0
        booked_gp = c_sales['GP'].sum() if not c_sales.empty else 0
        fin_pct = (booked_gp / target_gp * 100) if target_gp > 0 else 0
        rec_pct = (sent_count / CV_TARGET_QUARTERLY * 100)
        is_target_met = (fin_pct >= 100 or rec_pct >= 100)

        paid_gp, total_comm, level = 0, 0, 0
        if not is_int and not c_sales.empty:
            paid_sales = c_sales[c_sales['Status'] == 'Paid'].copy()
            if not paid_sales.empty:
                paid_sales['Payment Date Obj'] = pd.to_datetime(paid_sales['Payment Date Obj'])
                paid_sales = paid_sales.sort_values('Payment Date Obj')
                paid_sales['MonthKey'] = paid_sales['Payment Date Obj'].dt.to_period('M')
                running_gp = 0
                for m_key in sorted(paid_sales['MonthKey'].unique()):
                    m_deals = paid_sales[paid_sales['MonthKey'] == m_key]
                    running_gp += m_deals['GP'].sum()
                    lvl, mult = calculate_commission_tier(running_gp, base, is_tl)
                    level = lvl
                    for idx, row in m_deals.iterrows():
                        comm_val = calculate_single_deal_commission(row['Candidate Salary'], mult) * row['Percentage']
                        if is_target_met:
                            total_comm += comm_val
                            paid_sales.at[idx, 'Comm ($)'] = comm_val
                        paid_sales.at[idx, 'Applied Level'] = lvl
                        pmt_date = row['Payment Date Obj']
                        paid_sales.at[idx, 'Comm. Date'] = (datetime(pmt_date.year + (pmt_date.month // 12), (pmt_date.month % 12) + 1, 15)).strftime("%Y-%m-%d")
                paid_gp = running_gp
                c_sales.update(paid_sales)

        tl_overrides = []
        if is_tl and is_target_met and not q_sales.empty:
            others_paid = q_sales[(q_sales['Status'] == 'Paid') & (q_sales['Consultant'] != c_name) & (q_sales['Consultant'] != "Estela Peng")]
            for _, row in others_paid.iterrows():
                total_comm += 1000
                pmt_date = pd.to_datetime(row['Payment Date Obj'])
                comm_date_str = (datetime(pmt_date.year + (pmt_date.month // 12), (pmt_date.month % 12) + 1, 15)).strftime("%Y-%m-%d")
                tl_overrides.append({"Leader": c_name, "Source": row['Consultant'], "Salary": row['Candidate Salary'], "Date": comm_date_str, "Bonus": 1000})

        summary.append({
            "Consultant": c_name, "Role": role, "GP Target": target_gp, "Paid GP": paid_gp,
            "Fin % (Booked)": fin_pct, "Status": "Met" if is_target_met else "In Progress", "Level": level, "Payable Comm.": total_comm
        })
        details_map[c_name] = c_sales
        overrides_map[c_name] = pd.DataFrame(tl_overrides)

    return pd.DataFrame(summary), details_map, overrides_map

# ==========================================
# 🚀 5. 主程序渲染
# ==========================================
def main():
    st.title("💼 Management Dashboard")
    client = connect_to_google()
    if not client: st.error("❌ Auth Failed"); return

    if st.button("🔄 REFRESH ALL DATA", type="primary"):
        with st.spinner("⏳ Fetching live data..."):
            team_data = [{**c, "role": fetch_role(client, c['id'])} for c in TEAM_CONFIG]
            rec_all, rec_logs = [], []
            ref_sheet = client.open_by_key(TEAM_CONFIG[0]['id'])
            all_m = [ws.title for ws in ref_sheet.worksheets() if ws.title.isdigit() and len(ws.title) == 6]
            for m in all_m:
                for c in TEAM_CONFIG:
                    s, i, o, d_logs = internal_fetch_sheet_data(client, c, m)
                    rec_all.append({"Consultant": c['name'], "Sent": s, "Int": i, "Off": o, "Quarter": f"{m[:4]} Q{(int(m[4:]) - 1) // 3 + 1}", "Year": m[:4]})
                    rec_logs.extend(d_logs)
            
            sales_df = fetch_all_sales_data(client)
            hist_comm_list = []
            if not sales_df.empty:
                for q in sorted(sales_df['Quarter'].unique()):
                    _, details_q, _ = calculate_financial_summary(sales_df, pd.DataFrame(rec_all), q, team_data)
                    for c_name, c_df in details_q.items():
                        if 'Comm ($)' in c_df.columns:
                            p_comm = c_df[(c_df['Status'] == 'Paid') & (c_df['Comm ($)'] > 0)].copy()
                            if not p_comm.empty: hist_comm_list.append(p_comm)

            st.session_state['data'] = {"team": team_data, "rec": pd.DataFrame(rec_all), "logs": pd.DataFrame(rec_logs), "sales": sales_df, "hist_comm": pd.concat(hist_comm_list) if hist_comm_list else pd.DataFrame(), "ts": datetime.now().strftime("%H:%M:%S")}
            st.rerun()

    if 'data' not in st.session_state: st.info("Click REFRESH to start."); st.stop()
    d = st.session_state['data']
    df_fin_curr, details_curr, overrides_curr = calculate_financial_summary(d['sales'], d['rec'], CURRENT_Q_STR, d['team'])

    t_dash, t_det, t_logs = st.tabs(["📊 DASHBOARD", "📝 FINANCIAL DETAILS", "📜 RECRUITMENT LOGS"])

    # --- 第一页: Dashboard (来自 head running.py) ---
    with t_dash:
        st.markdown(f"### 🎯 Recruitment Stats ({CURRENT_Q_STR})")
        curr_rec = d['rec'][d['rec']['Quarter'] == CURRENT_Q_STR]
        if not curr_rec.empty:
            summary = curr_rec.groupby('Consultant')[['Sent', 'Int', 'Off']].sum().reset_index()
            summary['Activity %'] = (summary['Sent'] / CV_TARGET_QUARTERLY * 100).clip(0, 100)
            st.dataframe(summary, use_container_width=True, hide_index=True, column_config={"Activity %": st.column_config.ProgressColumn(format="%.0f%%")})
        
        st.divider()
        st.markdown(f"### 💰 Financial Performance ({CURRENT_Q_STR})")
        st.dataframe(df_fin_curr, use_container_width=True, hide_index=True, column_config={"Fin % (Booked)": st.column_config.ProgressColumn(format="%.0f%%", min_value=0, max_value=100)})

    # --- 第二页: Financial Details (来自 supervisor20251231.py) ---
    with t_det:
        st.markdown("### 🔍 Drill Down Details")
        for conf in d['team']:
            c_name = conf['name']
            fin_row = df_fin_curr[df_fin_curr['Consultant'] == c_name].iloc[0]
            with st.expander(f"👤 {c_name} | Role: {fin_row['Role']} | Status: {fin_row['Status']}"):
                st.markdown("#### 💸 Current Quarter Commission")
                c_curr = details_curr.get(c_name, pd.DataFrame())
                if not c_curr.empty:
                    st.dataframe(c_curr[['Onboard Date Str', 'Comm. Date', 'Candidate Salary', 'GP', 'Status', 'Comm ($)']], use_container_width=True, hide_index=True)
                
                st.divider()
                st.markdown("#### 📜 Historical Commission History")
                if not d['hist_comm'].empty:
                    h_view = d['hist_comm'][(d['hist_comm']['Consultant'] == c_name) & (d['hist_comm']['Quarter'] != CURRENT_Q_STR)]
                    if not h_view.empty: st.dataframe(h_view[['Quarter', 'Comm. Date', 'Candidate Salary', 'GP', 'Comm ($)']].sort_values('Comm. Date', ascending=False), use_container_width=True, hide_index=True)
                
                if fin_row['Role'] == 'Team Lead':
                    st.markdown("#### 👥 Team Overrides")
                    ov = overrides_curr.get(c_name, pd.DataFrame())
                    if not ov.empty: st.dataframe(ov, use_container_width=True, hide_index=True)

    # --- 第三页: Recruitment Logs (独立页面) ---
    with t_logs:
        st.markdown("### 📜 Detailed Recruitment Logs")
        years = sorted(d['logs']['Year'].unique(), reverse=True)
        for yr in years:
            with st.expander(f"📅 Year {yr}"):
                yr_logs = d['logs'][d['logs']['Year'] == yr]
                st.dataframe(yr_logs.groupby(['Month', 'Company', 'Position', 'Status'])['Count'].sum().reset_index().sort_values('Month', ascending=False), use_container_width=True, hide_index=True)

if __name__ == "__main__":
    main()
