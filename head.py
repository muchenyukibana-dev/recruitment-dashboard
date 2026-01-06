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
# 🔧 1. REAL-TIME DATE CONFIGURATION
# ==========================================
now = datetime.now()
CURRENT_YEAR = now.year
CURRENT_QUARTER = (now.month - 1) // 3 + 1
CURRENT_Q_STR = f"{CURRENT_YEAR} Q{CURRENT_QUARTER}"

# Automatically calculate months for the current quarter
# Q1: 1-3, Q2: 4-6, Q3: 7-9, Q4: 10-12
q_start_month = (CURRENT_QUARTER - 1) * 3 + 1
CURRENT_QUARTER_MONTHS = [f"{CURRENT_YEAR}{m:02d}" for m in range(q_start_month, q_start_month + 3)]

# ==========================================
# ⚙️ 2. DASHBOARD SETTINGS
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

# --- 🎨 Styles ---
st.markdown("""
    <style>
    .stApp { background-color: #FFFFFF; color: #000000; }
    h1, h2, h3, h4 { color: #333333 !important; font-family: 'Arial', sans-serif; }
    .stButton>button { background-color: #0056b3; color: white; border: none; border-radius: 4px; padding: 10px 24px; font-weight: bold; }
    .dataframe { font-size: 13px !important; }
    div[data-testid="metric-container"] { background-color: #f8f9fa; border: 1px solid #e9ecef; padding: 15px; border-radius: 8px; }
    </style>
    """, unsafe_allow_html=True)

# --- 🛡️ Keep Alive Logic ---
def keep_alive_worker():
    while True:
        try:
            time.sleep(600)
            print(f"💓 System Heartbeat: {datetime.now()}")
        except Exception: pass

if 'keep_alive_started' not in st.session_state:
    t = threading.Thread(target=keep_alive_worker, daemon=True)
    t.start()
    st.session_state['keep_alive_started'] = True

# ==========================================
# 🧮 3. HELPER FUNCTIONS
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

