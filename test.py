import streamlit as st
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from gspread.exceptions import APIError
import pandas as pd
import time
from datetime import datetime
import unicodedata
from concurrent.futures import ThreadPoolExecutor

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
    {"name": "Raul Solis", "id": "1vQuN-iNBRUug5J6gBMX-52jp6oogbA77SaeAf9j_zYs", "keyword": "Name", "base_salary": 11000},
    {"name": "Estela Peng", "id": "1sUkffAXzWnpzhhmklqBuwtoQylpR1U18zqBQ-lsp7Z4", "keyword": "姓名", "base_salary": 20800},
    {"name": "Ana Cruz", "id": "1VMVw5YCV12eI8I-VQSXEKg86J2IVZJEgjPJT7ggAFD0", "keyword": "Name", "base_salary": 13000},
    {"name": "Karina Albarran", "id": "1zc4ghvfjIxH0eJ2aXfopOWHqiyTDlD8yFNjBzpH07D8", "keyword": "Name", "base_salary": 15000},
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
    "Fin %": st.column_config.ProgressColumn("Financial % (Booked)", format="%.0f%%", min_value=0, max_value=100, width=150),
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

def connect_to_google():
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    try:
        if "gcp_service_account" in st.secrets:
            creds = ServiceAccountCredentials.from_json_keyfile_dict(dict(st.secrets["gcp_service_account"]), scope)
            return gspread.authorize(creds)
    except: return None

# --- 🚀 极速抓取逻辑 ---

def fetch_member_data_complete(client, conf, current_months):
    """抓取该顾问的所有数据：角色、当前季度招聘、全历史招聘"""
    stats_list = []
    details_list = []
    role = "Consultant"
    try:
        sheet = client.open_by_key(conf['id'])
        # 1. 抓取角色
        try: role = sheet.worksheet('Credentials').acell('B1').value.strip()
        except: pass
        # 2. 抓取所有工作表名（用于识别历史月份）
        worksheets = sheet.worksheets()
        all_month_tabs = [ws.title.strip() for ws in worksheets if ws.title.strip().isdigit() and len(ws.title.strip()) == 6]
        
        # 3. 抓取招聘数据
        for tab in all_month_tabs:
            rows = sheet.worksheet(tab).get_all_values()
            s, i, o, d = parse_recruitment_rows(rows, conf, tab)
            stats_list.append({"Consultant": conf['name'], "Month": tab, "Sent": s, "Int": i, "Off": o})
            if tab in current_months: details_list.extend(d)
    except: pass
    return role, stats_list, details_list

def parse_recruitment_rows(rows, conf, tab):
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
        elif fc in ["Position", "Role", "职位"]: block['p'] = r[1] if len(r) > 1 else "Unk"
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

