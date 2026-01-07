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

# --- 自动获取当前系统时间 ---
now = datetime.now()
CURRENT_YEAR = now.year
CURRENT_QUARTER = (now.month - 1) // 3 + 1
CURRENT_Q_STR = f"{CURRENT_YEAR} Q{CURRENT_QUARTER}"

start_m = (CURRENT_QUARTER - 1) * 3 + 1
end_m = start_m + 2
quarter_months_str = [f"{CURRENT_YEAR}{m:02d}" for m in range(start_m, end_m + 1)]

CV_TARGET_QUARTERLY = 87

TEAM_CONFIG = [
    {"name": "Raul Solis", "id": "1vQuN-iNBRUug5J6gBMX-52jp6oogbA77SaeAf9j_zYs", "keyword": "Name", "base_salary": 11000},
    {"name": "Estela Peng", "id": "1sUkffAXzWnpzhhmklqBuwtoQylpR1U18zqBQ-lsp7Z4", "keyword": "姓名", "base_salary": 20800},
    {"name": "Ana Cruz", "id": "1VMVw5YCV12eI8I-VQSXEKg86J2IVZJEgjPJT7ggAFD0", "keyword": "Name", "base_salary": 13000},
    {"name": "Karina Albarran", "id": "1zc4ghvfjIxH0eJ2aXfopOWHqiyTDlD8yFNjBzpH07D8", "keyword": "Name", "base_salary": 15000},
]

st.set_page_config(page_title="Management Dashboard", page_icon="💼", layout="wide")

# ==========================================
# 🎨 统一表格格式配置
# ==========================================
def get_rec_config():
    return {
        "Consultant": st.column_config.TextColumn("Consultant", width=150),
        "Period": st.column_config.TextColumn("Period", width=100),
        "Role": st.column_config.TextColumn("Role", width=100),
        "CV Target": st.column_config.NumberColumn("Target (Q)", format="%d", width=100),
        "Sent": st.column_config.NumberColumn("Sent", format="%d", width=100),
        "Activity %": st.column_config.ProgressColumn("Activity %", format="%.0f%%", min_value=0, max_value=100, width=150),
        "Int": st.column_config.NumberColumn("Int", width=100),
        "Off": st.column_config.NumberColumn("Off", width=80),
        "Int Rate": st.column_config.NumberColumn("Int/Sent", format="%.2f%%", width=120),
    }

def get_fin_config():
    return {
        "Consultant": st.column_config.TextColumn("Consultant", width=150),
        "Quarter": st.column_config.TextColumn("Quarter", width=100),
        "Role": st.column_config.TextColumn("Role", width=100),
        "GP Target": st.column_config.NumberColumn("GP Target", format="$%d", width=100),
        "Paid GP": st.column_config.NumberColumn("Paid GP", format="$%d", width=100),
        "Fin %": st.column_config.ProgressColumn("Financial %", format="%.0f%%", min_value=0, max_value=100, width=150),
        "Status": st.column_config.TextColumn("Status", width=140),
        "Level": st.column_config.NumberColumn("Level", width=80),
        "Est. Commission": st.column_config.NumberColumn("Payable Comm.", format="$%d", width=130),
    }

# ==========================================
# 🛡️ 后台保持活跃
# ==========================================
def keep_alive_worker():
    app_url = st.secrets.get("public_url", None)
    while True:
        try:
            time.sleep(300)
            if app_url: requests.get(app_url, timeout=30)
        except: time.sleep(60)

if 'keep_alive_started' not in st.session_state:
    t = threading.Thread(target=keep_alive_worker, daemon=True)
    t.start()
    st.session_state['keep_alive_started'] = True

# ==========================================
# 🧮 辅助计算函数
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
        except APIError as e:
            if "429" in str(e): time.sleep(2 * (2**i) + random.uniform(0, 1))
            else: raise e
    return None

def connect_to_google():
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    try:
        if "gcp_service_account" in st.secrets:
            creds = ServiceAccountCredentials.from_json_keyfile_dict(dict(st.secrets["gcp_service_account"]), scope)
        else:
            creds = ServiceAccountCredentials.from_json_keyfile_name('credentials.json', scope)
        return gspread.authorize(creds)
    except: return None

# ==========================================
# 📊 数据获取函数
# ==========================================
def fetch_role_from_personal_sheet(client, sheet_id):
    try:
        sheet = safe_api_call(client.open_by_key, sheet_id)
        ws = safe_api_call(sheet.worksheet, 'Credentials')
        role = safe_api_call(ws.acell, 'B1').value
        return role.strip() if role else "Consultant"
    except: return "Consultant"

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
        hist_months = [ws.title.strip() for ws in worksheets if ws.title.strip().isdigit() and len(ws.title.strip())==6 and ws.title.strip() not in exclude_months]
        for month in hist_months:
            for consultant in TEAM_CONFIG:
                s, i, o, _ = internal_fetch_sheet_data(client, consultant, month)
                if s+i+o > 0: all_stats.append({"Consultant": consultant['name'], "Month": month, "Sent": s, "Int": i, "Off": o})
        return pd.DataFrame(all_stats)
    except: return pd.DataFrame()

