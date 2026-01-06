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

start_m = (CURRENT_QUARTER - 1) * 3 + 1
CURRENT_QUARTER_MONTHS = [f"{CURRENT_YEAR}{m:02d}" for m in range(start_m, start_m + 3)]

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

# --- 🎨 STYLES (MATCHING IMAGES) ---
st.markdown("""
    <style>
    .stApp { background-color: #FFFFFF; color: #000000; }
    h3 { color: #333333 !important; font-family: 'Arial', sans-serif; font-weight: bold; margin-bottom: 20px; }
    .stButton>button { background-color: #0056b3; color: white; border-radius: 4px; font-weight: bold; }
    /* Headers Bold */
    [data-testid="stHeader"] { font-weight: bold; }
    .dataframe { font-size: 14px !important; }
    </style>
    """, unsafe_allow_html=True)


# --- 🛡️ KEEP ALIVE ---
def keep_alive_worker():
    while True:
        try:
            time.sleep(300)
            print(f"💓 Heartbeat: {datetime.now()}")
        except Exception:
            pass


if 'keep_alive_started' not in st.session_state:
    t = threading.Thread(target=keep_alive_worker, daemon=True)
    t.start()
    st.session_state['keep_alive_started'] = True


# ==========================================
# 🧮 2. CORE HELPERS
# ==========================================
def get_quarter_str(date_obj):
    if pd.isna(date_obj): return "Unknown"
    q = (date_obj.month - 1) // 3 + 1
    return f"{date_obj.year} Q{q}"


def calculate_commission_tier(total_gp, base_salary, is_tl=False):
    t1, t2, t3 = (4.5, 6.75, 11.25) if is_tl else (9.0, 13.5, 22.5)
    if total_gp < t1 * base_salary:
        return 0, 0
    elif total_gp < t2 * base_salary:
        return 1, 1
    elif total_gp < t3 * base_salary:
        return 2, 2
    else:
        return 3, 3


def calculate_single_deal_commission(sal, mult):
    if mult == 0: return 0
    if sal < 20000:
        base = 1000
    elif sal < 30000:
        base = sal * 0.05
    elif sal < 50000:
        base = sal * 1.5 * 0.05
    else:
        base = sal * 2.0 * 0.05
    return base * mult


