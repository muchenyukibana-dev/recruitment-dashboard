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
# 🔧 1. REAL-TIME CONFIGURATION
# ==========================================
# Automatically detect current time
now = datetime.now()
CURRENT_YEAR = now.year
CURRENT_QUARTER = (now.month - 1) // 3 + 1
CURRENT_Q_STR = f"{CURRENT_YEAR} Q{CURRENT_QUARTER}"

# Calculate months for the current quarter
q_start_month = (CURRENT_QUARTER - 1) * 3 + 1
CURRENT_QUARTER_MONTHS = [f"{CURRENT_YEAR}{m:02d}" for m in range(q_start_month, q_start_month + 3)]

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
    .dataframe { font-size: 13px !important; border: 1px solid #ddd !important; }
    div[data-testid="metric-container"] { background-color: #f8f9fa; border: 1px solid #e9ecef; padding: 15px; border-radius: 8px; color: #333; box-shadow: 0 2px 4px rgba(0,0,0,0.05); }
    </style>
    """, unsafe_allow_html=True)

# --- 🛡️ Keep Alive ---
def keep_alive_worker():
    while True:
        try:
            time.sleep(300)
            print(f"💓 Heartbeat: {datetime.now()}")
        except Exception: pass

if 'keep_alive_started' not in st.session_state:
    t = threading.Thread(target=keep_alive_worker, daemon=True)
    t.start()
    st.session_state['keep_alive_started'] = True

# --- 🧮 Helpers ---
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

def calculate_single_deal_commission(sal, mult):
    if mult == 0: return 0
    if sal < 20000: base = 1000
    elif sal < 30000: base = sal * 0.05
    elif sal < 50000: base = sal * 1.5 * 0.05
    else: base = sal * 2.0 * 0.05
    return base * mult

def get_commission_pay_date(pmt_date):
    if pd.isna(pmt_date) or not pmt_date: return None
    try:
        y, m = pmt_date.year + (pmt_date.month // 12), (pmt_date.month % 12) + 1
        return datetime(y, m, 15)
    except: return None

def normalize_text(text):
    return ''.join(c for c in unicodedata.normalize('NFD', str(text)) if unicodedata.category(c) != 'Mn').lower()

def safe_api_call(func, *args, **kwargs):
    for i in range(5):
        try: return func(*args, **kwargs)
        except APIError as e:
            if "429" in str(e): time.sleep(2 * (2 ** i)); continue
            raise e
        except Exception as e: raise e
    return None

def connect_to_google():
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    if "gcp_service_account" in st.secrets:
        creds = ServiceAccountCredentials.from_json_keyfile_dict(dict(st.secrets["gcp_service_account"]), scope)
        return gspread.authorize(creds)
    return None

# --- 🛠️ Data Fetching ---
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
                stg = str(c_data.get('s', 'Sent')).lower()
                is_off = "offer" in stg
                is_int = ("interview" in stg) or ("面试" in stg) or is_off
                if is_off: co += 1
                if is_int: ci += 1
                cs += 1
                stat = "Offered" if is_off else ("Interviewed" if is_int else "Sent")
                res.append({"Consultant": conf['name'], "Month": tab, "Year": tab[:4], "Company": b['c'], "Position": b['p'], "Status": stat, "Count": 1})
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

def fetch_all_sales(client):
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
                    found_header = True; continue
            if found_header:
                if "POSITION" in " ".join(row_lower).upper() and "PLACED" not in " ".join(row_lower).upper(): break
                if len(row) <= max(col_cons, col_onboard, col_sal): continue
                c_name_raw = row[col_cons].strip()
                if not c_name_raw: continue
                on_date = None
                for fmt in date_formats:
                    try: on_date = datetime.strptime(row[col_onboard].strip(), fmt); break
                    except: pass
                if not on_date: continue
                matched = "Unknown"
                c_norm = normalize_text(c_name_raw)
                for conf in TEAM_CONFIG:
                    conf_norm = normalize_text(conf['name'])
                    if conf_norm in c_norm or c_norm in conf_norm or conf_norm.split()[0] in c_norm:
                        matched = conf['name']; break
                if matched == "Unknown": continue
                try: sal = float(str(row[col_sal]).replace(',','').replace('$','').strip())
                except: sal = 0
                pct = 1.0
                if col_pct != -1 and len(row) > col_pct:
                    try: 
                        p_float = float(str(row[col_pct]).replace('%', '').strip())
                        pct = p_float / 100.0 if p_float > 1.0 else p_float
                    except: pct = 1.0
                gp = sal * (1.0 if sal < 20000 else 1.5) * pct
                pay_obj, status = None, "Pending"
                if col_pay != -1 and len(row) > col_pay:
                    pay_str = row[col_pay].strip()
                    if len(pay_str) > 5:
                        status = "Paid"
                        for fmt in date_formats:
                            try: pay_obj = datetime.strptime(pay_str, fmt); break
                            except: pass
                sales_records.append({
                    "Consultant": matched, "GP": gp, "Candidate Salary": sal, "Percentage": pct,
                    "Onboard Date": on_date, "Year": str(on_date.year), "Status": status, "Payment Date Obj": pay_obj,
                    "Quarter": get_quarter_str(on_date)
                })
        return pd.DataFrame(sales_records)
    except: return pd.DataFrame()

# --- 🎯 Summary Calculation Engine ---
def get_financial_summary(sales_df, rec_stats_df, quarter_str, team_data):
    summary = []
    updated_deals = []
    
    q_sales = sales_df[sales_df['Quarter'] == quarter_str].copy() if not sales_df.empty else pd.DataFrame()
    q_rec = rec_stats_df[rec_stats_df['Quarter'] == quarter_str] if not rec_stats_df.empty else pd.DataFrame()

    for conf in team_data:
        c_name, base, role = conf['name'], conf['base_salary'], conf.get('role', 'Consultant')
        is_tl, is_int = (role == "Team Lead"), (role == "Intern")
        target_gp = 0 if is_int else base * (4.5 if is_tl else 9.0)
        
        c_sales = q_sales[q_sales['Consultant'] == c_name].copy() if not q_sales.empty else pd.DataFrame()
        sent_count = q_rec[q_rec['Consultant'] == c_name]['Sent'].sum() if not q_rec.empty else 0
        
        booked_gp = c_sales['GP'].sum() if not c_sales.empty else 0
        fin_pct = (booked_gp / target_gp * 100) if target_gp > 0 else 0
        rec_pct = (sent_count / CV_TARGET_QUARTERLY * 100)
        
        is_target_met = (fin_pct >= 100 or rec_pct >= 100)
        total_comm, paid_gp, current_level = 0, 0, 0

        if not is_int and not c_sales.empty:
            paid_sales = c_sales[c_sales['Status'] == 'Paid'].copy()
            if not paid_sales.empty:
                paid_sales['Payment Date Obj'] = pd.to_datetime(paid_sales['Payment Date Obj'])
                paid_sales = paid_sales.sort_values(by='Payment Date Obj')
                paid_sales['Month_Key'] = paid_sales['Payment Date Obj'].dt.to_period('M')
                running_paid_gp = 0
                for m_key in sorted(paid_sales['Month_Key'].unique()):
                    m_deals = paid_sales[paid_sales['Month_Key'] == m_key]
                    running_paid_gp += m_deals['GP'].sum()
                    level, mult = calculate_commission_tier(running_paid_gp, base, is_tl)
                    current_level = level
                    if is_target_met:
                        for idx, row in m_deals.iterrows():
                            comm = calculate_single_deal_commission(row['Candidate Salary'], mult) * row['Percentage']
                            total_comm += comm
                            c_sales.loc[idx, 'Commission'] = comm
                paid_gp = running_paid_gp
        
        # TL Override
        if is_tl and is_target_met and not q_sales.empty:
            override_deals = q_sales[(q_sales['Status'] == 'Paid') & (q_sales['Consultant'] != c_name) & (q_sales['Consultant'] != "Estela Peng")]
            for _, row in override_deals.iterrows():
                total_comm += 1000

        summary.append({
            "Consultant": c_name, "Role": role, "Quarter": quarter_str, "GP Target": target_gp, 
            "Booked GP": booked_gp, "Paid GP": paid_gp, "Fin %": fin_pct, "CV %": rec_pct,
            "Target Met": "✅" if is_target_met else "❌", "Level": current_level, "Payable Comm.": total_comm
        })
        updated_deals.append(c_sales)
        
    return pd.DataFrame(summary), pd.concat(updated_deals) if updated_deals else pd.DataFrame()

# ==========================================
# 🚀 MAIN APP
# ==========================================
def main():
    st.title("💼 Management Dashboard")
    st.caption(f"📅 Current Quarter: **{CURRENT_Q_STR}** | Snapshot: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    client = connect_to_google()
    if not client: st.error("❌ Google Auth Failed"); return

    if st.button("🔄 REFRESH ALL DATA", type="primary"):
        with st.spinner("⏳ Fetching data across all sheets..."):
            # Team roles
            team_data = []
            for c in TEAM_CONFIG:
                team_data.append({**c, "role": fetch_role(client, c['id'])})
            
            # Rec Stats
            rec_all = []
            rec_logs = []
            ref_sheet = client.open_by_key(TEAM_CONFIG[0]['id'])
            all_months = [ws.title for ws in ref_sheet.worksheets() if ws.title.isdigit() and len(ws.title) == 6]
            
            for m in all_months:
                for c in TEAM_CONFIG:
                    s, i, o, d = internal_fetch_sheet_data(client, c, m)
                    q = f"{m[:4]} Q{(int(m[4:])-1)//3 + 1}"
                    rec_all.append({"Consultant": c['name'], "Sent": s, "Int": i, "Off": o, "Quarter": q, "Year": m[:4]})
                    rec_logs.extend(d)
            
            # Sales
            sales_df = fetch_all_sales(client)
            
            st.session_state['data'] = {
                "team": team_data, "rec": pd.DataFrame(rec_all), "logs": pd.DataFrame(rec_logs),
                "sales": sales_df, "ts": datetime.now().strftime("%H:%M:%S")
            }
            st.rerun()

    if 'data' not in st.session_state:
        st.info("👋 Welcome! Click 'REFRESH ALL DATA' to load the dashboard."); st.stop()

    d = st.session_state['data']
    tab_dash, tab_det, tab_logs = st.tabs(["📊 DASHBOARD", "📝 FINANCIAL DETAILS", "📜 RECRUITMENT LOGS"])

    with tab_dash:
        # --- Recruitment Section ---
        st.markdown(f"### 🎯 Recruitment Stats ({CURRENT_Q_STR})")
        curr_rec = d['rec'][d['rec']['Quarter'] == CURRENT_Q_STR].groupby('Consultant')[['Sent','Int','Off']].sum().reset_index()
        curr_rec['Activity %'] = (curr_rec['Sent'] / CV_TARGET_QUARTERLY * 100).clip(0, 100)
        st.dataframe(curr_rec, use_container_width=True, hide_index=True, column_config={
            "Activity %": st.column_config.ProgressColumn(format="%.0f%%", min_value=0, max_value=100)
        })
        
        with st.expander("📜 Historical Recruitment Stats (Same Format)"):
            hist_rec = d['rec'][d['rec']['Quarter'] != CURRENT_Q_STR].groupby(['Quarter','Consultant'])[['Sent','Int','Off']].sum().reset_index()
            hist_rec['Activity %'] = (hist_rec['Sent'] / CV_TARGET_QUARTERLY * 100).clip(0, 100)
            st.dataframe(hist_rec.sort_values(['Quarter','Consultant'], ascending=[False, True]), use_container_width=True, hide_index=True, column_config={
                "Activity %": st.column_config.ProgressColumn(format="%.0f%%", min_value=0, max_value=100)
            })

        st.divider()

        # --- Financial Section ---
        st.markdown(f"### 💰 Financial Performance ({CURRENT_Q_STR})")
        curr_fin_sum, _ = get_financial_summary(d['sales'], d['rec'], CURRENT_Q_STR, d['team'])
        st.dataframe(curr_fin_sum, use_container_width=True, hide_index=True, column_config={
            "Fin %": st.column_config.ProgressColumn(format="%.0f%%", min_value=0, max_value=100),
            "CV %": st.column_config.ProgressColumn(format="%.0f%%", min_value=0, max_value=100),
            "Payable Comm.": st.column_config.NumberColumn(format="$%d")
        })

        with st.expander("📜 Historical Financial Target Achievement"):
            hist_quarters = [q for q in d['rec']['Quarter'].unique() if q != CURRENT_Q_STR]
            hist_fin_all = []
            for q in sorted(hist_quarters, reverse=True):
                h_sum, _ = get_financial_summary(d['sales'], d['rec'], q, d['team'])
                hist_fin_all.append(h_sum)
            if hist_fin_all:
                st.dataframe(pd.concat(hist_fin_all), use_container_width=True, hide_index=True, column_config={
                    "Payable Comm.": st.column_config.NumberColumn(format="$%d")
                })

    with tab_det:
        st.markdown("### 🔍 Sales Drill Down")
        for yr in ["2026", "2025"]:
            st.markdown(f"#### Year: {yr}")
            yr_sales = d['sales'][d['sales']['Year'] == yr]
            if not yr_sales.empty:
                st.dataframe(yr_sales[['Quarter', 'Consultant', 'Candidate Salary', 'GP', 'Status']], use_container_width=True, hide_index=True)
            else: st.info(f"No sales data for {yr}")

    with tab_logs:
        st.markdown("### 📝 Recruitment Logs")
        for yr in ["2026", "2025"]:
            with st.expander(f"📅 View Logs for {yr}"):
                yr_logs = d['logs'][d['logs']['Year'] == yr]
                if not yr_logs.empty:
                    st.dataframe(yr_logs.groupby(['Month','Company','Position','Status'])['Count'].sum().reset_index().sort_values('Month', ascending=False), use_container_width=True, hide_index=True)
                else: st.info(f"No logs for {yr}")

if __name__ == "__main__":
    main()