def internal_fetch_sheet_data(client, conf, tab):
    try:
        sheet = safe_api_call(client.open_by_key, conf['id'])
        ws = safe_api_call(sheet.worksheet, tab)
        rows = safe_api_call(ws.get_all_values)
        details, cs, ci, co = [], 0, 0, 0
        target_key = conf.get('keyword', 'Name')
        block = {"c": "Unk", "p": "Unk", "cands": {}}
        def flush(b):
            res, nonlocal_s, nonlocal_i, nonlocal_o = [], 0, 0, 0
            for _, c_data in b['cands'].items():
                if not c_data.get('n'): continue
                stage = str(c_data.get('s', 'Sent')).lower()
                is_off = "offer" in stage
                is_int = ("interview" in stage) or ("面试" in stage) or is_off
                if is_off: nonlocal_o += 1
                if is_int: nonlocal_i += 1
                nonlocal_s += 1
                stat = "Offered" if is_off else ("Interviewed" if is_int else "Sent")
                res.append({"Consultant": conf['name'], "Month": tab, "Company": b['c'], "Position": b['p'], "Status": stat, "Count": 1})
            return res, nonlocal_s, nonlocal_i, nonlocal_o

        for r in rows:
            if not r: continue
            fc = r[0].strip()
            if fc in ["Company", "Client", "Cliente", "公司"]:
                d, s_inc, i_inc, o_inc = flush(block)
                details.extend(d); cs+=s_inc; ci+=i_inc; co+=o_inc
                block = {"c": r[1] if len(r)>1 else "Unk", "p": "Unk", "cands": {}}
            elif fc in ["Position", "Role", "职位"]: block['p'] = r[1] if len(r)>1 else "Unk"
            elif fc == target_key:
                for idx, v in enumerate(r[1:], 1):
                    if v.strip():
                        if idx not in block['cands']: block['cands'][idx] = {}
                        block['cands'][idx]['n'] = v.strip()
            elif fc in ["Stage", "Status", "状态"]:
                for idx, v in enumerate(r[1:], 1):
                    if v.strip():
                        if idx not in block['cands']: block['cands'][idx] = {}
                        block['cands'][idx]['s'] = v.strip()
        d, s_inc, i_inc, o_inc = flush(block)
        details.extend(d); cs+=s_inc; ci+=i_inc; co+=o_inc
        return cs, ci, co, details
    except: return 0, 0, 0, []

def fetch_all_sales_data(client):
    try:
        sheet = safe_api_call(client.open_by_key, SALES_SHEET_ID)
        ws = safe_api_call(sheet.worksheet, SALES_TAB_NAME)
        rows = safe_api_call(ws.get_all_values)
        col_cons, col_onboard, col_pay, col_sal, col_pct = -1, -1, -1, -1, -1
        sales_records, found_header = [], False
        date_formats = ["%Y-%m-%d", "%d/%m/%Y", "%Y/%m/%d", "%m/%d/%Y", "%d-%b-%y"]
        for row in rows:
            row_lower = [str(x).strip().lower() for x in row]
            if not found_header:
                if any("linkeazi" in c for c in row_lower) and any("onboarding" in c for c in row_lower):
                    for idx, cell in enumerate(row_lower):
                        if "linkeazi" in cell: col_cons = idx
                        if "onboarding" in cell: col_onboard = idx
                        if "candidate" in cell and "salary" in cell: col_sal = idx
                        if "payment" in cell and "onboard" not in cell: col_pay = idx
                        if "percentage" in cell or cell == "%": col_pct = idx
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
                for conf in TEAM_CONFIG:
                    if normalize_text(conf['name']) in normalize_text(c_name): matched = conf['name']; break
                if matched == "Unknown": continue
                try: salary = float(str(row[col_sal]).replace(',','').replace('$','').strip())
                except: salary = 0
                pct = 1.0
                if col_pct != -1:
                    try: 
                        p_val = float(str(row[col_pct]).replace('%','').strip())
                        pct = p_val/100 if p_val > 1 else p_val
                    except: pass
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
                    "Payment Date Obj": pay_date_obj, "Status": status, "Quarter": get_quarter_str(onboard_date)
                })
        return pd.DataFrame(sales_records)
    except: return pd.DataFrame()

def load_data_from_api(client, months):
    team_data = []
    for conf in TEAM_CONFIG:
        member = conf.copy()
        member['role'] = fetch_role_from_personal_sheet(client, conf['id'])
        team_data.append(member)
    rec_stats, rec_details = fetch_recruitment_stats(client, months)
    rec_hist = fetch_historical_recruitment_stats(client, months)
    all_sales = fetch_all_sales_data(client)
    return {"team_data": team_data, "rec_stats": rec_stats, "rec_details": rec_details, "rec_hist": rec_hist, "sales_all": all_sales, "last_updated": datetime.now().strftime("%H:%M:%S")}