def fetch_all_sales_fast(client):
    try:
        sheet = client.open_by_key(SALES_SHEET_ID)
        ws = sheet.worksheet(SALES_TAB_NAME)
        rows = ws.get_all_values()
        col_idx = {}
        header_found = False
        start_row = 0
        for i, row in enumerate(rows):
            row_l = [str(c).lower() for c in row]
            if any("linkeazi" in c and "consultant" in c for c in row_l):
                for j, cell in enumerate(row_l):
                    if "linkeazi" in cell and "consultant" in cell: col_idx['cons'] = j
                    if "onboarding" in cell and "date" in cell: col_idx['onboard'] = j
                    if "candidate" in cell and "salary" in cell: col_idx['sal'] = j
                    if "payment" in cell and "onboard" not in cell: col_idx['pay'] = j
                    if "percentage" in cell or cell == "%": col_idx['pct'] = j
                    if any(x in cell for x in ["company", "client", "客户", "公司"]): col_idx['comp'] = j
                    if any(x in cell for x in ["candidate", "候选人", "上岗"]): col_idx['cand'] = j
                header_found = True; start_row = i + 1; break
        if not header_found: return pd.DataFrame()
        sales_records = []
        date_formats = ["%Y-%m-%d", "%d/%m/%Y", "%Y/%m/%d", "%m/%d/%Y", "%d-%b-%y", "%Y.%m.%d"]
        for row in rows[start_row:]:
            if len(row) <= max(col_idx.values()): continue
            c_name = row[col_idx['cons']].strip()
            if not c_name: continue
            matched = "Unknown"
            c_norm = normalize_text(c_name)
            for conf in TEAM_CONFIG:
                if normalize_text(conf['name']) in c_norm or c_norm in normalize_text(conf['name']): matched = conf['name']; break
            if matched == "Unknown": continue
            onboard_date = None
            for fmt in date_formats:
                try: onboard_date = datetime.strptime(row[col_idx['onboard']].strip(), fmt); break
                except: pass
            if not onboard_date: continue
            try: salary = float(row[col_idx['sal']].replace(',', '').replace('$', '').strip())
            except: salary = 0
            try:
                pv = float(row[col_idx['pct']].replace('%', '').strip())
                pct = pv / 100 if pv > 1 else pv
            except: pct = 1.0
            calc_gp = salary * (1.0 if salary < 20000 else 1.5) * pct
            pay_val = row[col_idx['pay']].strip()
            pay_date_obj, status = None, "Pending"
            if len(pay_val) > 5:
                status = "Paid"
                for fmt in date_formats:
                    try: pay_date_obj = datetime.strptime(pay_val, fmt); break
                    except: pass
            sales_records.append({
                "Consultant": matched, "Company": row[col_idx['comp']], "Cdd Placed": row[col_idx['cand']],
                "GP": calc_gp, "Candidate Salary": salary, "Percentage": pct,
                "Onboard Date": onboard_date, "Onboard Date Str": onboard_date.strftime("%Y-%m-%d"),
                "Payment Date Obj": pay_date_obj, "Status": status, "Quarter": get_quarter_str(onboard_date)
            })
        return pd.DataFrame(sales_records)
    except: return pd.DataFrame()

def load_data_complete_optimized(client):
    """并行抓取所有数据"""
    all_stats, all_details, team_info = [], [], []
    with ThreadPoolExecutor(max_workers=4) as executor:
        futures = [executor.submit(fetch_member_data_complete, client, conf, quarter_months_str) for conf in TEAM_CONFIG]
        for i, f in enumerate(futures):
            role, stats, details = f.result()
            m_info = TEAM_CONFIG[i].copy()
            m_info['role'] = role
            team_info.append(m_info)
            all_stats.extend(stats)
            all_details.extend(details)
    all_sales = fetch_all_sales_fast(client)
    return {"team_data": team_info, "rec_stats": pd.DataFrame(all_stats), "rec_details": pd.DataFrame(all_details), "sales_all": all_sales}

# --- 🚀 主程序 ---

