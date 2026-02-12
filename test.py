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
now = datetime.now()
CURRENT_YEAR = now.year
CURRENT_QUARTER = (now.month - 1) // 3 + 1
CURRENT_Q_STR = f"{CURRENT_YEAR} Q{CURRENT_QUARTER}"

if CURRENT_QUARTER == 1:
    PREV_Q_STR = f"{CURRENT_YEAR - 1} Q4"
    prev_q_year = CURRENT_YEAR - 1
    prev_q_start_m = 10
else:
    PREV_Q_STR = f"{CURRENT_YEAR} Q{CURRENT_QUARTER - 1}"
    prev_q_year = CURRENT_YEAR
    prev_q_start_m = (CURRENT_QUARTER - 2) * 3 + 1

prev_q_months = [f"{prev_q_year}{m:02d}" for m in range(prev_q_start_m, prev_q_start_m + 3)]
start_m = (CURRENT_QUARTER - 1) * 3 + 1
curr_q_months = [f"{CURRENT_YEAR}{m:02d}" for m in range(start_m, start_m + 3)]
quanbu = prev_q_months + curr_q_months

CV_TARGET_QUARTERLY = 87
SALES_SHEET_ID = '1jniQ-GpeMINjQMebniJ_J1eLVLQIR1NGbSjTtOFP9Q8'
SALES_TAB_NAME = 'Positions'

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


def keep_alive_worker():
    app_url = st.secrets.get("public_url", None)
    while True:
        try:
            time.sleep(300)
            if app_url: requests.get(app_url, timeout=30)
        except:
            pass


if 'keep_alive_started' not in st.session_state:
    t = threading.Thread(target=keep_alive_worker, daemon=True)
    t.start()
    st.session_state['keep_alive_started'] = True


# --- 🧮 辅助函数 ---
def get_quarter_str(date_obj):
    if pd.isna(date_obj): return "Unknown"
    q = (date_obj.month - 1) // 3 + 1
    return f"{date_obj.year} Q{q}"


