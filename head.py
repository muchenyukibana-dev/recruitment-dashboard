import streamlit as st
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import pandas as pd
import os
import time
from datetime import datetime, timedelta
import unicodedata

# ==========================================
# 🔧 TEAM CONFIGURATION
# ==========================================
SALES_SHEET_ID = '1jniQ-GpeMINjQMebniJ_J1eLVLQIR1NGbSjTtOFP9Q8'
SALES_TAB_NAME = 'Positions'

TEAM_CONFIG = [
    {
        "name": "Raul Solis",
        "id": "1vQuN-iNBRUug5J6gBMX-52jp6oogbA77SaeAf9j_zYs",
        "keyword": "Name",
        "base_salary": 11000,
        "is_team_lead": True  # 👑 Team Lead Logic
    },
    {
        "name": "Estela Peng",
        "id": "1sUkffAXzWnpzhhmklqBuwtoQylpR1U18zqBQ-lsp7Z4",
        "keyword": "姓名",
        "base_salary": 20800
    },
    {
        "name": "Ana Cruz",
        "id": "1VMVw5YCV12eI8I-VQSXEKg86J2IVZJEgjPJT7ggAFD0",
        "keyword": "Name",
        "base_salary": 13000
    },
    {
        "name": "Karina Albarran",
        "id": "1zc4ghvfjIxH0eJ2aXfopOWHqiyTDlD8yFNjBzpH07D8",
        "keyword": "Name",
        "base_salary": 15000
    },
]

# 🎯 Recruitment Goals
MONTHLY_GOAL = 114
QUARTERLY_GOAL = 342
# ==========================================

st.set_page_config(page_title="Fill The Pit", page_icon="🐱", layout="wide")

# --- 🎨 CSS STYLING ---
st.markdown("""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Press+Start+2P&display=swap');

    /* Global */
    html, body, [class*="css"] {
        font-family: 'Press Start 2P', monospace;
        background-color: #FFA500;
        color: #FFFFFF;
    }

    /* Title */
    h1 {
        text-shadow: 4px 4px #000000;
        color: #FFD700 !important;
        text-align: center;
        font-size: 3em !important;
        margin-bottom: 20px;
    }

    /* CENTERED BUTTON */
    .stButton {
        display: flex;
        justify-content: center;
        width: 100%;
        margin-left: 180px; 
    }
    .stButton>button {
        background-color: #FF0055;
        color: white;
        border: 4px solid #FFFFFF;
        font-family: 'Press Start 2P', monospace;
        font-size: 28px !important; 
        padding: 25px 50px !important; 
        box-shadow: 8px 8px 0px #000000;
        transition: transform 0.1s;
        width: 100%;
    }
    .stButton>button:hover {
        background-color: #FF5599;
        transform: scale(1.02);
        color: yellow;
        border-color: yellow;
    }

    /* THE PITS (Recruitment Bars) */
    .pit-container {
        background-color: #222;
        border: 4px solid #fff;
        height: 60px;
        width: 100%;
        position: relative;
        margin-top: 10px;
        margin-bottom: 30px;
        box-shadow: 6px 6px 0px #000000;
    }

    .pit-fill-month { background-color: #8B4513; height: 100%; display: flex; align-items: center; justify-content: flex-end; }
    .pit-fill-season { background-color: #0000FF; height: 100%; display: flex; align-items: center; justify-content: flex-end; }
    
    /* FINANCIAL BAR STYLE */
    .money-fill {
        background-color: #28a745; 
        height: 100%;
        display: flex;
        align-items: center; 
        justify-content: flex-end;
    }

    .cat-squad {
        position: absolute;
        right: -30px; 
        top: -25px;
        font-size: 30px;
        z-index: 10;
        white-space: nowrap;
    }

    /* Stats Cards */
    .stat-card {
        background-color: #FFA500;
        border: 4px solid #FFFFFF;
        box-shadow: 6px 6px 0px #000000;
        padding: 15px;
        text-align: center;
        margin-bottom: 15px;
    }
    .stat-val { color: #000000; font-size: 1.5em; margin-top: 10px; }
    .stat-name { color: #FFF; font-size: 1.2em; font-weight: bold; text-transform: uppercase; line-height: 1.5; }

    /* MVP Card */
    .mvp-card {
        background-color: #333; 
        padding: 15px; 
        border: 4px solid #FFD700;
        box-shadow: 8px 8px 0px rgba(255, 15, 0, 0.3);
        text-align: center;
        margin-top: 20px;
    }

    /* Commission Box */
    .comm-box {
        background-color: #222;
        border: 2px dashed #FFD700;
        padding: 10px;
        text-align: center;
        margin-top: -20px;
        margin-bottom: 20px;
        box-shadow: 4px 4px 0px #000;
        color: #FFD700;
        font-size: 0.9em;
    }
    
    .header-bordered {
        border: 4px solid #FFFFFF;
        box-shadow: 6px 6px 0px #000000;
        padding: 15px;
        text-align: center;
        margin-bottom: 20px;
        background-color: #222;
        color: #FFD700;
        font-size: 1.5em;
    }
    .dataframe { font-family: 'Press Start 2P', monospace !important; font-size: 0.8em !important; color: white !important; }
    </style>
    """, unsafe_allow_html=True)


