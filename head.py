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
now = datetime.now()
CURRENT_YEAR = now.year
CURRENT_QUARTER = (now.month - 1) // 3 + 1
CURRENT_Q_STR = f"{CURRENT_YEAR} Q{CURRENT_QUARTER}"

# Calculate months for current quarter fetching (e.g., 202601, 202602, 202603)
start_m = (CURRENT_QUARTER - 1) * 3 + 1
QUARTER_MONTHS_STR = [f"{CURRENT_YEAR}{m:02d}" for m in range(start_m, start_m + 3)]

SALES_SHEET_ID = '1jniQ-GpeMINjQMebniJ_J1eLVLQIR1NGbSjTtOFP9Q8'
SALES_TAB_NAME = 'Positions'
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

# --- 🎨 STYLES ---
st.markdown("""
    <style>
    .stApp { background-color: #FFFFFF; color: #000000; }
    h1, h2, h3, h4 { color: #333333 !important; font-family: 'Arial', sans-serif; }
    .stButton>button { background-color: #0056b3; color: white; border: none; border-radius: 4px; padding: 10px 24px; font-weight: bold; }
    .dataframe { font-size: 13px !important; }
    div[data-testid="metric-container"] { background-color: #f8f9fa; border: 1px solid #e9ecef; border-radius: 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.05); }
    </style>
    """, unsafe_allow_html=True)