def calculate_commission_tier(total_gp, base_salary, is_team_lead=False):
    if is_team_lead:
        t1, t2, t3 = 4.5, 6.75, 11.25
    else:
        t1, t2, t3 = 9.0, 13.5, 22.5
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
        p_date = pd.to_datetime(payment_date)
        year = p_date.year + (p_date.month // 12)
        month = (p_date.month % 12) + 1
        return datetime(year, month, 15)
    except:
        return None


def get_payout_date_from_month_key(month_key):
    try:
        dt = datetime.strptime(str(month_key), "%Y-%m")
        year = dt.year + (dt.month // 12)
        month = (dt.month % 12) + 1
        return datetime(year, month, 15)
    except:
        return None


def normalize_text(text):
    return ''.join(c for c in unicodedata.normalize('NFD', str(text)) if unicodedata.category(c) != 'Mn').lower()


def safe_api_call(func, *args, **kwargs):
    max_retries = 5
    for i in range(max_retries):
        try:
            return func(*args, **kwargs)
        except APIError as e:
            if "429" in str(e):
                time.sleep(2 * (2 ** i) + random.uniform(0, 1))
            else:
                raise e
    return None


def connect_to_google():
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    if "gcp_service_account" in st.secrets:
        creds = ServiceAccountCredentials.from_json_keyfile_dict(dict(st.secrets["gcp_service_account"]), scope)
        return gspread.authorize(creds)
    return None


def fetch_role_from_personal_sheet(client, sheet_id):
    try:
        sheet = safe_api_call(client.open_by_key, sheet_id)
        ws = safe_api_call(sheet.worksheet, 'Credentials')
        role = safe_api_call(ws.acell, 'B1').value
        return role.strip() if role else "Consultant"
    except:
        return "Consultant"


def fetch_recruitment_stats(client, months):
    all_stats, all_details = [], []
    for month in months:
        for consultant in TEAM_CONFIG:
            s, i, o, d = internal_fetch_sheet_data(client, consultant, month)
            all_stats.append({"Consultant": consultant['name'], "Month": month, "Sent": s, "Int": i, "Off": o})
            if d: all_details.extend(d)
    return pd.DataFrame(all_stats), pd.DataFrame(all_details)


def internal_fetch_sheet_data(client, conf, tab):
    try:
        sheet = safe_api_call(client.open_by_key, conf['id'])
        ws = safe_api_call(sheet.worksheet, tab)
        rows = safe_api_call(ws.get_all_values)
        details, cs, ci, co = [], 0, 0, 0
        target_key = conf.get('keyword', 'Name')
        COMPANY_KEYS, POSITION_KEYS, STAGE_KEYS = ["Company", "Client", "Cliente", "公司", "客户"], ["Position", "Role",
                                                                                                     "职位"], ["Stage",
                                                                                                               "Status",
                                                                                                               "阶段"]
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
                res.append(
                    {"Consultant": conf['name'], "Month": tab, "Company": b['c'], "Position": b['p'], "Status": stat,
                     "Count": 1})
            return res

        for r in rows:
            if not r: continue
            fc = r[0].strip()
            if fc in COMPANY_KEYS:
                details.extend(flush(block)); block = {"c": r[1] if len(r) > 1 else "Unk", "p": "Unk", "cands": {}}
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

            # --- 优化表头匹配逻辑 ---
            if not found_header:
                # 只要一行里同时出现了 "consultant" 和 "onboarding" 就算找到了表头
                if any("consultant" in c for c in row_lower) and any("onboarding" in c for c in row_lower):
                    for idx, cell in enumerate(row_lower):
                        if "consultant" in cell: col_cons = idx
                        if "onboarding" in cell and "date" in cell: col_onboard = idx
                        if "candidate" in cell and "salary" in cell: col_sal = idx
                        if "payment" in cell and "date" in cell: col_pay = idx
                        if "percentage" in cell or cell == "%" or "pct" in cell: col_pct = idx
                    found_header = True
                    continue

            if found_header:
                # 停止条件
                if "POSITION" in " ".join(row_lower).upper() and "PLACED" not in " ".join(row_lower).upper(): break
                if len(row) <= max(col_cons, col_onboard): continue

                consultant_name = row[col_cons].strip()
                if not consultant_name: continue

                # 日期解析
                onboard_date = None
                for fmt in date_formats:
                    try:
                        onboard_date = datetime.strptime(row[col_onboard].strip(), fmt)
                        break
                    except:
                        pass

                if not onboard_date: continue

                # 匹配顾问姓名
                matched = "Unknown"
                c_norm = normalize_text(consultant_name)
                for conf in TEAM_CONFIG:
                    conf_norm = normalize_text(conf['name'])
                    if conf_norm in c_norm or c_norm in conf_norm:
                        matched = conf['name']
                        break

                if matched == "Unknown": continue

                # 薪资与提成比
                try:
                    salary = float(str(row[col_sal]).replace(',', '').replace('$', '').strip())
                except:
                    salary = 0

                pct_val = 1.0
                if col_pct != -1 and len(row) > col_pct:
                    try:
                        p_str = str(row[col_pct]).replace('%', '').strip()
                        p_float = float(p_str)
                        pct_val = p_float / 100.0 if p_float > 1.0 else p_float
                    except:
                        pct_val = 1.0

                calc_gp = salary * (1.0 if salary < 20000 else 1.5) * pct_val

                # 付款状态
                pay_date_obj, status = None, "Pending"
                if col_pay != -1 and len(row) > col_pay:
                    pay_str = row[col_pay].strip()
                    if len(pay_str) > 5:
                        status = "Paid"
                        for fmt in date_formats:
                            try:
                                pay_date_obj = datetime.strptime(pay_str, fmt)
                                break
                            except:
                                pass

                sales_records.append({
                    "Consultant": matched, "GP": calc_gp, "Candidate Salary": salary, "Percentage": pct_val,
                    "Onboard Date Obj": onboard_date, "Onboard Date Str": onboard_date.strftime("%Y-%m-%d"),
                    "Payment Date": row[col_pay].strip() if col_pay != -1 and len(row) > col_pay else "",
                    "Payment Date Obj": pay_date_obj, "Status": status, "Quarter": get_quarter_str(onboard_date)
                })
        return pd.DataFrame(sales_records)
    except Exception as e:
        st.error(f"Data Fetch Error: {e}")
        return pd.DataFrame()


def load_data_from_api(client, quanbu):
    team_data = []
    for conf in TEAM_CONFIG:
        member = conf.copy()
        member['role'] = fetch_role_from_personal_sheet(client, conf['id'])
        team_data.append(member)
    rec_stats_df, rec_details_df = fetch_recruitment_stats(client, quanbu)
    all_sales_df = fetch_all_sales_data(client)
    return {"team_data": team_data, "rec_stats": rec_stats_df, "rec_details": rec_details_df,
            "rec_hist": pd.DataFrame(), "sales_all": all_sales_df, "last_updated": datetime.now().strftime("%H:%M:%S")}


def main():
    st.title("💼 Management Dashboard")
    client = connect_to_google()
    if not client: st.error("❌ API Error"); return

    col1, col2 = st.columns([1, 5])
    with col1:
        if st.button("🔄 REFRESH DATA", type="primary"):
            with st.spinner("⏳ Fetching ..."):
                data_package = load_data_from_api(client, quanbu)
                st.session_state['data_cache'] = data_package
                st.rerun()

    if 'data_cache' not in st.session_state: st.stop()

    cache = st.session_state['data_cache']
    dynamic_team_config = cache['team_data']
    rec_stats_df, all_sales_df = cache['rec_stats'], cache['sales_all']
    sales_df_2q = all_sales_df[
        all_sales_df['Quarter'].isin([CURRENT_Q_STR, PREV_Q_STR])].copy() if not all_sales_df.empty else pd.DataFrame()

    tab_dash, tab_details = st.tabs(["📊 DASHBOARD", "📝 DETAILS"])

    with tab_dash:
        def get_role_target(c_name):
            for member in dynamic_team_config:
                if member['name'] == c_name: return member.get('role', 'Consultant'), CV_TARGET_QUARTERLY
            return 'Consultant', CV_TARGET_QUARTERLY

        st.markdown(f"### 🎯 Recruitment Stats (Q{CURRENT_QUARTER})")
        if not rec_stats_df.empty:
            rec_curr = rec_stats_df[rec_stats_df['Month'].isin(curr_q_months)]
            rec_summary = rec_curr.groupby('Consultant')[['Sent', 'Int', 'Off']].sum().reset_index()
            rec_summary[['Role', 'CV Target']] = rec_summary['Consultant'].apply(
                lambda x: pd.Series(get_role_target(x)))
            rec_summary['Activity %'] = (rec_summary['Sent'] / rec_summary['CV Target']).fillna(0) * 100
            rec_summary['Int Rate'] = (rec_summary['Int'] / rec_summary['Sent']).fillna(0) * 100
            st.dataframe(rec_summary, use_container_width=True, hide_index=True, column_config={
                "Activity %": st.column_config.ProgressColumn("Activity %", format="%.0f%%", min_value=0,
                                                              max_value=100)})

        st.divider()
        st.markdown(f"### 💰 Financial Performance (Q{CURRENT_QUARTER})")
        financial_curr, financial_hist, updated_sales_records, team_lead_overrides = [], [], [], []

        for conf in dynamic_team_config:
            c_name, base, role = conf['name'], conf['base_salary'], conf.get('role', 'Consultant')
            is_intern, is_team_lead = (role == "Intern"), (role == "Team Lead")
            gp_target = 0 if is_intern else base * (4.5 if is_team_lead else 9.0)

            # 这里的筛选一定要准确
            c_sales = sales_df_2q[
                sales_df_2q['Consultant'] == c_name].copy() if not sales_df_2q.empty else pd.DataFrame()

            # 分开当前季度和历史季度的数据
            c_sales_curr = c_sales[c_sales['Quarter'] == CURRENT_Q_STR] if not c_sales.empty else pd.DataFrame()
            c_sales_hist = c_sales[c_sales['Quarter'] == PREV_Q_STR] if not c_sales.empty else pd.DataFrame()

            # 计算 Paid GP 用于 Dashboard 显示 (只要上岗且已付就算)
            paid_gp_curr_display = c_sales_curr[c_sales_curr['Status'] == 'Paid']['GP'].sum()
            paid_gp_hist_display = c_sales_hist[c_sales_hist['Status'] == 'Paid']['GP'].sum()

            # ... (后面接简历统计和达标判定) ...

            # --- 达标判定 ---
            achieved_curr, is_target_met_curr = [], False
            if is_intern:
                if rec_pct_curr >= 100: achieved_curr.append("Activity"); is_target_met_curr = True
            else:
                if fin_curr >= 100: achieved_curr.append("Financial"); is_target_met_curr = True
                if rec_pct_curr >= 100: achieved_curr.append("Activity"); is_target_met_curr = True
            status_text_curr = " & ".join(achieved_curr) if achieved_curr else "In Progress"

            achieved_hist, is_target_met_hist = [], False
            if is_intern:
                if rec_pct_hist >= 100: achieved_hist.append("Activity"); is_target_met_hist = True
            else:
                if fin_hist >= 100: achieved_hist.append("Financial"); is_target_met_hist = True
                if rec_pct_hist >= 100: achieved_hist.append("Activity"); is_target_met_hist = True
            status_text_hist = " & ".join(achieved_hist) if achieved_hist else "Below Target"

            # --- 佣金逻辑计算 (明细 + 汇总) ---
            total_comm_curr, total_comm_hist = 0, 0
            if not is_intern and not c_sales.empty:
                # 寻找日期列
                t_col = next((c for c in ['Onboard Date Obj', 'Onboard Date Str'] if c in c_sales.columns), None)
                if t_col:
                    c_sales['Payment Date Obj'] = pd.to_datetime(c_sales['Payment Date Obj'], errors='coerce')
                    c_sales['Applied Level'], c_sales['Final Comm'], c_sales['Commission Day'] = 0, 0.0, ""

                    for q_name in [PREV_Q_STR, CURRENT_Q_STR]:
                        q_mask = c_sales['Quarter'] == q_name
                        if not q_mask.any(): continue

                        target_is_met = is_target_met_curr if q_name == CURRENT_Q_STR else is_target_met_hist
                        q_data = c_sales[q_mask].copy().sort_values(by='Onboard Date Obj')
                        running_onboard_gp = 0
                        _, level1_mult = calculate_commission_tier(base + 1, base, is_team_lead)

                        for idx, row in q_data.iterrows():
                            running_onboard_gp += row['GP']
                            level, multiplier = calculate_commission_tier(running_onboard_gp, base, is_team_lead)

                            # 【核心补发逻辑】只要总业绩达标，Level 0 自动转 Level 1
                            if target_is_met and level == 0: level, multiplier = 1, level1_mult

                            c_sales.at[idx, 'Applied Level'] = level
                            if target_is_met and row['Status'] == 'Paid' and level > 0:
                                comm = calculate_single_deal_commission(row['Candidate Salary'], multiplier) * row[
                                    'Percentage']
                                p_date = get_commission_pay_date(row['Payment Date Obj'])
                                c_sales.at[idx, 'Final Comm'] = comm
                                if p_date:
                                    c_sales.at[idx, 'Commission Day'] = p_date.strftime("%Y-%m-%d")
                                    if p_date <= datetime.now() + timedelta(days=20):
                                        if q_name == CURRENT_Q_STR:
                                            total_comm_curr += comm
                                        else:
                                            total_comm_hist += comm
                updated_sales_records.append(c_sales)
            else:
                updated_sales_records.append(c_sales)

            # 主管额外提成
            if not is_intern and is_team_lead and is_target_met_curr and not sales_df_2q.empty:
                ov_mask = (sales_df_2q['Status'] == 'Paid') & (sales_df_2q['Consultant'] != c_name) & (
                            sales_df_2q['Consultant'] != "Estela Peng")
                for _, row in sales_df_2q[ov_mask].iterrows():
                    p_date = get_commission_pay_date(row['Payment Date Obj'])
                    if p_date and p_date <= datetime.now() + timedelta(days=20):
                        bonus = 1000 * row['Percentage']
                        total_comm_curr += bonus
                        team_lead_overrides.append(
                            {"Leader": c_name, "Source": row['Consultant'], "Salary": row['Candidate Salary'],
                             "Percentage": row['Percentage'], "Date": p_date.strftime("%Y-%m-%d"), "Bonus": bonus})

            financial_curr.append({"Consultant": c_name, "Role": role, "GP Target": gp_target,
                                   "Paid GP": c_sales_curr['GP'].sum() if not c_sales_curr.empty else 0,
                                   "Fin %": fin_curr, "Status": status_text_curr, "Est. Commission": total_comm_curr})
            financial_hist.append({"Consultant": c_name, "Role": role, "GP Target": gp_target,
                                   "Paid GP": c_sales_hist['GP'].sum() if not c_sales_hist.empty else 0,
                                   "Fin %": fin_hist, "Status": status_text_hist, "Est. Commission": total_comm_hist})

        final_sales_df = pd.concat(updated_sales_records) if updated_sales_records else pd.DataFrame()
        override_df = pd.DataFrame(team_lead_overrides)
        st.dataframe(pd.DataFrame(financial_curr).sort_values('Paid GP', ascending=False), use_container_width=True,
                     hide_index=True,
                     column_config={"Est. Commission": st.column_config.NumberColumn("Payable Comm.", format="$%d"),
                                    "Fin %": st.column_config.ProgressColumn("Financial % (Booked)", format="%.0f%%",
                                                                             min_value=0, max_value=100)})

    with tab_details:
        st.markdown("### 🔍 Drill Down Details")
        for conf in dynamic_team_config:
            c_name = conf['name']
            with st.expander(f"👤 {c_name}"):
                if not final_sales_df.empty:
                    c_view = final_sales_df[final_sales_df['Consultant'] == c_name]
                    for q_name in [PREV_Q_STR, CURRENT_Q_STR]:
                        q_data = c_view[c_view['Quarter'] == q_name]
                        if not q_data.empty:
                            st.markdown(f"**📅 {q_name}**")
                            st.dataframe(q_data[
                                             ['Onboard Date Str', 'Payment Date', 'Commission Day', 'Candidate Salary',
                                              'GP', 'Status', 'Applied Level', 'Final Comm']], use_container_width=True,
                                         hide_index=True)


if __name__ == "__main__":
    main()