def get_commission_pay_date(payment_date):
    if pd.isna(payment_date) or not payment_date: return None
    try:
        year = payment_date.year + (payment_date.month // 12)
        month = (payment_date.month % 12) + 1
        return datetime(year, month, 15)
    except: return None

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
            if "429" in str(e): time.sleep(2 * (2 ** i) + random.uniform(0, 1))
            else: raise e
    return None

def connect_to_google():
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    if "gcp_service_account" in st.secrets:
        creds = ServiceAccountCredentials.from_json_keyfile_dict(dict(st.secrets["gcp_service_account"]), scope)
        return gspread.authorize(creds)
    return None

# ==========================================
# 📥 4. DATA FETCHING (RESTORED ORIGINAL LOGIC)
# ==========================================
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
                res.append({"Consultant": conf['name'], "Month": tab, "Status": "Offered" if is_off else ("Interviewed" if is_int else "Sent"), "Count": 1})
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
                if any("linkeazi" in c and "consultant" in c for c in row_lower) and any("onboarding" in c for c in row_lower):
                    for idx, cell in enumerate(row_lower):
                        if "linkeazi" in cell and "consultant" in cell: col_cons = idx
                        if "onboarding" in cell and "date" in cell: col_onboard = idx
                        if "candidate" in cell and "salary" in cell: col_sal = idx
                        if "payment" in cell and "onboard" not in cell: col_pay = idx
                        if "percentage" in cell or cell == "%" or "pct" in cell: col_pct = idx
                    found_header = True
                    continue
            if found_header:
                if "POSITION" in " ".join(row_lower).upper() and "PLACED" not in " ".join(row_lower).upper(): break
                if len(row) <= max(col_cons, col_onboard, col_sal): continue
                consultant_name = row[col_cons].strip()
                if not consultant_name: continue
                onboard_date = None
                for fmt in date_formats:
                    try: onboard_date = datetime.strptime(row[col_onboard].strip(), fmt); break
                    except: pass
                if not onboard_date: continue
                matched = "Unknown"
                c_norm = normalize_text(consultant_name)
                for conf in TEAM_CONFIG:
                    conf_norm = normalize_text(conf['name'])
                    if conf_norm in c_norm or c_norm in conf_norm or conf_norm.split()[0] in c_norm: matched = conf['name']; break
                if matched == "Unknown": continue
                try: salary = float(str(row[col_sal]).replace(',', '').replace('$', '').strip())
                except: salary = 0
                pct_val = 1.0
                if col_pct != -1 and len(row) > col_pct:
                    try: 
                        p_float = float(str(row[col_pct]).replace('%', '').strip())
                        pct_val = p_float / 100.0 if p_float > 1.0 else p_float
                    except: pct_val = 1.0
                calc_gp = salary * (1.0 if salary < 20000 else 1.5) * pct_val
                pay_date_obj, status = None, "Pending"
                if col_pay != -1 and len(row) > col_pay:
                    pay_str = row[col_pay].strip()
                    if len(pay_str) > 5:
                        status = "Paid"
                        for fmt in date_formats:
                            try: pay_date_obj = datetime.strptime(pay_str, fmt); break
                            except: pass
                sales_records.append({
                    "Consultant": matched, "GP": calc_gp, "Candidate Salary": salary, "Percentage": pct_val,
                    "Onboard Date": onboard_date, "Onboard Date Str": onboard_date.strftime("%Y-%m-%d"),
                    "Payment Date Obj": pay_date_obj, "Status": status, "Quarter": get_quarter_str(onboard_date)
                })
        return pd.DataFrame(sales_records)
    except: return pd.DataFrame()

# ==========================================
# 📊 5. MAIN LOGIC & UI RENDER
# ==========================================
def main():
    st.title("💼 Management Dashboard")
    st.caption(f"📅 System Time: {now.strftime('%Y-%m-%d')} | Active: **{CURRENT_Q_STR}**")

    client = connect_to_google()
    if not client: st.error("❌ Google Sheets API Connection Failed."); return

    if st.button("🔄 REFRESH ALL DATA", type="primary"):
        with st.spinner("⏳ Fetching live data from all sources..."):
            team_data = []
            for conf in TEAM_CONFIG:
                member = conf.copy()
                member['role'] = fetch_role_from_personal_sheet(client, conf['id'])
                team_data.append(member)
                time.sleep(0.3)

            # Fetch Recruitment
            rec_stats_df, rec_details_df = [], []
            for month in CURRENT_QUARTER_MONTHS:
                for consultant in TEAM_CONFIG:
                    s, i, o, d = internal_fetch_sheet_data(client, consultant, month)
                    rec_stats_df.append({"Consultant": consultant['name'], "Month": month, "Sent": s, "Int": i, "Off": o, "Quarter": CURRENT_Q_STR})
                    rec_details_df.extend(d)
            
            # Fetch History
            rec_hist_df = []
            try:
                sheet = client.open_by_key(TEAM_CONFIG[0]['id'])
                hist_months = [ws.title.strip() for ws in sheet.worksheets() if ws.title.strip().isdigit() and ws.title.strip() not in CURRENT_QUARTER_MONTHS]
                for m in hist_months:
                    for conf in TEAM_CONFIG:
                        s, i, o, _ = internal_fetch_sheet_data(client, conf, m)
                        if s+i+o > 0: rec_hist_df.append({"Consultant": conf['name'], "Month": m, "Sent": s, "Int": i, "Off": o, "Quarter": f"{m[:4]} Q{(int(m[4:])-1)//3+1}"})
            except: pass

            sales_all = fetch_all_sales_data(client)
            
            st.session_state['data'] = {
                "team": team_data, "rec_curr": pd.DataFrame(rec_stats_df), "rec_hist": pd.DataFrame(rec_hist_df),
                "rec_details": pd.DataFrame(rec_details_df), "sales_all": sales_all, "ts": datetime.now().strftime("%H:%M:%S")
            }
            st.rerun()

    if 'data' not in st.session_state:
        st.info("👋 Click Refresh to load the dashboard."); st.stop()

    data = st.session_state['data']
    tab_rec, tab_fin = st.tabs(["📊 RECRUITMENT STATS", "💰 FINANCIAL PERFORMANCE"])

    # ---------------------------------------------------------
    # TAB 1: RECRUITMENT (TOP: CURRENT, BOTTOM: HISTORY)
    # ---------------------------------------------------------
    with tab_rec:
        def render_rec_block(df, title):
            st.markdown(f"### {title}")
            if df.empty: st.info("No data available."); return
            summary = df.groupby(['Quarter', 'Consultant'])[['Sent', 'Int', 'Off']].sum().reset_index()
            summary['Target'] = CV_TARGET_QUARTERLY
            summary['Activity %'] = (summary['Sent'] / summary['Target'] * 100).clip(0, 100)
            summary['Int Rate'] = (summary['Int'] / summary['Sent'] * 100).fillna(0)
            st.dataframe(summary, use_container_width=True, hide_index=True, column_config={
                "Activity %": st.column_config.ProgressColumn(format="%.0f%%", min_value=0, max_value=100),
                "Int Rate": st.column_config.NumberColumn(format="%.1f%%")
            })

        render_rec_block(data['rec_curr'], f"Current Quarter Stats ({CURRENT_Q_STR})")
        st.divider()
        render_rec_block(data['rec_hist'], "Historical Recruitment Stats")

    # ---------------------------------------------------------
    # TAB 2: FINANCIAL (TOP: CURRENT, BOTTOM: HISTORY)
    # ---------------------------------------------------------
    with tab_fin:
        st.markdown(f"### Current Financial Performance ({CURRENT_Q_STR})")
        sales_df = data['sales_all']
        sales_curr = sales_df[sales_df['Quarter'] == CURRENT_Q_STR] if not sales_df.empty else pd.DataFrame()
        
        fin_summary = []
        for conf in data['team']:
            c_name, base, role = conf['name'], conf['base_salary'], conf['role']
            is_tl = (role == "Team Lead")
            is_int = (role == "Intern")
            target_gp = 0 if is_int else base * (4.5 if is_tl else 9.0)
            
            c_sales = sales_curr[sales_curr['Consultant'] == c_name].copy() if not sales_curr.empty else pd.DataFrame()
            sent_count = data['rec_curr'][data['rec_curr']['Consultant'] == c_name]['Sent'].sum() if not data['rec_curr'].empty else 0
            
            booked_gp = c_sales['GP'].sum()
            fin_pct = (booked_gp / target_gp * 100) if target_gp > 0 else 0
            rec_pct = (sent_count / CV_TARGET_QUARTERLY * 100)
            
            # Commission Logic
            is_target_met = (fin_pct >= 100 or rec_pct >= 100)
            paid_gp, total_comm = 0, 0
            
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
                        _, mult = calculate_commission_tier(running_gp, base, is_tl)
                        if is_target_met:
                            for _, row in m_deals.iterrows():
                                total_comm += calculate_single_deal_commission(row['Candidate Salary'], mult) * row['Percentage']
                    paid_gp = running_gp

            fin_summary.append({
                "Consultant": c_name, "Role": role, "GP Target": target_gp, "Paid GP": paid_gp, 
                "Fin % (Booked)": fin_pct, "Payable Comm.": total_comm, "Status": "Target Met" if is_target_met else "In Progress"
            })

        st.dataframe(pd.DataFrame(fin_summary), use_container_width=True, hide_index=True, column_config={
            "Fin % (Booked)": st.column_config.ProgressColumn(format="%.0f%%", min_value=0, max_value=100),
            "GP Target": st.column_config.NumberColumn(format="$%d"),
            "Paid GP": st.column_config.NumberColumn(format="$%d"),
            "Payable Comm.": st.column_config.NumberColumn(format="$%d")
        })
        
        st.divider()
        st.markdown("### Historical Financial Summary (Total GP)")
        if not sales_df.empty:
            sales_hist = sales_df[sales_df['Quarter'] != CURRENT_Q_STR]
            if not sales_hist.empty:
                hist_fin = sales_hist.groupby(['Quarter', 'Consultant'])['GP'].sum().reset_index()
                st.dataframe(hist_fin.sort_values(['Quarter', 'Consultant'], ascending=[False, True]), use_container_width=True, hide_index=True, column_config={
                    "GP": st.column_config.NumberColumn("Total GP", format="$%d")
                })

if __name__ == "__main__":
    main()