def main():
    st.title("💼 Management Dashboard")
    client = connect_to_google()
    if not client: st.error("❌ API Error"); return

    if st.button("🔄 REFRESH DATA", type="primary"):
        with st.spinner("⏳ Fetching live data in parallel..."):
            st.session_state['data_cache'] = load_data_complete_optimized(client)
            st.rerun()

    if 'data_cache' not in st.session_state:
        st.info("👋 Welcome! Click 'REFRESH DATA' to load report."); st.stop()

    cache = st.session_state['data_cache']
    dynamic_team_config, rec_stats_all, all_sales_df = cache['team_data'], cache['rec_stats'], cache['sales_all']
    rec_details_df = cache['rec_details']

    # --- 核心逻辑预处理 ---
    rec_stats_all['Quarter'] = rec_stats_all['Month'].apply(lambda x: f"{x[:4]} Q{(int(x[4:])-1)//3+1}")
    q_sent_map = rec_stats_all.groupby(['Consultant', 'Quarter'])['Sent'].sum().to_dict()
    
    target_status_lookup = {}
    updated_sales_all_list = []
    all_qs = sorted(all_sales_df['Quarter'].unique()) if not all_sales_df.empty else [CURRENT_Q_STR]

    # 第一遍：定达标
    for q in all_qs:
        q_sales = all_sales_df[all_sales_df['Quarter'] == q] if not all_sales_df.empty else pd.DataFrame()
        for conf in dynamic_team_config:
            name, base, role = conf['name'], conf['base_salary'], conf['role']
            sent = q_sent_map.get((name, q), 0)
            booked_gp = q_sales[q_sales['Consultant'] == name]['GP'].sum() if not q_sales.empty else 0
            gp_target = base * (4.5 if role == "Team Lead" else 9.0) if role != "Intern" else 0
            is_met = (sent >= CV_TARGET_QUARTERLY) if role == "Intern" else (sent >= CV_TARGET_QUARTERLY or (gp_target > 0 and booked_gp >= gp_target))
            target_status_lookup[(name, q)] = is_met

    # 第二遍：算提成
    for q in all_qs:
        q_sales_pool = all_sales_df[all_sales_df['Quarter'] == q].copy() if not all_sales_df.empty else pd.DataFrame()
        for conf in dynamic_team_config:
            name, base, role = conf['name'], conf['base_salary'], conf['role']
            is_met = target_status_lookup.get((name, q), False)
            c_q_sales = q_sales_pool[q_sales_pool['Consultant'] == name].copy() if not q_sales_pool.empty else pd.DataFrame()
            
            if not c_q_sales.empty:
                c_q_sales['Final Comm'] = 0.0
                paid_deals = c_q_sales[c_q_sales['Status'] == 'Paid'].copy()
                if not paid_deals.empty:
                    paid_deals['Payment Date Obj'] = pd.to_datetime(paid_deals['Payment Date Obj'])
                    paid_deals = paid_deals.sort_values('Payment Date Obj')
                    running_gp = 0
                    for idx, row in paid_deals.iterrows():
                        running_gp += row['GP']
                        _, mult = calculate_commission_tier(running_gp, base, role == "Team Lead")
                        if is_met:
                            paid_deals.at[idx, 'Final Comm'] = calculate_single_deal_commission(row['Candidate Salary'], mult) * row['Percentage']
                    c_q_sales.update(paid_deals)

            # Lead Override
            if role == "Team Lead" and is_met and not q_sales_pool.empty:
                others_paid = q_sales_pool[(q_sales_pool['Status'] == 'Paid') & (q_sales_pool['Consultant'] != name) & (q_sales_pool['Consultant'] != "Estela Peng")]
                if not others_paid.empty:
                    c_q_sales = pd.concat([c_q_sales, pd.DataFrame([{"Consultant": name, "Quarter": q, "Company": "TEAM OVERRIDE", "Cdd Placed": f"{others_paid.shape[0]} deals", "GP": 0, "Status": "Paid", "Final Comm": others_paid.shape[0]*1000, "Onboard Date Str": "N/A"}])], ignore_index=True)
            if not c_q_sales.empty: updated_sales_all_list.append(c_q_sales)

    final_sales_all = pd.concat(updated_sales_all_list) if updated_sales_all_list else pd.DataFrame()

    # --- 渲染 ---
    tab_dash, tab_details, tab_logs = st.tabs(["📊 DASHBOARD", "📝 DETAILS", "🕕 LOGS"])

    with tab_dash:
        st.markdown(f"### 🎯 Recruitment Stats ({CURRENT_Q_STR})")
        curr_rec = []
        for conf in dynamic_team_config:
            name = conf['name']
            row = rec_stats_all[(rec_stats_all['Consultant'] == name) & (rec_stats_all['Quarter'] == CURRENT_Q_STR)]
            s, i, o = row['Sent'].sum(), row['Int'].sum(), row['Off'].sum()
            curr_rec.append({"Quarter": CURRENT_Q_STR, "Consultant": name, "Role": conf['role'], "CV Target": CV_TARGET_QUARTERLY, "Sent": s, "Int": i, "Off": o, "Activity %": (s/CV_TARGET_QUARTERLY*100), "Int Rate": (i/s*100) if s>0 else 0})
        st.dataframe(pd.DataFrame(curr_rec), use_container_width=True, hide_index=True, column_config=REC_COL_CONFIG)

        with st.expander("📜 Historical Recruitment Data"):
            hist_rec = []
            u_qs = sorted([q for q in rec_stats_all['Quarter'].unique() if q != CURRENT_Q_STR], reverse=True)
            for q in u_qs:
                for conf in dynamic_team_config:
                    name = conf['name']
                    row = rec_stats_all[(rec_stats_all['Consultant'] == name) & (rec_stats_all['Quarter'] == q)]
                    s, i, o = row['Sent'].sum(), row['Int'].sum(), row['Off'].sum()
                    if s+i+o > 0: hist_rec.append({"Quarter": q, "Consultant": name, "Role": conf['role'], "CV Target": CV_TARGET_QUARTERLY, "Sent": s, "Int": i, "Off": o, "Activity %": (s/CV_TARGET_QUARTERLY*100), "Int Rate": (i/s*100) if s>0 else 0})
            st.dataframe(pd.DataFrame(hist_rec), use_container_width=True, hide_index=True, column_config=REC_COL_CONFIG)

        st.markdown(f"### 💰 Financial Performance ({CURRENT_Q_STR})")
        fin_sum = []
        for conf in dynamic_team_config:
            name, base, role = conf['name'], conf['base_salary'], conf['role']
            is_met = target_status_lookup.get((name, CURRENT_Q_STR), False)
            q_data = final_sales_all[(final_sales_all['Consultant'] == name) & (final_sales_all['Quarter'] == CURRENT_Q_STR)] if not final_sales_all.empty else pd.DataFrame()
            paid_gp = q_data[q_data['Company'] != "TEAM OVERRIDE"]['GP'].sum() if not q_data.empty else 0
            gp_target = base * (4.5 if role == "Team Lead" else 9.0) if role != "Intern" else 0
            fin_sum.append({"Quarter": CURRENT_Q_STR, "Consultant": name, "Role": role, "GP Target": gp_target, "Paid GP": paid_gp, "Fin %": (paid_gp/gp_target*100) if gp_target > 0 else 0, "Status": "Target Met" if is_met else "In Progress", "Level": calculate_commission_tier(paid_gp, base, role=="Team Lead")[0], "Est. Commission": q_data['Final Comm'].sum() if not q_data.empty else 0})
        st.dataframe(pd.DataFrame(fin_sum).sort_values('Paid GP', ascending=False), use_container_width=True, hide_index=True, column_config=FIN_COL_CONFIG)

    with tab_details:
        st.markdown("### 🔍 Historical Drill Down")
        for conf in dynamic_team_config:
            name = conf['name']
            c_deals = final_sales_all[final_sales_all['Consultant'] == name] if not final_sales_all.empty else pd.DataFrame()
            with st.expander(f"👤 {name} - Full History"):
                if not c_deals.empty:
                    st.dataframe(c_deals[['Quarter', 'Onboard Date Str', 'Company', 'Cdd Placed', 'Status', 'GP', 'Final Comm']].sort_values(['Quarter', 'Onboard Date Str'], ascending=False), use_container_width=True, hide_index=True, column_config={"GP": st.column_config.NumberColumn("GP", format="$%d"), "Final Comm": st.column_config.NumberColumn("Comm ($)", format="$%.2f")})
                else: st.info("No records.")

    with tab_logs:
        st.markdown("🕕 ACTIVITY LOGS")
        if not rec_details_df.empty:
            st.dataframe(rec_details_df.sort_values('Month', ascending=False), use_container_width=True, hide_index=True)

if __name__ == "__main__":
    main()