# ==========================================
# 🧮 佣金计算核心逻辑库
# ==========================================

def get_payout_date_from_month_key(month_key):
    """辅助：根据 '2025-11' 计算发薪日 '2025-12-15'"""
    try:
        dt = datetime.strptime(str(month_key), "%Y-%m")
        year = dt.year + (dt.month // 12)
        month = (dt.month % 12) + 1
        return datetime(year, month, 15)
    except:
        return None

def calculate_commission_tier(total_gp, base_salary, is_team_lead=False):
    """辅助：判定 Level"""
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
    """辅助：计算单笔基础佣金"""
    if multiplier == 0: return 0
    base_comm = 0
    if candidate_salary < 20000:
        base_comm = 1000
    elif candidate_salary < 30000:
        base_comm = candidate_salary * 0.05
    elif candidate_salary < 50000:
        base_comm = candidate_salary * 1.5 * 0.05
    else:
        base_comm = candidate_salary * 2.0 * 0.05
    return base_comm * multiplier

def calculate_consultant_performance(all_sales_df, consultant_name, base_salary, is_team_lead=False):
    """
    🚀 核心函数：计算单个顾问的业绩、Level、佣金发放日及总额
    """
    
    # 1. 初始化
    target = base_salary * (4.5 if is_team_lead else 9.0)
    
    # 筛选该顾问的单子
    c_sales = all_sales_df[all_sales_df['Consultant'] == consultant_name].copy()
    
    if c_sales.empty:
        return {
            "Booked GP": 0, "Paid GP": 0, "Level": 0, 
            "Est. Commission": 0, "Target Achieved": 0
        }

    # 初始化新列
    c_sales['Applied Level'] = 0
    c_sales['Final Comm'] = 0.0
    c_sales['Commission Day Obj'] = pd.NaT

    booked_gp = c_sales['GP'].sum()
    paid_gp = 0
    total_comm = 0
    current_level = 0
    
    # ====================================================
    # 核心算法: 阈值触发回溯累积 (Threshold Triggered Catch-up)
    # ====================================================
    
    # 提取已付款的单子进行计算
    paid_sales = c_sales[c_sales['Status'] == 'Paid'].copy()

    if not paid_sales.empty:
        if 'Payment Date Obj' not in paid_sales.columns:
             paid_sales['Payment Date Obj'] = pd.to_datetime(paid_sales['Payment Date'], errors='coerce')
             
        paid_sales = paid_sales.dropna(subset=['Payment Date Obj']).sort_values(by='Payment Date Obj')
        paid_sales['Pay_Month_Key'] = paid_sales['Payment Date Obj'].dt.to_period('M')
        unique_months = sorted(paid_sales['Pay_Month_Key'].unique())

        running_paid_gp = 0
        pending_indices = []

        for month_key in unique_months:
            month_deals = paid_sales[paid_sales['Pay_Month_Key'] == month_key]
            month_new_gp = month_deals['GP'].sum()
            running_paid_gp += month_new_gp
            pending_indices.extend(month_deals.index.tolist())
            
            level, multiplier = calculate_commission_tier(running_paid_gp, base_salary, is_team_lead)
            
            if level > 0:
                payout_date = get_payout_date_from_month_key(str(month_key))
                for idx in pending_indices:
                    row = paid_sales.loc[idx]
                    deal_comm = calculate_single_deal_commission(row['Candidate Salary'], multiplier) * row['Percentage']
                    paid_sales.at[idx, 'Final Comm'] = deal_comm
                    paid_sales.at[idx, 'Commission Day Obj'] = payout_date
                pending_indices = []
            
        paid_gp = running_paid_gp
        current_level, _ = calculate_commission_tier(running_paid_gp, base_salary, is_team_lead)

        limit_date = datetime.now() + timedelta(days=20)
        
        for idx, row in paid_sales.iterrows():
            comm_date = row['Commission Day Obj']
            if pd.notnull(comm_date) and comm_date <= limit_date:
                total_comm += row['Final Comm']

    # ====================================================
    # Team Lead Override 计算
    # ====================================================
    if is_team_lead and not all_sales_df.empty:
        mask = (all_sales_df['Status'] == 'Paid') & \
               (all_sales_df['Consultant'] != consultant_name) & \
               (all_sales_df['Consultant'] != "Estela Peng")
        
        pot_overrides = all_sales_df[mask].copy()
        
        if 'Payment Date Obj' not in pot_overrides.columns:
            pot_overrides['Payment Date Obj'] = pd.to_datetime(pot_overrides['Payment Date'], errors='coerce')

        for _, row in pot_overrides.iterrows():
            pay_date = row['Payment Date Obj']
            if pd.isna(pay_date): continue
            
            comm_pay_obj = datetime(
                pay_date.year + (pay_date.month // 12), 
                (pay_date.month % 12) + 1, 
                15
            )
            
            if comm_pay_obj <= (datetime.now() + timedelta(days=20)):
                total_comm += 1000

    # 返回汇总
    summary = {
        "Consultant": consultant_name,
        "Booked GP": booked_gp,
        "Paid GP": paid_gp,
        "Level": current_level,
        "Target Achieved": (paid_gp / target * 100) if target > 0 else 0,
        "Est. Commission": total_comm
    }
    return summary


# --- GOOGLE CONNECTION & HELPERS ---
def get_quarter_info():
    today = datetime.now()
    year = today.year
    month = today.month
    quarter = (month - 1) // 3 + 1
    start_month = (quarter - 1) * 3 + 1
    end_month = start_month + 2
    tabs = [f"{year}{m:02d}" for m in range(start_month, start_month + 3)]
    return tabs, quarter, start_month, end_month, year

def normalize_text(text):
    return ''.join(c for c in unicodedata.normalize('NFD', str(text)) if unicodedata.category(c) != 'Mn').lower()

def connect_to_google():
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    if "gcp_service_account" in st.secrets:
        try:
            creds_dict = dict(st.secrets["gcp_service_account"])
            creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
            return gspread.authorize(creds)
        except Exception: return None
    else:
        return None # Local handling omitted for brevity

# --- FETCH RECRUITMENT DATA ---
def fetch_consultant_data(client, consultant_config, target_tab):
    sheet_id = consultant_config['id']
    target_key = consultant_config.get('keyword', 'Name')
    COMPANY_KEYS = ["Company", "Client", "Cliente", "公司", "客户"]
    POSITION_KEYS = ["Position", "Role", "Posición", "职位", "岗位"]
    try:
        sheet = client.open_by_key(sheet_id)
        try: worksheet = sheet.worksheet(target_tab)
        except: return 0, []
        rows = worksheet.get_all_values()
        count = 0; details = []
        current_company = "Unknown"; current_position = "Unknown"
        for row in rows:
            if not row: continue
            first_cell = row[0].strip()
            if first_cell in COMPANY_KEYS: current_company = row[1].strip() if len(row) > 1 else "Unknown"
            elif first_cell in POSITION_KEYS: current_position = row[1].strip() if len(row) > 1 else "Unknown"
            elif first_cell == target_key:
                candidates = [x for x in row[1:] if x.strip()]
                count += len(candidates)
                for _ in range(len(candidates)):
                    details.append({"Consultant": consultant_config['name'], "Company": current_company, "Position": current_position, "Count": 1})
        return count, details
    except: return 0, []

# --- FETCH FINANCIAL DATA (DATAFRAME VERSION) ---
def fetch_financial_df(client, start_m, end_m, year):
    """返回 DataFrame 以便进行精细化计算"""
    try:
        sheet = client.open_by_key(SALES_SHEET_ID)
        try: ws = sheet.worksheet(SALES_TAB_NAME)
        except: ws = sheet.get_worksheet(0)
        rows = ws.get_all_values()
        
        col_cons = -1; col_onboard = -1; col_pay = -1; col_sal = -1; col_pct = -1
        found_header = False
        records = []

        for row in rows:
            if not any(cell.strip() for cell in row): continue
            row_lower = [str(x).strip().lower() for x in row]

            if not found_header:
                if any("linkeazi" in c for c in row_lower) and any("onboarding" in c for c in row_lower):
                    for idx, cell in enumerate(row_lower):
                        if "linkeazi" in cell and "consultant" in cell: col_cons = idx
                        if "onboarding" in cell and "date" in cell: col_onboard = idx
                        if "candidate" in cell and "salary" in cell: col_sal = idx
                        if "payment" in cell and "onboard" not in cell: col_pay = idx
                        if "percentage" in cell or "pct" in cell or cell == "%": col_pct = idx
                    found_header = True
                    continue

            if found_header:
                row_upper = " ".join(row_lower).upper()
                if "POSITION" in row_upper and "PLACED" not in row_upper: break
                if len(row) <= max(col_cons, col_onboard, col_sal): continue

                consultant_name = row[col_cons].strip()
                if not consultant_name: continue

                onboard_str = row[col_onboard].strip()
                onboard_date = None
                for fmt in ["%Y-%m-%d", "%d/%m/%Y", "%Y/%m/%d", "%m/%d/%Y", "%d-%b-%y"]:
                    try: onboard_date = datetime.strptime(onboard_str, fmt); break
                    except: pass
                
                if not onboard_date: continue
                if not (onboard_date.year == year and start_m <= onboard_date.month <= end_m): continue

                matched = "Unknown"
                c_norm = normalize_text(consultant_name)
                for conf in TEAM_CONFIG:
                    conf_norm = normalize_text(conf['name'])
                    if conf_norm in c_norm or c_norm in conf_norm: matched = conf['name']; break
                    if conf_norm.split()[0] in c_norm: matched = conf['name']; break
                if matched == "Unknown": continue

                salary_raw = str(row[col_sal]).replace(',', '').replace('$', '').replace('MXN', '').strip()
                try: salary = float(salary_raw)
                except: salary = 0

                pct_val = 1.0
                if col_pct != -1 and len(row) > col_pct:
                    p_str = str(row[col_pct]).replace('%', '').strip()
                    try:
                        p_float = float(p_str)
                        if p_float > 1.0: pct_val = p_float / 100.0
                        else: pct_val = p_float
                    except: pct_val = 1.0

                base_gp_factor = 1.0 if salary < 20000 else 1.5
                calc_gp = salary * base_gp_factor * pct_val
                
                pay_date_str = ""
                status = "Pending"
                if col_pay != -1 and len(row) > col_pay:
                    pay_date_str = row[col_pay].strip()
                    if len(pay_date_str) > 5: status = "Paid"

                records.append({
                    "Consultant": matched,
                    "GP": calc_gp,
                    "Candidate Salary": salary,
                    "Percentage": pct_val,
                    "Onboard Date": onboard_date,
                    "Payment Date": pay_date_str,
                    "Status": status
                })
        
        return pd.DataFrame(records)

    except Exception as e:
        print(f"Financial Error: {e}")
        return pd.DataFrame()

# --- RENDER RECRUITMENT PIT ---
def render_pit(placeholder, current_total, goal, color_class, label):
    percent = (current_total / goal) * 100 if goal > 0 else 0
    if percent > 100: percent = 100
    cats = "🐈"
    if percent > 30: cats = "🐈🐈"
    if percent > 60: cats = "🐈🐈🐈"
    if percent >= 100: cats = "😻🎉"
    html = f"""<div class="section-label">{label}: {int(current_total)} / {goal}</div>
    <div class="pit-container"><div class="{color_class}" style="width: {percent}%;"><div class="cat-squad">{cats}</div></div></div>"""
    placeholder.markdown(html, unsafe_allow_html=True)

# --- RENDER FINANCIAL BAR & COMMISSION ---
def render_money_bar(name, achieved_pct, comm_amount):
    display_pct = min(achieved_pct, 100)
    icon = "💸"
    if display_pct >= 50: icon = "💰"
    if display_pct >= 80: icon = "💎"
    if display_pct >= 100: icon = "👑"

    st.markdown(f"""
    <div style="margin-bottom: 20px;">
        <div style="display: flex; justify-content: space-between; font-size: 0.8em; color: #FFD700; font-family: 'Press Start 2P', monospace;">
            <span>{name}</span>
            <span>{achieved_pct:.1f}% COMPLETED</span> 
        </div>
        <div class="pit-container" style="height: 40px; margin-top: 5px; box-shadow: 4px 4px 0px #000;">
            <div class="money-fill" style="width: {display_pct}%;">
                <div class="cat-squad" style="font-size: 20px; top: -10px;">{icon}</div>
            </div>
        </div>
    </div>
    """, unsafe_allow_html=True)
    
    # 💰 Commission Display (Confidential: No base salary, no target shown)
    if comm_amount > 0:
        st.markdown(f"""
        <div class="comm-box">
            💰 COMMISSION UNLOCKED: ${comm_amount:,.0f}
        </div>
        """, unsafe_allow_html=True)

# --- MAIN APP ---
def main():
    quarter_tabs, quarter_num, start_m, end_m, year = get_quarter_info()
    current_month_tab = datetime.now().strftime("%Y%m")

    st.title("🔥 FILL THE PIT 🔥")

    col1, col2, col3 = st.columns([1, 3, 1])
    with col2:
        start_btn = st.button(f"🚩 START THE GAME")

    if start_btn:
        client = connect_to_google()
        if not client: st.error("CONNECTION ERROR"); return

        monthly_results = []
        quarterly_results = []
        quarterly_total_count = 0
        all_month_details = [] 
        
        # Store calculated financial summaries
        financial_summaries = {}

        with st.spinner(f"🛰️ SCANNING MONTH & Q{quarter_num} DATA..."):
            
            # 1. Fetch Sales Data Frame
            sales_df = fetch_financial_df(client, start_m, end_m, year)
            
            # 2. Calculate Financials using new logic
            for conf in TEAM_CONFIG:
                summary = calculate_consultant_performance(
                    sales_df, 
                    conf['name'], 
                    conf['base_salary'], 
                    conf.get('is_team_lead', False)
                )
                financial_summaries[conf['name']] = summary

            # 3. Recruitment Data
            for consultant in TEAM_CONFIG:
                m_count, m_details = fetch_consultant_data(client, consultant, current_month_tab)
                all_month_details.extend(m_details)

                q_count = 0
                for q_tab in quarter_tabs:
                    if q_tab == current_month_tab: q_count += m_count
                    else:
                        c, _ = fetch_consultant_data(client, consultant, q_tab)
                        q_count += c

                monthly_results.append({"name": consultant['name'], "count": m_count})
                quarterly_results.append({"name": consultant['name'], "count": q_count})
                quarterly_total_count += q_count

        time.sleep(0.5)

        # --- ANIMATION SECTIONS ---
        st.markdown(f'<div class="header-bordered">MONTHLY GOAL ({current_month_tab})</div>', unsafe_allow_html=True)
        pit_month_ph = st.empty()
        stats_month_ph = st.empty()

        st.markdown(f'<div class="header-bordered" style="margin-top: 30px; border-color: #FFFF00; color: #FFA500;">SEASON CAMPAIGN (Q{quarter_num})</div>', unsafe_allow_html=True)
        pit_quarter_ph = st.empty()
        stats_quarter_ph = st.empty()

        mvp_col1, mvp_col2 = st.columns(2)
        with mvp_col1: mvp_month_ph = st.empty()
        with mvp_col2: mvp_season_ph = st.empty()

        monthly_total = sum([r['count'] for r in monthly_results])

        # Animation Loop
        steps = 20
        for step in range(steps + 1):
            curr_m = (monthly_total / steps) * step
            render_pit(pit_month_ph, curr_m, MONTHLY_GOAL, "pit-fill-month", "MONTH TOTAL")
            curr_q = (quarterly_total_count / steps) * step
            render_pit(pit_quarter_ph, curr_q, QUARTERLY_GOAL, "pit-fill-season", "SEASON TOTAL")
            
            if step == steps:
                cols_m = stats_month_ph.columns(len(monthly_results))
                for idx, res in enumerate(monthly_results):
                    with cols_m[idx]: st.markdown(f"""<div class="stat-card"><div class="stat-name">{res['name']}</div><div class="stat-val">{res['count']}</div></div>""", unsafe_allow_html=True)
                cols_q = stats_quarter_ph.columns(len(quarterly_results))
                for idx, res in enumerate(quarterly_results):
                    with cols_q[idx]: st.markdown(f"""<div class="stat-card" style="border-color: #FFFF00;"><div class="stat-name">{res['name']}</div><div class="stat-val" style="color: #000000;">{res['count']}</div></div>""", unsafe_allow_html=True)
            time.sleep(0.02)

        # ==========================================
        # 💰 FINANCIAL QUEST
        # ==========================================
        st.markdown("<br>", unsafe_allow_html=True)
        st.markdown(f'<div class="header-bordered" style="border-color: #28a745; color: #28a745;">💰 FINANCIAL QUEST (Q{quarter_num})</div>', unsafe_allow_html=True)
        
        fin_cols = st.columns(2)
        for idx, conf in enumerate(TEAM_CONFIG):
            c_name = conf['name']
            # Get pre-calculated summary
            summary = financial_summaries.get(c_name, {})
            achieved_pct = summary.get("Target Achieved", 0.0)
            est_comm = summary.get("Est. Commission", 0.0)
            
            with fin_cols[idx % 2]:
                render_money_bar(c_name, achieved_pct, est_comm)

        # ==========================================
        # 🏆 MVPs
        # ==========================================
        df_m = pd.DataFrame(monthly_results)
        if not df_m.empty and monthly_total > 0:
            mvp_m = df_m.sort_values(by="count", ascending=False).iloc[0]
            mvp_month_ph.markdown(f"""<div class="mvp-card"><h3 style="color: #FFD700; margin:0; font-size: 1em;">🏆 MONTHLY MVP</h3><h2 style="color: white; margin: 10px 0;">{mvp_m['name']}</h2><h1 style="color: #000000; margin:0;">{mvp_m['count']}</h1></div>""", unsafe_allow_html=True)

        df_q = pd.DataFrame(quarterly_results)
        if not df_q.empty and quarterly_total_count > 0:
            mvp_q = df_q.sort_values(by="count", ascending=False).iloc[0]
            mvp_season_ph.markdown(f"""<div class="mvp-card" style="border-color: #00FFFF; "><h3 style="color: #00FFFF; margin:0; font-size: 1em;">🌊 SEASON MVP</h3><h2 style="color: white; margin: 10px 0;">{mvp_q['name']}</h2><h1 style="color: #FFFFFF; margin:0;">{mvp_q['count']}</h1></div>""", unsafe_allow_html=True)
            st.balloons()

        # ==========================================
        # 📝 LOGS
        # ==========================================
        if all_month_details:
            st.markdown("---")
            with st.expander(f"📜 MISSION LOGS ({current_month_tab}) - CLICK TO OPEN", expanded=False):
                df_all = pd.DataFrame(all_month_details)
                tab_names = [c['name'] for c in TEAM_CONFIG]
                tabs = st.tabs(tab_names)
                for idx, tab in enumerate(tabs):
                    with tab:
                        current_consultant = tab_names[idx]
                        df_c = df_all[df_all['Consultant'] == current_consultant]
                        if not df_c.empty:
                            df_agg = df_c.groupby(['Company', 'Position'])['Count'].sum().reset_index()
                            df_agg = df_agg.sort_values(by='Count', ascending=False)
                            df_agg['Count'] = df_agg['Count'].astype(str)
                            st.dataframe(df_agg, use_container_width=True, hide_index=True, column_config={"Company": st.column_config.TextColumn("TARGET COMPANY"), "Position": st.column_config.TextColumn("TARGET ROLE"), "Count": st.column_config.TextColumn("CVs")})
                        else: st.info(f"NO DATA FOR {current_consultant}")

        elif monthly_total == 0:
            st.markdown("---")
            st.info("NO DATA FOUND FOR THIS MONTH YET.")

if __name__ == "__main__":
    main()