def get_commission_pay_date(pmt_date):
    if pd.isna(pmt_date) or not pmt_date: return None
    try:
        y, m = pmt_date.year + (pmt_date.month // 12), (pmt_date.month % 12) + 1
        return datetime(y, m, 15)
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
        creds = ServiceAccountCredentials.from_json_keyfile_dict(dict(st.secrets["gcp_service_account"]), scope)
        return gspread.authorize(creds)
    return None


# ==========================================
# 📥 3. DATA FETCHING
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
                stg = str(c_data.get('s', 'Sent')).lower()
                is_off = "offer" in stg
                is_int = ("interview" in stg) or ("面试" in stg) or is_off
                if is_off: co += 1
                if is_int: ci += 1
                cs += 1
                stat = "Offered" if is_off else ("Interviewed" if is_int else "Sent")
                res.append(
                    {"Consultant": conf['name'], "Month": tab, "Year": tab[:4], "Company": b['c'], "Position": b['p'],
                     "Status": stat, "Count": 1})
            return res

        for r in rows:
            if not r: continue
            fc = r[0].strip()
            if fc in COMPANY_KEYS:
                details.extend(flush(block));
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
                on_date = None
                for fmt in date_formats:
                    try:
                        on_date = datetime.strptime(row[col_onboard].strip(), fmt); break
                    except:
                        pass
                if not on_date: continue
                matched = "Unknown"
                c_norm = normalize_text(c_name_raw)
                for conf in TEAM_CONFIG:
                    conf_norm = normalize_text(conf['name'])
                    if conf_norm in c_norm or c_norm in conf_norm or conf_norm.split()[0] in c_norm: matched = conf[
                        'name']; break
                if matched == "Unknown": continue
                try:
                    sal = float(str(row[col_sal]).replace(',', '').replace('$', '').strip())
                except:
                    sal = 0
                pct = 1.0
                if col_pct != -1 and len(row) > col_pct:
                    try:
                        p_float = float(str(row[col_pct]).replace('%', '').strip())
                        pct = p_float / 100.0 if p_float > 1.0 else p_float
                    except:
                        pct = 1.0
                gp = sal * (1.0 if sal < 20000 else 1.5) * pct
                pay_obj, status = None, "Pending"
                if col_pay != -1 and len(row) > col_pay:
                    pay_str = row[col_pay].strip()
                    if len(pay_str) > 5:
                        status = "Paid"
                        for fmt in date_formats:
                            try:
                                pay_obj = datetime.strptime(pay_str, fmt); break
                            except:
                                pass
                sales_records.append({
                    "Consultant": matched, "GP": gp, "Candidate Salary": sal, "Percentage": pct,
                    "Onboard Date": on_date, "Year": str(on_date.year), "Status": status, "Payment Date Obj": pay_obj,
                    "Quarter": get_quarter_str(on_date)
                })
        return pd.DataFrame(sales_records)
    except:
        return pd.DataFrame()


# ==========================================
# 📊 4. UI RENDER FUNCTIONS (MATCHING IMAGES)
# ==========================================

def render_rec_table_styled(df, title, roles_map):
    st.markdown(f"### 🎯 {title}")
    if df.empty: st.info("No data available."); return

    # Process grouping
    summary = df.groupby('Consultant')[['Sent', 'Int', 'Off']].sum().reset_index()
    summary['Role'] = summary['Consultant'].map(roles_map)
    summary['Target (Q)'] = CV_TARGET_QUARTERLY
    summary['Activity %'] = (summary['Sent'] / summary['Target (Q)'] * 100).clip(0, 500)
    summary['Int/Sent'] = (summary['Int'] / summary['Sent'] * 100).fillna(0)

    # Calculate Total Row
    total_row = pd.DataFrame([{
        'Consultant': 'TOTAL',
        'Role': '-',
        'Target (Q)': summary['Target (Q)'].sum(),
        'Sent': summary['Sent'].sum(),
        'Activity %': (summary['Sent'].sum() / summary['Target (Q)'].sum() * 100),
        'Int': summary['Int'].sum(),
        'Off': summary['Off'].sum(),
        'Int/Sent': (summary['Int'].sum() / summary['Sent'].sum() * 100 if summary['Sent'].sum() > 0 else 0)
    }])

    final_df = pd.concat([summary, total_row], ignore_index=True)

    # Column selection & order as per image
    cols = ['Consultant', 'Role', 'Target (Q)', 'Sent', 'Activity %', 'Int', 'Off', 'Int/Sent']

    st.dataframe(
        final_df[cols],
        use_container_width=True,
        hide_index=True,
        column_config={
            "Target (Q)": st.column_config.NumberColumn("Target (Q)", format="%d"),
            "Sent": st.column_config.NumberColumn("Sent", format="%d"),
            "Activity %": st.column_config.ProgressColumn("Activity %", format="%.0f%%", min_value=0, max_value=100),
            "Int": st.column_config.NumberColumn("Int", format="%d"),
            "Off": st.column_config.NumberColumn("Off", format="%d"),
            "Int/Sent": st.column_config.NumberColumn("Int/Sent", format="%.2f%%")
        }
    )


def render_fin_table_styled(sales_df, rec_stats_df, quarter_str, team_data):
    st.markdown(f"### 💰 Financial Performance ({quarter_str})")

    summary_list = []
    q_sales = sales_df[sales_df['Quarter'] == quarter_str].copy() if not sales_df.empty else pd.DataFrame()
    q_rec = rec_stats_df[rec_stats_df['Quarter'] == quarter_str] if not rec_stats_df.empty else pd.DataFrame()

    for conf in team_data:
        c_name, base, role = conf['name'], conf['base_salary'], conf.get('role', 'Consultant')
        is_tl, is_int = (role == "Team Lead"), (role == "Intern")
        target_gp = 0 if is_int else base * (4.5 if is_tl else 9.0)

        c_sales = q_sales[q_sales['Consultant'] == c_name].copy() if not q_sales.empty else pd.DataFrame()
        sent_count = q_rec[q_rec['Consultant'] == c_name]['Sent'].sum() if not q_rec.empty else 0

        booked_gp = c_sales['GP'].sum()
        paid_gp, total_comm, level = 0, 0, 0

        fin_pct = (booked_gp / target_gp * 100) if target_gp > 0 else 0
        rec_pct = (sent_count / CV_TARGET_QUARTERLY * 100)
        is_target_met = (fin_pct >= 100 or rec_pct >= 100)

        if not is_int and not c_sales.empty:
            paid_sales = c_sales[c_sales['Status'] == 'Paid'].copy()
            if not paid_sales.empty:
                paid_sales['Payment Date Obj'] = pd.to_datetime(paid_sales['Payment Date Obj'])
                paid_sales = paid_sales.sort_values(by='Payment Date Obj')
                paid_sales['MonthKey'] = paid_sales['Payment Date Obj'].dt.to_period('M')
                running_gp = 0
                for m_key in sorted(paid_sales['MonthKey'].unique()):
                    m_deals = paid_sales[paid_sales['MonthKey'] == m_key]
                    running_gp += m_deals['GP'].sum()
                    lvl, mult = calculate_commission_tier(running_gp, base, is_tl)
                    level = lvl
                    if is_target_met:
                        for _, row in m_deals.iterrows():
                            total_comm += calculate_single_deal_commission(row['Candidate Salary'], mult) * row[
                                'Percentage']
                paid_gp = running_gp

        # TL Bonus
        if is_tl and is_target_met and not q_sales.empty:
            others_paid = q_sales[(q_sales['Status'] == 'Paid') & (q_sales['Consultant'] != c_name) & (
                        q_sales['Consultant'] != "Estela Peng")]
            total_comm += len(others_paid) * 1000

        status = "Financial" if fin_pct >= 100 else ("Activity" if rec_pct >= 100 else "In Progress")

        summary_list.append({
            "Consultant": c_name, "Role": role, "GP Target": target_gp, "Paid GP": paid_gp,
            "Financial % (Booked)": fin_pct, "Status": status, "Level": level, "Payable Comm.": total_comm
        })

    final_df = pd.DataFrame(summary_list).sort_values('Financial % (Booked)', ascending=False)

    st.dataframe(
        final_df,
        use_container_width=True,
        hide_index=True,
        column_config={
            "GP Target": st.column_config.NumberColumn("GP Target", format="$%d"),
            "Paid GP": st.column_config.NumberColumn("Paid GP", format="$%d"),
            "Financial % (Booked)": st.column_config.ProgressColumn("Financial % (Booked)", format="%.0f%%",
                                                                    min_value=0, max_value=100),
            "Payable Comm.": st.column_config.NumberColumn("Payable Comm.", format="$%d")
        }
    )


# ==========================================
# 🔧 顶部自动日期配置 (确保实时性)
# ==========================================
from datetime import datetime
now = datetime.now()
CURRENT_YEAR = now.year
CURRENT_QUARTER = (now.month - 1) // 3 + 1
CURRENT_Q_STR = f"{CURRENT_YEAR} Q{CURRENT_QUARTER}"

# --- 🚀 主程序 ---
def main():
    st.title("💼 Management Dashboard")

    client = connect_to_google()
    if not client: st.error("❌ API Error"); return

    # 自动获取当前季度的月份列表 (例如 202601, 202602, 202603)
    start_m = (CURRENT_QUARTER - 1) * 3 + 1
    end_m = start_m + 2
    quarter_months_str = [f"{CURRENT_YEAR}{m:02d}" for m in range(start_m, end_m + 1)]

    col1, col2 = st.columns([1, 5])
    with col1:
        if st.button("🔄 REFRESH DATA", type="primary"):
            with st.spinner("⏳ Fetching live data & roles..."):
                try:
                    data_package = load_data_from_api(client, quarter_months_str)
                    st.session_state['data_cache'] = data_package
                    st.success(f"Updated: {data_package['last_updated']}")
                    time.sleep(0.5)
                    st.rerun()
                except Exception as e:
                    st.error(str(e))

    if 'data_cache' not in st.session_state:
        st.info(f"👋 Welcome! Click 'REFRESH DATA' to load the {CURRENT_Q_STR} report.")
        st.stop()

    cache = st.session_state['data_cache']
    dynamic_team_config = cache['team_data']
    rec_stats_df, rec_details_df, rec_hist_df, all_sales_df = cache['rec_stats'], cache['rec_details'], cache[
        'rec_hist'], cache['sales_all']
    st.caption(f"📅 Snapshot: {cache['last_updated']}")

    # 数据隔离逻辑
    if not all_sales_df.empty:
        # 当前季度掩码
        current_q_mask = (all_sales_df['Quarter'] == CURRENT_Q_STR)
        sales_df_curr = all_sales_df[current_q_mask].copy()
        sales_df_hist = all_sales_df[~current_q_mask].copy()
        
        # 为了兼容你原有的 Dashboard 变量名，我们将 sales_df_q4 指向当前季度数据
        sales_df_q4 = sales_df_curr 
    else:
        sales_df_q4, sales_df_hist = pd.DataFrame(), pd.DataFrame()

    tab_dash, tab_details = st.tabs(["📊 DASHBOARD", "📝 DETAILS"])

    # ==========================================================
    # 第一页：DASHBOARD (完全保留你的原始逻辑)
    # ==========================================================
    with tab_dash:
        # 1. Recruitment Stats
        st.markdown(f"### 🎯 Recruitment Stats ({CURRENT_Q_STR})")
        if not rec_stats_df.empty:
            rec_summary = rec_stats_df.groupby('Consultant')[['Sent', 'Int', 'Off']].sum().reset_index()

            def get_role_target(c_name):
                for member in dynamic_team_config:
                    if member['name'] == c_name:
                        return member.get('role', 'Consultant'), CV_TARGET_QUARTERLY
                return 'Consultant', CV_TARGET_QUARTERLY

            rec_summary[['Role', 'CV Target']] = rec_summary['Consultant'].apply(
                lambda x: pd.Series(get_role_target(x))
            )

            rec_summary['Activity %'] = (rec_summary['Sent'] / rec_summary['CV Target']).fillna(0) * 100
            rec_summary['Int Rate'] = (rec_summary['Int'] / rec_summary['Sent']).fillna(0) * 100

            total_sent = rec_summary['Sent'].sum()
            total_int = rec_summary['Int'].sum()
            total_off = rec_summary['Off'].sum()
            total_target = rec_summary['CV Target'].sum()

            total_activity_rate = (total_sent / total_target * 100) if total_target > 0 else 0
            total_int_rate = (total_int / total_sent * 100) if total_sent > 0 else 0

            total_row = pd.DataFrame([{
                'Consultant': 'TOTAL', 'Role': '-', 'CV Target': total_target,
                'Sent': total_sent, 'Activity %': total_activity_rate,
                'Int': total_int, 'Off': total_off, 'Int Rate': total_int_rate
            }])
            rec_summary = pd.concat([rec_summary, total_row], ignore_index=True)

            cols = ['Consultant', 'Role', 'CV Target', 'Sent', 'Activity %', 'Int', 'Off', 'Int Rate']
            st.dataframe(
                rec_summary[cols], use_container_width=True, hide_index=True,
                column_config={
                    "Consultant": st.column_config.TextColumn("Consultant", width=150),
                    "Activity %": st.column_config.ProgressColumn("Activity %", format="%.0f%%", min_value=0, max_value=100, width=150),
                    "Int Rate": st.column_config.NumberColumn("Int/Sent", format="%.2f%%", width=130),
                }
            )
        else:
            st.warning("No data.")

        with st.expander("📜 Historical Recruitment Data"):
            if not rec_hist_df.empty:
                st.dataframe(
                    rec_hist_df.groupby('Consultant')[['Sent', 'Int', 'Off']].sum().reset_index().sort_values('Sent', ascending=False),
                    use_container_width=True, hide_index=True)
            else:
                st.info("No data.")
        st.divider()

        # 2. Financial Performance (Dashboard Summary)
        st.markdown(f"### 💰 Financial Performance ({CURRENT_Q_STR})")
        financial_summary = []
        
        # 预计算所有顾问的当前季度数据
        for conf in dynamic_team_config:
            c_name = conf['name']; base = conf['base_salary']; role = conf.get('role', 'Consultant')
            is_intern = (role == "Intern"); is_team_lead = (role == "Team Lead")
            gp_target = 0 if is_intern else base * (4.5 if is_team_lead else 9.0)
            
            c_sales_curr = sales_df_q4[sales_df_q4['Consultant'] == c_name].copy() if not sales_df_q4.empty else pd.DataFrame()
            sent_count = rec_stats_df[rec_stats_df['Consultant'] == c_name]['Sent'].sum() if not rec_stats_df.empty else 0
            booked_gp = c_sales_curr['GP'].sum() if not c_sales_curr.empty else 0
            
            fin_pct = (booked_gp / gp_target * 100) if gp_target > 0 else 0
            rec_pct = (sent_count / CV_TARGET_QUARTERLY * 100) if CV_TARGET_QUARTERLY > 0 else 0

            achieved = []
            is_target_met = False
            if is_intern:
                if rec_pct >= 100: achieved.append("Activity"); is_target_met = True
            else:
                if fin_pct >= 100: achieved.append("Financial"); is_target_met = True
                if rec_pct >= 100: achieved.append("Activity"); is_target_met = True
            
            # 佣金计算 (仅用于 Dash 展示总额)
            total_comm_dash = 0
            if not is_intern and not c_sales_curr.empty:
                # 简化逻辑用于 Dashboard 展示，详细逻辑在 Details 页展示
                paid_sales = c_sales_curr[c_sales_curr['Status'] == 'Paid'].copy()
                if not paid_sales.empty and is_target_met:
                    running_gp = 0
                    paid_sales['Payment Date Obj'] = pd.to_datetime(paid_sales['Payment Date Obj'])
                    paid_sales = paid_sales.sort_values('Payment Date Obj')
                    for _, row in paid_sales.iterrows():
                        running_gp += row['GP']
                        lvl, mult = calculate_commission_tier(running_gp, base, is_team_lead)
                        total_comm_dash += calculate_single_deal_commission(row['Candidate Salary'], mult) * row['Percentage']

            financial_summary.append({
                "Consultant": c_name, "Role": role, "GP Target": gp_target, "Paid GP": booked_gp, "Fin %": fin_pct,
                "Status": " & ".join(achieved) if achieved else "In Progress", "Est. Commission": total_comm_dash
            })

        st.dataframe(
            pd.DataFrame(financial_summary).sort_values('Paid GP', ascending=False),
            use_container_width=True, hide_index=True,
            column_config={
                "Fin %": st.column_config.ProgressColumn("Financial % (Booked)", format="%.0f%%", min_value=0, max_value=100, width=150),
                "GP Target": st.column_config.NumberColumn(format="$%d"),
                "Paid GP": st.column_config.NumberColumn(format="$%d"),
                "Est. Commission": st.column_config.NumberColumn(format="$%d"),
            }
        )

        with st.expander("📜 Historical GP Summary"):
            if not sales_df_hist.empty:
                q_totals = sales_df_hist.groupby('Quarter')['GP'].sum().reset_index()
                q_totals['Consultant'] = '📌 TOTAL'
                d_rows = sales_df_hist.groupby(['Quarter', 'Consultant'])['GP'].sum().reset_index()
                st.dataframe(
                    pd.concat([q_totals, d_rows]).sort_values(['Quarter', 'Consultant'], ascending=[False, True]),
                    use_container_width=True, hide_index=True,
                    column_config={"GP": st.column_config.NumberColumn("Total GP", format="$%d")})

    # ==========================================================
    # 第二页：DETAILS (按时间倒序展示多季度明细)
    # ==========================================================
    with tab_details:
        st.markdown("### 🔍 Drill Down Details")
        
        # 获取所有存在的季度并从新到旧排序
        available_quarters = sorted(all_sales_df['Quarter'].unique(), reverse=True) if not all_sales_df.empty else []

        for conf in dynamic_team_config:
            c_name = conf['name']; base = conf['base_salary']; role = conf.get('role', 'Consultant')
            # 找到该顾问在 Dash 里的状态
            try:
                c_status = next(item['Status'] for item in financial_summary if item['Consultant'] == c_name)
            except:
                c_status = "In Progress"
                
            with st.expander(f"👤 {c_name} ({role}) | Overall Status: {c_status}"):
                
                for q_label in available_quarters:
                    # 仅处理该顾问在该季度的数据
                    q_sales = all_sales_df[(all_sales_df['Consultant'] == c_name) & (all_sales_df['Quarter'] == q_label)].copy()
                    if q_sales.empty: continue
                    
                    st.markdown(f"#### 📅 {q_label} Breakdown")
                    
                    if role != "Intern":
                        # 计算该季度提成逻辑
                        is_tl = (role == "Team Lead")
                        # 检查该顾问在该季度的达标情况 (需要从历史招聘数据匹配)
                        # 注意：此处简化为只要在该季度有 GP 产出即尝试计算佣金等级
                        q_sales['Payment Date Obj'] = pd.to_datetime(q_sales['Payment Date Obj'])
                        q_sales = q_sales.sort_values('Payment Date Obj')
                        
                        running_gp = 0
                        q_sales['Applied Level'] = 0
                        q_sales['Comm ($)'] = 0.0
                        q_sales['Comm. Date'] = ""

                        for idx, row in q_sales.iterrows():
                            if row['Status'] == 'Paid':
                                running_gp += row['GP']
                                lvl, mult = calculate_commission_tier(running_gp, base, is_tl)
                                q_sales.at[idx, 'Applied Level'] = lvl
                                comm_val = calculate_single_deal_commission(row['Candidate Salary'], mult) * row['Percentage']
                                q_sales.at[idx, 'Comm ($)'] = comm_val
                                # 计算佣金发放日 (回款次月15日)
                                if pd.notnull(row['Payment Date Obj']):
                                    p_date = row['Payment Date Obj']
                                    comm_date = datetime(p_date.year + (p_date.month // 12), (p_date.month % 12) + 1, 15)
                                    q_sales.at[idx, 'Comm. Date'] = comm_date.strftime("%Y-%m-%d")
                        
                        # 显示提成表
                        q_sales['Pct Display'] = q_sales['Percentage'].apply(lambda x: f"{int(x*100)}%")
                        display_cols = ['Onboard Date Str', 'Payment Date', 'Comm. Date', 'Candidate Salary', 'Pct Display', 'GP', 'Status', 'Applied Level', 'Comm ($)']
                        
                        st.dataframe(
                            q_sales[display_cols],
                            use_container_width=True, hide_index=True,
                            column_config={
                                "Comm ($)": st.column_config.NumberColumn(format="$%.2f"),
                                "GP": st.column_config.NumberColumn(format="$%d"),
                                "Candidate Salary": st.column_config.NumberColumn(format="$%d"),
                            }
                        )

                        # 如果是 Team Lead，显示 Overrides
                        if is_tl:
                            st.markdown("##### 👥 Team Overrides")
                            # 查找该季度其他人的 Paid 单子
                            tl_over_df = all_sales_df[(all_sales_df['Quarter'] == q_label) & 
                                                      (all_sales_df['Status'] == 'Paid') & 
                                                      (all_sales_df['Consultant'] != c_name) & 
                                                      (all_sales_df['Consultant'] != "Estela Peng")].copy()
                            if not tl_over_df.empty:
                                tl_over_df['Bonus'] = 1000
                                tl_over_df['Date'] = tl_over_df['Payment Date Obj'].apply(
                                    lambda x: (datetime(x.year + (x.month // 12), (x.month % 12) + 1, 15)).strftime("%Y-%m-%d") if pd.notnull(x) else ""
                                )
                                st.dataframe(
                                    tl_over_df[['Consultant', 'Onboard Date Str', 'GP', 'Date', 'Bonus']].rename(columns={'Consultant': 'Source'}),
                                    use_container_width=True, hide_index=True,
                                    column_config={"Bonus": st.column_config.NumberColumn(format="$%d")}
                                )
                            else:
                                st.caption("No team overrides for this quarter.")
                    
                    st.divider()

                # 日志部分放在最后
                st.markdown("#### 📝 Recruitment Logs")
                c_logs = rec_details_df[rec_details_df['Consultant'] == c_name]
                if not c_logs.empty:
                    st.dataframe(c_logs.groupby(['Month', 'Company', 'Position', 'Status'])['Count'].sum().reset_index().sort_values('Month', ascending=False),
                                  use_container_width=True, hide_index=True)

if __name__ == "__main__":
    main()