# ==========================================
# 🚀 主程序
# ==========================================
def main():
    st.title("💼 Management Dashboard")
    client = connect_to_google()
    if not client: st.error("❌ Google API Connection Failed. Check Secrets/Credentials."); return

    if st.button("🔄 REFRESH DATA", type="primary"):
        with st.spinner("⏳ Fetching data..."):
            st.session_state['data_cache'] = load_data_from_api(client, quarter_months_str)
            st.rerun()

    if 'data_cache' not in st.session_state:
        st.info("👋 Click 'REFRESH DATA' to load the report."); st.stop()

    cache = st.session_state['data_cache']
    dynamic_team = cache['team_data']
    rec_stats, rec_details, rec_hist, all_sales = cache['rec_stats'], cache['rec_details'], cache['rec_hist'], cache['sales_all']

    if not all_sales.empty:
        curr_mask = (all_sales['Onboard Date'].dt.year == CURRENT_YEAR) & (all_sales['Onboard Date'].dt.month >= start_m) & (all_sales['Onboard Date'].dt.month <= end_m)
        sales_curr, sales_hist = all_sales[curr_mask].copy(), all_sales[~curr_mask].copy()
    else: sales_curr = sales_hist = pd.DataFrame()

    tab1, tab2 = st.tabs(["📊 DASHBOARD", "📝 DETAILS"])

    with tab1:
        # --- Recruitment Section ---
        st.markdown(f"### 🎯 Recruitment Stats (Q{CURRENT_QUARTER})")
        def process_rec(df, is_hist=False):
            if df.empty: return pd.DataFrame()
            summary = df.groupby(['Consultant', 'Month'] if is_hist else 'Consultant')[['Sent', 'Int', 'Off']].sum().reset_index()
            summary['Period'] = summary['Month'] if is_hist else CURRENT_Q_STR
            summary['Role'] = summary['Consultant'].apply(lambda x: next((m['role'] for m in dynamic_team if m['name']==x), "Consultant"))
            summary['CV Target'] = CV_TARGET_QUARTERLY
            summary['Activity %'] = (summary['Sent'] / summary['CV Target'] * 100).clip(upper=100)
            summary['Int Rate'] = (summary['Int'] / summary['Sent'] * 100).fillna(0)
            return summary

        curr_rec = process_rec(rec_stats)
        st.dataframe(curr_rec, use_container_width=True, hide_index=True, column_config=get_rec_config())

        with st.expander("📜 Historical Recruitment Data"):
            if not rec_hist.empty:
                hist_rec = process_rec(rec_hist, is_hist=True)
                st.dataframe(hist_rec.sort_values('Month', ascending=False), use_container_width=True, hide_index=True, column_config=get_rec_config())
            else: st.info("No historical recruitment data.")

        st.divider()

        # --- Financial Section ---
        st.markdown(f"### 💰 Financial Performance (Q{CURRENT_QUARTER})")
        def build_fin(sales_df, team_list, rec_df):
            res = []
            for conf in team_list:
                name, base, role = conf['name'], conf['base_salary'], conf.get('role', 'Consultant')
                is_lead = (role == "Team Lead")
                target = 0 if role == "Intern" else base * (4.5 if is_lead else 9.0)
                c_sales = sales_df[sales_df['Consultant'] == name] if not sales_df.empty else pd.DataFrame()
                booked = c_sales['GP'].sum()
                paid = c_sales[c_sales['Status'] == 'Paid']['GP'].sum()
                sent = rec_df[rec_df['Consultant'] == name]['Sent'].sum() if not rec_df.empty else 0
                
                achieved = []
                if target > 0 and (booked/target) >= 1: achieved.append("Financial")
                if (sent/CV_TARGET_QUARTERLY) >= 1: achieved.append("Activity")
                
                level, _ = calculate_commission_tier(paid, base, is_lead)
                res.append({"Consultant": name, "Role": role, "GP Target": target, "Paid GP": paid, "Fin %": (booked/target*100 if target>0 else 0), "Status": " & ".join(achieved) if achieved else "In Progress", "Level": level, "Est. Commission": 0})
            return pd.DataFrame(res)

        curr_fin = build_fin(sales_curr, dynamic_team, rec_stats)
        st.dataframe(curr_fin.sort_values('Paid GP', ascending=False), use_container_width=True, hide_index=True, column_config=get_fin_config())

        with st.expander("📜 Historical GP Summary"):
            if not sales_hist.empty:
                hist_fin_list = []
                for q in sorted(sales_hist['Quarter'].unique(), reverse=True):
                    q_data = build_fin(sales_hist[sales_hist['Quarter']==q], dynamic_team, pd.DataFrame())
                    q_data['Quarter'] = q
                    hist_fin_list.append(q_data[q_data['Paid GP'] > 0])
                if hist_fin_list:
                    st.dataframe(pd.concat(hist_fin_list), use_container_width=True, hide_index=True, column_config=get_fin_config())
            else: st.info("No historical financial data.")

    with tab2:
        st.info("Details view is active based on loaded data.")

if __name__ == "__main__":
    main()