# --- 🛡️ KEEP ALIVE WORKER ---
def keep_alive_worker():
    while True:
        try:
            time.sleep(300)
            print(f"💓 [KeepAlive] Heartbeat: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        except:
            pass


if 'keep_alive_started' not in st.session_state:
    t = threading.Thread(target=keep_alive_worker, daemon=True)
    t.start()
    st.session_state['keep_alive_started'] = True


# ==========================================
# 🧮 2. HELPER FUNCTIONS
# ==========================================
def get_quarter_str(date_obj):
    if pd.isna(date_obj): return "Unknown"
    q = (date_obj.month - 1) // 3 + 1
    return f"{date_obj.year} Q{q}"


def calculate_commission_tier(total_gp, base_salary, is_team_lead=False):
    t1, t2, t3 = (4.5, 6.75, 11.25) if is_team_lead else (9.0, 13.5, 22.5)
    if total_gp < t1 * base_salary:
        return 0, 0
    elif total_gp < t2 * base_salary:
        return 1, 1
    elif total_gp < t3 * base_salary:
        return 2, 2
    else:
        return 3, 3


def calculate_single_deal_commission(candidate_salary, multiplier):
    if multiplier == 0: return 0
    if candidate_salary < 20000:
        base_comm = 1000
    elif candidate_salary < 30000:
        base_comm = candidate_salary * 0.05
    elif candidate_salary < 50000:
        base_comm = candidate_salary * 1.5 * 0.05
    else:
        base_comm = candidate_salary * 2.0 * 0.05
    return base_comm * multiplier


def get_commission_pay_date(payment_date):
    if pd.isna(payment_date) or not payment_date: return None
    try:
        year = payment_date.year + (payment_date.month // 12)
        month = (payment_date.month % 12) + 1
        return datetime(year, month, 15)
    except:
        return None


def normalize_text(text):
    return ''.join(c for c in unicodedata.normalize('NFD', str(text)) if unicodedata.category(c) != 'Mn').lower()


def safe_api_call(func, *args, **kwargs):
    for i in range(5):
        try:
            return func(*args, **kwargs)
        except Exception as e:
            if "429" in str(e): time.sleep(2 * (2 ** i)); continue
            raise e
    return None


def connect_to_google():
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    if "gcp_service_account" in st.secrets:
        try:
            creds = ServiceAccountCredentials.from_json_keyfile_dict(dict(st.secrets["gcp_service_account"]), scope)
            return gspread.authorize(creds)
        except:
            return None
    return None


# ==========================================
# 📥 3. DATA FETCHING LOGIC
# ==========================================
def fetch_role(client, sheet_id):
    try:
        sheet = safe_api_call(client.open_by_key, sheet_id)
        ws = safe_api_call(sheet.worksheet, 'Credentials')
        return safe_api_call(ws.acell, 'B1').value.strip() or "Consultant"
    except:
        return "Consultant"


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
                res.append(
                    {"Consultant": conf['name'], "Month": tab, "Year": tab[:4], "Company": b['c'], "Position": b['p'],
                     "Status": "Offered" if is_off else ("Interviewed" if is_int else "Sent"), "Count": 1})
            return res

        for r in rows:
            if not r: continue
            fc = r[0].strip()
            if fc in COMPANY_KEYS:
                details.extend(flush(block))
                block = {"c": r[1] if len(r) > 1 else "Unk", "p": "Unk", "cands": {}}
            elif fc in POSITION_KEYS:
                block['p'] = r[1] if len(r) > 1 else "Unk"
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
    except:
        return 0, 0, 0, []


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
                if any("linkeazi" in c and "consultant" in c for c in row_lower) and any(
                        "onboarding" in c for c in row_lower):
                    for idx, cell in enumerate(row_lower):
                        if "linkeazi" in cell and "consultant" in cell: col_cons = idx
                        if "onboarding" in cell and "date" in cell: col_onboard = idx
                        if "candidate" in cell and "salary" in cell: col_sal = idx
                        if "payment" in cell and "onboard" not in cell: col_pay = idx
                        if "percentage" in cell or cell == "%" or "pct" in cell: col_pct = idx
                    found_header = True;
                    continue
            if found_header:
                if "POSITION" in " ".join(row_lower).upper() and "PLACED" not in " ".join(row_lower).upper(): break
                if len(row) <= max(col_cons, col_onboard, col_sal): continue
                c_name_raw = row[col_cons].strip()
                if not c_name_raw: continue
                onboard_date = None
                for fmt in date_formats:
                    try:
                        onboard_date = datetime.strptime(row[col_onboard].strip(), fmt); break
                    except:
                        pass
                if not onboard_date: continue
                matched = "Unknown"
                c_norm = normalize_text(c_name_raw)
                for conf in TEAM_CONFIG:
                    conf_norm = normalize_text(conf['name'])
                    if conf_norm in c_norm or c_norm in conf_norm or conf_norm.split()[0] in c_norm: matched = conf[
                        'name']; break
                if matched == "Unknown": continue
                try:
                    salary = float(str(row[col_sal]).replace(',', '').replace('$', '').strip())
                except:
                    salary = 0
                pct = 1.0
                if col_pct != -1 and len(row) > col_pct:
                    try:
                        p_float = float(str(row[col_pct]).replace('%', '').strip())
                        pct = p_float / 100.0 if p_float > 1.0 else p_float
                    except:
                        pct = 1.0
                calc_gp = salary * (1.0 if salary < 20000 else 1.5) * pct
                pay_date_obj, status = None, "Pending"
                if col_pay != -1 and len(row) > col_pay:
                    pay_str = row[col_pay].strip()
                    if len(pay_str) > 5:
                        status = "Paid"
                        for fmt in date_formats:
                            try:
                                pay_date_obj = datetime.strptime(pay_str, fmt); break
                            except:
                                pass
                sales_records.append({
                    "Consultant": matched, "GP": calc_gp, "Candidate Salary": salary, "Percentage": pct,
                    "Onboard Date": onboard_date, "Onboard Date Str": onboard_date.strftime("%Y-%m-%d"),
                    "Payment Date": row[col_pay].strip() if col_pay != -1 and len(row) > col_pay else "",
                    "Payment Date Obj": pay_date_obj, "Status": status, "Quarter": get_quarter_str(onboard_date),
                    "Year": str(onboard_date.year)
                })
        return pd.DataFrame(sales_records)
    except:
        return pd.DataFrame()


# ==========================================
# 📊 4. DASHBOARD CALCULATION ENGINE
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

        # --- 【关键修复：初始化所有可能缺失的列】 ---
        for col in ['Comm ($)', 'Applied Level', 'Comm. Date']:
            if col not in c_sales.columns:
                if col == 'Comm ($)':
                    c_sales[col] = 0.0
                elif col == 'Applied Level':
                    c_sales[col] = 0
                else:
                    c_sales[col] = ""

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
                        else:
                            paid_sales.at[idx, 'Comm ($)'] = 0.0
                        paid_sales.at[idx, 'Applied Level'] = lvl
                        pmt_date = row['Payment Date Obj']
                        paid_sales.at[idx, 'Comm. Date'] = (
                            datetime(pmt_date.year + (pmt_date.month // 12), (pmt_date.month % 12) + 1, 15)).strftime(
                            "%Y-%m-%d")
                paid_gp = running_gp
                c_sales.update(paid_sales)

        tl_overrides = []
        if is_tl and is_target_met and not q_sales.empty:
            others_paid = q_sales[(q_sales['Status'] == 'Paid') & (q_sales['Consultant'] != c_name) & (
                        q_sales['Consultant'] != "Estela Peng")]
            for _, row in others_paid.iterrows():
                total_comm += 1000
                pmt_date = pd.to_datetime(row['Payment Date Obj'])
                comm_date_str = (
                    datetime(pmt_date.year + (pmt_date.month // 12), (pmt_date.month % 12) + 1, 15)).strftime(
                    "%Y-%m-%d")
                tl_overrides.append({"Leader": c_name, "Source": row['Consultant'], "Salary": row['Candidate Salary'],
                                     "Date": comm_date_str, "Bonus": 1000})

        status = "Financial" if fin_pct >= 100 else ("Activity" if rec_pct >= 100 else "In Progress")
        summary.append({
            "Consultant": c_name, "Role": role, "GP Target": target_gp, "Paid GP": paid_gp,
            "Financial % (Booked)": fin_pct, "Status": status, "Level": level, "Payable Comm.": total_comm
        })
        details_map[c_name] = c_sales
        overrides_map[c_name] = pd.DataFrame(tl_overrides)

    return pd.DataFrame(summary).sort_values('Financial % (Booked)', ascending=False), details_map, overrides_map


def render_rec_table(df, title, roles_map):
    st.markdown(f"### 🎯 Recruitment Stats ({title})")
    if df.empty: st.info("No data available."); return
    summary = df.groupby('Consultant')[['Sent', 'Int', 'Off']].sum().reset_index()
    summary['Role'] = summary['Consultant'].map(roles_map)
    summary['Target (Q)'] = CV_TARGET_QUARTERLY
    summary['Activity %'] = (summary['Sent'] / summary['Target (Q)'] * 100).clip(0, 500)
    summary['Int/Sent'] = (summary['Int'] / summary['Sent'] * 100).fillna(0)
    total_row = pd.DataFrame(
        [{'Consultant': 'TOTAL', 'Role': '-', 'Target (Q)': summary['Target (Q)'].sum(), 'Sent': summary['Sent'].sum(),
          'Activity %': (summary['Sent'].sum() / summary['Target (Q)'].sum() * 100), 'Int': summary['Int'].sum(),
          'Off': summary['Off'].sum(),
          'Int/Sent': (summary['Int'].sum() / summary['Sent'].sum() * 100 if summary['Sent'].sum() > 0 else 0)}])
    final_df = pd.concat([summary, total_row], ignore_index=True)
    st.dataframe(final_df[['Consultant', 'Role', 'Target (Q)', 'Sent', 'Activity %', 'Int', 'Off', 'Int/Sent']],
                 use_container_width=True, hide_index=True, column_config={
            "Activity %": st.column_config.ProgressColumn(format="%.0f%%", min_value=0, max_value=100),
            "Int/Sent": st.column_config.NumberColumn(format="%.2f%%")})


# ==========================================
# 🚀 5. MAIN LOGIC (Updated with Historical Commissions)
# ==========================================
def main():
    st.title("💼 Management Dashboard")

    client = connect_to_google()
    if not client: st.error("❌ Google Auth Failed"); return

    if st.button("🔄 REFRESH ALL DATA", type="primary"):
        with st.spinner("⏳ Fetching data..."):
            team_data = []
            for c in TEAM_CONFIG:
                team_data.append({**c, "role": fetch_role(client, c['id'])})

            rec_all, rec_logs = [], []
            ref_sheet = client.open_by_key(TEAM_CONFIG[0]['id'])
            all_m = [ws.title for ws in ref_sheet.worksheets() if ws.title.isdigit() and len(ws.title) == 6]

            for m in all_m:
                for c in TEAM_CONFIG:
                    s, i, o, d_logs = internal_fetch_sheet_data(client, c, m)
                    q = f"{m[:4]} Q{(int(m[4:]) - 1) // 3 + 1}"
                    rec_all.append(
                        {"Consultant": c['name'], "Sent": s, "Int": i, "Off": o, "Quarter": q, "Year": m[:4]})
                    rec_logs.extend(d_logs)

            sales_df = fetch_all_sales_data(client)

            # --- 【新逻辑：计算历史所有季度的提成明细】 ---
            hist_comm_list = []
            if not sales_df.empty:
                all_qs = sorted(sales_df['Quarter'].unique(), reverse=True)
                for q in all_qs:
                    # 对每个季度运行提成逻辑
                    _, details_q, _ = calculate_financial_summary(sales_df, pd.DataFrame(rec_all), q, team_data)
                    for c_name, c_df in details_q.items():
                        # 只保留产生了提成的“Paid”记录
                        if 'Comm ($)' in c_df.columns:
                            paid_with_comm = c_df[(c_df['Status'] == 'Paid') & (c_df['Comm ($)'] > 0)].copy()
                            if not paid_with_comm.empty:
                                hist_comm_list.append(paid_with_comm)

            st.session_state['data'] = {
                "team": team_data,
                "rec": pd.DataFrame(rec_all),
                "logs": pd.DataFrame(rec_logs),
                "sales": sales_df,
                "hist_comm": pd.concat(hist_comm_list) if hist_comm_list else pd.DataFrame(),
                "ts": datetime.now().strftime("%H:%M:%S")
            }
            st.rerun()

    if 'data' not in st.session_state:
        st.info("👋 Welcome! Click 'REFRESH ALL DATA' to load dashboard.");
        st.stop()

    d = st.session_state['data']
    role_map = {m['name']: m['role'] for m in d['team']}

    # 计算当前季度数据用于汇总页
    df_fin_curr, details_curr, overrides_curr = calculate_financial_summary(d['sales'], d['rec'], CURRENT_Q_STR,
                                                                            d['team'])

    t_dash, t_det, t_logs = st.tabs(["📊 DASHBOARD", "📝 FINANCIAL DETAILS", "📜 RECRUITMENT LOGS"])

    with t_dash:
        # (这部分保持你原来的 render_rec_table_styled 和 render_fin_table_styled 逻辑不变)
        render_rec_table(d['rec'][d['rec']['Quarter'] == CURRENT_Q_STR], CURRENT_Q_STR, role_map)
        with st.expander("📜 Historical Recruitment Stats"):
            hist_qs = sorted([q for q in d['rec']['Quarter'].unique() if q != CURRENT_Q_STR], reverse=True)
            for q in hist_qs: render_rec_table(d['rec'][d['rec']['Quarter'] == q], q, role_map)
        st.divider()
        st.markdown(f"### 💰 Financial Performance ({CURRENT_Q_STR})")
        st.dataframe(df_fin_curr, use_container_width=True, hide_index=True)

    with t_det:
        st.markdown("### 🔍 Drill Down Details")
        for conf in d['team']:
            c_name = conf['name']
            try:
                fin_row = df_fin_curr[df_fin_curr['Consultant'] == c_name].iloc[0]
            except:
                continue

            with st.expander(f"👤 {c_name} ({fin_row['Role']}) | Status: {fin_row['Status']}"):
                # 1. 当前季度提成 (Current Quarter)
                if fin_row['Role'] != "Intern":
                    st.markdown("#### 💸 Current Quarter Breakdown")
                    c_curr = details_curr.get(c_name, pd.DataFrame())
                    if not c_curr.empty:
                        c_curr['Pct Display'] = c_curr['Percentage'].apply(lambda x: f"{int(x * 100)}%")
                        display_cols = ['Onboard Date Str', 'Payment Date', 'Comm. Date', 'Candidate Salary',
                                        'Pct Display', 'GP', 'Status', 'Applied Level', 'Comm ($)']
                        st.dataframe(c_curr[display_cols], use_container_width=True, hide_index=True)
                    else:
                        st.info("No deals for current quarter.")

                # 2. 【新增】历史提成汇总 (Historical Commission History)
                if fin_row['Role'] != "Intern":
                    st.divider()
                    st.markdown("#### 📜 Historical Commission History")
                    if not d['hist_comm'].empty:
                        # 筛选出该顾问的、且不属于当前季度的历史提成
                        h_view = d['hist_comm'][(d['hist_comm']['Consultant'] == c_name) & (
                                    d['hist_comm']['Quarter'] != CURRENT_Q_STR)].copy()
                        if not h_view.empty:
                            h_view['Pct Display'] = h_view['Percentage'].apply(lambda x: f"{int(x * 100)}%")
                            # 按发工资日期倒序排
                            h_view = h_view.sort_values('Comm. Date', ascending=False)
                            st.dataframe(h_view[['Comm. Date', 'Quarter', 'Onboard Date Str', 'Candidate Salary',
                                                 'Pct Display', 'GP', 'Applied Level', 'Comm ($)']],
                                         use_container_width=True, hide_index=True,
                                         column_config={"Comm ($)": st.column_config.NumberColumn(format="$%.2f")})
                        else:
                            st.info("No historical commission records found.")

                # 3. 团队提成 (Team Overrides)
                if fin_row['Role'] == 'Team Lead':
                    st.divider()
                    st.markdown("#### 👥 Team Overrides")
                    ov_view = overrides_curr.get(c_name, pd.DataFrame())
                    if not ov_view.empty:
                        st.dataframe(ov_view, use_container_width=True, hide_index=True)
                    else:
                        st.info("No overrides yet.")

    with t_logs:
        # (保持原有的 Recruitment Logs 逻辑不变)
        for yr in sorted(d['logs']['Year'].unique(), reverse=True):
            with st.expander(f"📅 Recruitment Logs {yr}"):
                df_yr = d['logs'][d['logs']['Year'] == yr]
                if not df_yr.empty: st.dataframe(
                    df_yr.groupby(['Month', 'Company', 'Position', 'Status'])['Count'].sum().reset_index().sort_values(
                        'Month', ascending=False), use_container_width=True, hide_index=True)


if __name__ == "__main__":
    main()
