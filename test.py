import streamlit as st
import streamlit.components.v1 as components
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from gspread.exceptions import APIError
import pandas as pd
import os
import time
import random
import unicodedata
from datetime import datetime, timedelta

# ==========================================
# 🔧 1. 配置与季度定义
# ==========================================
SALES_SHEET_ID = '1jniQ-GpeMINjQMebniJ_J1eLVLQIR1NGbSjTtOFP9Q8'
SALES_TAB_NAME = 'Positions'

# 核心目标
CV_TARGET_INDIVIDUAL = 87
MONTHLY_TEAM_GOAL = 116
QUARTERLY_TEAM_GOAL = 348

# 计算当前和上个季度的字符串标识
now = datetime.now()
curr_year = now.year
curr_q = (now.month - 1) // 3 + 1
CURRENT_Q_STR = f"{curr_year} Q{curr_q}"

if curr_q == 1:
    PREV_Q_STR = f"{curr_year - 1} Q4"
    prev_q_start_m, prev_q_year = 10, curr_year - 1
else:
    PREV_Q_STR = f"{curr_year} Q{curr_q - 1}"
    prev_q_start_m, prev_q_year = (curr_q - 2) * 3 + 1, curr_year

# 季度包含的月份表 (用于抓取数据)
start_m = (curr_q - 1) * 3 + 1
CURR_Q_MONTHS = [f"{curr_year}{m:02d}" for m in range(start_m, start_m + 3)]
PREV_Q_MONTHS = [f"{prev_q_year}{m:02d}" for m in range(prev_q_start_m, prev_q_start_m + 3)]

TEAM_CONFIG_TEMPLATE = [
    {"name": "Raul Solis", "id": "1vQuN-iNBRUug5J6gBMX-52jp6oogbA77SaeAf9j_zYs", "keyword": "Name", "base_salary": 11000},
    {"name": "Estela Peng", "id": "1sUkffAXzWnpzhhmklqBuwtoQylpR1U18zqBQ-lsp7Z4", "keyword": "姓名", "base_salary": 20800},
    {"name": "Ana Cruz", "id": "1VMVw5YCV12eI8I-VQSXEKg86J2IVZJEgjPJT7ggAFD0", "keyword": "Name", "base_salary": 13000},
    {"name": "Karina Albarran", "id": "1zc4ghvfjIxH0eJ2aXfopOWHqiyTDlD8yFNjBzpH07D8", "keyword": "Name", "base_salary": 15000},
]

# ==========================================
# 🎨 2. 游戏化 CSS 样式 (完全保留自原版)
# ==========================================
st.set_page_config(page_title="Fill The Pit", page_icon="🎮", layout="wide")

st.markdown("""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Press+Start+2P&display=swap');
    @import url('https://fonts.googleapis.com/css2?family=Fredoka+One&display=swap');

    .stApp { background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); font-family: 'Press Start 2P', monospace; }
    h1 { text-shadow: 4px 4px 0px #000; color: #FFD700 !important; text-align: center; font-size: 3.5em !important; -webkit-text-stroke: 2px #000; }
    
    .stButton { display: flex; justify-content: center; width: 100%; margin-left: 200px; }
    .stButton>button { 
        background-color: #FF4757; color: white; border: 4px solid #000; border-radius: 15px; 
        font-family: 'Press Start 2P', monospace; font-size: 24px !important; padding: 20px 40px !important;
        box-shadow: 0px 8px 0px #a71c2a; width: 100%; 
    }
    .stButton>button:hover { transform: translateY(4px); box-shadow: 0px 4px 0px #a71c2a; background-color: #ff6b81; }

    .pit-container { background-color: #eee; border: 3px solid #000; border-radius: 12px; width: 100%; position: relative; margin-bottom: 12px; overflow: hidden; }
    .pit-height-std { height: 25px; }
    .pit-height-boss { height: 60px; border-width: 4px; }
    
    @keyframes barberpole { from { background-position: 0 0; } to { background-position: 50px 50px; } }
    @keyframes rainbow-move { 0% { background-position: 0% 50%; } 50% { background-position: 100% 50%; } 100% { background-position: 0% 50%; } }
    .pit-fill-boss { background: linear-gradient(270deg, #ff6b6b, #feca57, #48dbfb, #ff9ff3, #54a0ff); background-size: 400% 400%; animation: rainbow-move 6s ease infinite; height: 100%; display: flex; align-items: center; justify-content: flex-end; }
    .pit-fill-season { background-image: linear-gradient(45deg, #3742fa 25%, #5352ed 25%, #5352ed 50%, #3742fa 50%, #3742fa 75%, #5352ed 75%, #5352ed 100%); background-size: 50px 50px; animation: barberpole 3s linear infinite; height: 100%; display: flex; align-items: center; justify-content: flex-end; }
    .money-fill { background-image: linear-gradient(45deg, #2ed573 25%, #7bed9f 25%, #7bed9f 50%, #2ed573 50%, #2ed573 75%, #7bed9f 75%, #7bed9f 100%); background-size: 50px 50px; animation: barberpole 4s linear infinite; height: 100%; display: flex; align-items: center; justify-content: flex-end; }
    .cv-fill { background-image: linear-gradient(45deg, #ff9ff3 25%, #f368e0 25%, #f368e0 50%, #ff9ff3 50%, #ff9ff3 75%, #f368e0 75%, #f368e0 100%); background-size: 50px 50px; animation: barberpole 3s linear infinite; height: 100%; display: flex; align-items: center; justify-content: flex-end; }
    
    .player-card { background-color: #FFF; border: 4px solid #000; border-radius: 15px; padding: 20px; margin-bottom: 30px; color: #333; box-shadow: 8px 8px 0px rgba(0,0,0,0.2); }
    .card-border-1 { border-bottom: 6px solid #ff6b6b; }
    .card-border-2 { border-bottom: 6px solid #feca57; }
    .card-border-3 { border-bottom: 6px solid #48dbfb; }
    .card-border-4 { border-bottom: 6px solid #ff9ff3; }
    
    .status-badge-pass { background-color: #2ed573; color: white; padding: 8px 12px; border-radius: 20px; border: 2px solid #000; font-size: 0.6em; box-shadow: 2px 2px 0px #000; animation: bounce 1s infinite alternate; }
    .status-badge-loading { background-color: #feca57; color: #000; padding: 8px 12px; border-radius: 20px; border: 2px solid #000; font-size: 0.6em; }
    @keyframes bounce { from { transform: translateY(0); } to { transform: translateY(-2px); } }

    .comm-unlocked { background-color: #fff4e6; border: 2px solid #ff9f43; border-radius: 10px; color: #e67e22; text-align: center; padding: 10px; margin-top: 15px; font-weight: bold; font-size: 0.9em; box-shadow: inset 0 0 10px #ffeaa7;}
    .comm-locked { background-color: #f1f2f6; border: 2px solid #ced6e0; border-radius: 10px; color: #a4b0be; text-align: center; padding: 10px; margin-top: 15px; font-size: 0.8em; }
    
    .header-bordered { background-color: #FFF; border: 4px solid #000; border-radius: 15px; box-shadow: 6px 6px 0px #000; padding: 20px; text-align: center; margin-bottom: 25px; }
    .sub-label { font-family: 'Fredoka One', sans-serif; font-size: 0.8em; color: #FFF; margin-bottom: 5px; text-transform: uppercase; text-shadow: 1px 1px 0px #000; }
    
    .stat-card { background-color: #fff; border: 3px solid #000; border-radius: 10px; padding: 10px; text-align: center; }
    .stat-val { color: #000; font-size: 1.2em; font-weight: bold; }
    .stat-name { color: #555; font-size: 0.8em; }
    </style>
    """, unsafe_allow_html=True)

# ==========================================
# ⚙️ 3. 核心计算逻辑 (带跨季度追溯)
# ==========================================

def normalize_text(text):
    return ''.join(c for c in unicodedata.normalize('NFD', str(text)) if unicodedata.category(c) != 'Mn').lower()

def safe_api_call(func, *args, **kwargs):
    for i in range(5):
        try: return func(*args, **kwargs)
        except APIError as e:
            if "429" in str(e): time.sleep(2 * (2 ** i) + random.uniform(0, 1))
            else: raise e
    return None

def calculate_commission_tier(total_gp, base_salary, is_team_lead=False):
    t1, t2, t3 = (4.5, 6.75, 11.25) if is_team_lead else (9.0, 13.5, 22.5)
    if total_gp < t1 * base_salary: return 0, 0
    elif total_gp < t2 * base_salary: return 1, 1
    elif total_gp < t3 * base_salary: return 2, 2
    else: return 3, 3

def calculate_single_deal_commission(salary, multiplier):
    if multiplier == 0: return 0
    if salary < 20000: base = 1000
    elif salary < 30000: base = salary * 0.05
    elif salary < 50000: base = salary * 1.5 * 0.05
    else: base = salary * 2.0 * 0.05
    return base * multiplier

def get_commission_pay_date(payment_date_obj):
    if pd.isna(payment_date_obj): return None
    try:
        year = payment_date_obj.year + (payment_date_obj.month // 12)
        month = (payment_date_obj.month % 12) + 1
        return datetime(year, month, 15)
    except: return None

# ==========================================
# 🛰️ 4. 数据爬取 (带简历明细采集)
# ==========================================

def connect_to_google():
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    if "gcp_service_account" in st.secrets:
        creds = ServiceAccountCredentials.from_json_keyfile_dict(dict(st.secrets["gcp_service_account"]), scope)
        return gspread.authorize(creds)
    return None

def fetch_role_info(client, sheet_id):
    try:
        sheet = safe_api_call(client.open_by_key, sheet_id)
        ws = safe_api_call(sheet.worksheet, 'Credentials')
        role_raw = safe_api_call(ws.acell, 'B1').value or "Consultant"
        is_lead = "lead" in role_raw.lower() or "manager" in role_raw.lower()
        is_intern = "intern" in role_raw.lower()
        return "Intern" if is_intern else "Full-Time", is_lead, role_raw.title()
    except: return "Full-Time", False, "Consultant"

def fetch_cv_data_with_details(client, conf, tabs):
    """同时获取简历总数和明细"""
    total = 0
    details = []
    COMPANY_KEYS = ["Company", "Client", "Cliente", "公司名称", "客户"]
    POSITION_KEYS = ["Position", "Role", "Posición", "职位", "岗位"]
    
    try:
        sheet = safe_api_call(client.open_by_key, conf['id'])
        for tab in tabs:
            try:
                ws = safe_api_call(sheet.worksheet, tab)
                rows = safe_api_call(ws.get_all_values)
                target_key = conf.get('keyword', 'Name')
                current_company = "Unknown"
                current_position = "Unknown"
                
                for r in rows:
                    if not r: continue
                    cleaned = [str(x).strip() for x in r]
                    
                    # 检查是否为标题行
                    first_cell = cleaned[0] if cleaned else ""
                    if first_cell in COMPANY_KEYS:
                        current_company = cleaned[1] if len(cleaned) > 1 else "Unknown"
                    elif first_cell in POSITION_KEYS:
                        current_position = cleaned[1] if len(cleaned) > 1 else "Unknown"
                    
                    # 查找简历发送情况
                    if target_key in cleaned:
                        idx = cleaned.index(target_key)
                        cands = [x for x in cleaned[idx+1:] if x]
                        count = len(cands)
                        total += count
                        # 如果是当月 Tab，记录详细日志
                        if tab == tabs[-1]:
                            if count > 0:
                                details.append({
                                    "Consultant": conf['name'],
                                    "Company": current_company,
                                    "Position": current_position,
                                    "Count": count
                                })
            except: continue
    except: pass
    return total, details

def fetch_sales_history(client, year):
    """获取全年的销售数据，以便追溯上季度单子"""
    records = []
    try:
        sheet = safe_api_call(client.open_by_key, SALES_SHEET_ID)
        ws = safe_api_call(sheet.worksheet, SALES_TAB_NAME)
        rows = safe_api_call(ws.get_all_values)
        col_cons, col_onboard, col_pay, col_sal, col_pct = -1, -1, -1, -1, -1
        found_header = False
        
        for row in rows:
            row_l = [str(x).strip().lower() for x in row]
            if not found_header:
                if any("consultant" in c for c in row_l) and any("onboarding" in c for c in row_l):
                    for idx, c in enumerate(row_l):
                        if "consultant" in c: col_cons = idx
                        if "onboarding" in c and "date" in c: col_onboard = idx
                        if "salary" in c: col_sal = idx
                        if "payment" in c and "date" in c: col_pay = idx
                        if "percentage" in c or c == "%": col_pct = idx
                    found_header = True; continue
            else:
                if len(row) <= max(col_cons, col_onboard): continue
                c_name_raw = row[col_cons].strip()
                if not c_name_raw: continue
                
                onboard_date = None
                for fmt in ["%Y-%m-%d", "%d/%m/%Y", "%m/%d/%Y", "%Y/%m/%d"]:
                    try: onboard_date = datetime.strptime(row[col_onboard].strip(), fmt); break
                    except: pass
                if not onboard_date or onboard_date.year != year: continue

                # 标记该单据所属季度
                q_idx = (onboard_date.month - 1) // 3 + 1
                q_label = f"{onboard_date.year} Q{q_idx}"
                
                # 匹配顾问
                matched = "Unknown"
                for conf in TEAM_CONFIG_TEMPLATE:
                    if normalize_text(conf['name']) in normalize_text(c_name_raw): matched = conf['name']; break
                if matched == "Unknown": continue

                sal = float(str(row[col_sal]).replace(',','').replace('$','').strip() or 0)
                pct = 1.0
                if col_pct != -1 and len(row) > col_pct:
                    try: 
                        p_val = float(str(row[col_pct]).replace('%','').strip())
                        pct = p_val/100 if p_val > 1 else p_val
                    except: pct = 1.0
                
                pay_date_obj = None
                status = "Pending"
                if col_pay != -1 and len(row) > col_pay:
                    pay_str = row[col_pay].strip()
                    if len(pay_str) > 5:
                        status = "Paid"
                        for fmt in ["%Y-%m-%d", "%d/%m/%Y", "%m/%d/%Y", "%Y/%m/%d"]:
                            try: pay_date_obj = datetime.strptime(pay_str, fmt); break
                            except: pass

                records.append({
                    "Consultant": matched, "GP": sal * (1.5 if sal >= 20000 else 1.0) * pct,
                    "Salary": sal, "Pct": pct, "Status": status, "PayDateObj": pay_date_obj,
                    "Quarter": q_label
                })
    except: pass
    return pd.DataFrame(records)

# ==========================================
# 🎨 5. UI 渲染组件
# ==========================================

def render_bar(current, goal, color_class, label, is_boss=False):
    percent = (current / goal * 100) if goal > 0 else 0
    height_cls = "pit-height-boss" if is_boss else "pit-height-std"
    cat = "🎉" if percent >= 100 else ""
    st.markdown(f"""
        <div class="sub-label">{label} ({percent:.1f}%)</div>
        <div class="pit-container {height_cls}">
            <div class="{color_class}" style="width: {min(percent, 100)}%;">
                <div style="margin-right:10px; font-size:20px;">{cat}</div>
            </div>
        </div>
    """, unsafe_allow_html=True)

def render_player_card(conf, q_cvs, prev_q_cvs, sales_df, card_idx):
    c_name = conf['name']
    role = conf['role']
    is_lead = conf['is_team_lead']
    base = conf['base_salary']
    
    # --- 1. 判定当前季度是否达标 ---
    c_sales_curr = sales_df[(sales_df['Consultant'] == c_name) & (sales_df['Quarter'] == CURRENT_Q_STR)]
    booked_gp_curr = c_sales_curr['GP'].sum()
    target_gp = base * (4.5 if is_lead else 9.0)
    
    is_qualified_curr = (booked_gp_curr >= target_gp or q_cvs >= CV_TARGET_INDIVIDUAL) if role != "Intern" else (q_cvs >= CV_TARGET_INDIVIDUAL)

    # --- 2. 判定上个季度是否达标 (用于结算历史佣金) ---
    c_sales_prev = sales_df[(sales_df['Consultant'] == c_name) & (sales_df['Quarter'] == PREV_Q_STR)]
    booked_gp_prev = c_sales_prev['GP'].sum()
    is_qualified_prev = (booked_gp_prev >= target_gp or prev_q_cvs >= CV_TARGET_INDIVIDUAL) if role != "Intern" else (prev_q_cvs >= CV_TARGET_INDIVIDUAL)

    # --- 3. 佣金计算 (扫描本季度+上季度) ---
    total_comm = 0
    payout_limit = datetime.now() + timedelta(days=20)

    if role != "Intern":
        # 计算逻辑：针对每个季度，先看是否达标，达标后再看该季度内已付款的单据结算日是否到期
        for q_label, is_q_ok, q_df in [(CURRENT_Q_STR, is_qualified_curr, c_sales_curr), (PREV_Q_STR, is_qualified_prev, c_sales_prev)]:
            if is_q_ok:
                running_gp = 0
                paid_deals = q_df[q_df['Status'] == 'Paid'].sort_values('PayDateObj')
                for _, row in paid_deals.iterrows():
                    running_gp += row['GP']
                    lvl, mult = calculate_commission_tier(running_gp, base, is_lead)
                    # 达标后保底 Level 1
                    if lvl == 0:
                        _, mult = calculate_commission_tier(base * (5.0 if is_lead else 10.0), base, is_lead)
                    
                    p_date = get_commission_pay_date(row['PayDateObj'])
                    if p_date and p_date <= payout_limit:
                        total_comm += calculate_single_deal_commission(row['Salary'], mult) * row['Pct']
        
        # 主管津贴 (仅限当前季度达标后领取当月发放的所有 Override)
        if is_lead and is_qualified_curr:
            ov_mask = (sales_df['Status'] == 'Paid') & (sales_df['Consultant'] != c_name) & (sales_df['Consultant'] != "Estela Peng")
            for _, row in sales_df[ov_mask].iterrows():
                p_date = get_commission_pay_date(row['PayDateObj'])
                if p_date and p_date <= payout_limit:
                    total_comm += 1000 * row['Pct']

    # --- 4. UI 渲染 ---
    border = f"card-border-{(card_idx % 4) + 1}"
    status_html = '<span class="status-badge-pass">LEVEL UP! 🌟</span>' if is_qualified_curr else '<span class="status-badge-loading">LOADING... 🚀</span>'
    
    st.markdown(f"""
    <div class="player-card {border}">
        <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:15px;">
            <div><b style="font-size:1.1em;">{c_name} {"👑" if is_lead else ""}</b><br>
            <small style="color:#999;">{conf['title_display']}</small></div>
            {status_html}
        </div>
    """, unsafe_allow_html=True)

    if role == "Intern":
        render_bar(q_cvs, CV_TARGET_INDIVIDUAL, "cv-fill", "Q. CVs")
    else:
        render_bar(booked_gp_curr, target_gp, "money-fill", "GP Target")
        st.markdown('<div style="font-size:0.5em; color:#666; margin:5px 0;">OR RECRUITMENT GOAL:</div>', unsafe_allow_html=True)
        render_bar(q_cvs, CV_TARGET_INDIVIDUAL, "cv-fill", "Q. CVs")

    if role != "Intern":
        if total_comm > 0:
            st.markdown(f'<div class="comm-unlocked">💰 UNLOCKED: ${total_comm:,.0f}</div>', unsafe_allow_html=True)
        else:
            msg = "🔒 LOCKED (TARGET NOT MET)" if not is_qualified_curr else "🔒 LOCKED (WAITING PAY)"
            st.markdown(f'<div class="comm-locked">{msg}</div>', unsafe_allow_html=True)
    st.markdown("</div>", unsafe_allow_html=True)

# ==========================================
# 🎮 6. 主程序
# ==========================================

def main():
    st.title("👾 FILL THE PIT 👾")
    
    col1, col2, col3 = st.columns([1, 3, 1])
    with col2:
        start_btn = st.button(f"🚩 PRESS START")

    if start_btn:
        client = connect_to_google()
        if not client: st.error("CONNECTION ERROR"); return

        active_team = []
        q_cv_counts = {}
        prev_q_cv_counts = {}
        m_cv_counts = {}
        all_mission_logs = []

        with st.spinner("🛰️ SCANNING SECTOR..."):
            # 1. 抓取角色和简历
            for conf in TEAM_CONFIG_TEMPLATE:
                role, is_lead, title = fetch_role_info(client, conf['id'])
                c_conf = conf.copy()
                c_conf.update({"role": role, "is_team_lead": is_lead, "title_display": title})
                active_team.append(c_conf)
                
                # 获取本季度 CV 及其明细
                q_total, m_logs = fetch_cv_data_with_details(client, c_conf, CURR_Q_MONTHS)
                all_mission_logs.extend(m_logs)
                
                # 仅获取当月总数 (用于 Boss Bar)
                m_total, _ = fetch_cv_data_with_details(client, c_conf, [CURR_Q_MONTHS[-1]])
                
                # 获取上个季度总数 (用于结算上季佣金)
                prev_q_total, _ = fetch_cv_data_with_details(client, c_conf, PREV_Q_MONTHS)
                
                q_cv_counts[conf['name']] = q_total
                m_cv_counts[conf['name']] = m_total
                prev_q_cv_counts[conf['name']] = prev_q_total

            # 2. 抓取全年销售数据
            sales_df = fetch_sales_history(client, now.year)

        # --- Boss Bars ---
        st.markdown(f'<div class="header-bordered" style="border-color:#feca57;">🏆 TEAM MONTHLY GOAL ({CURR_Q_MONTHS[-1]})</div>', unsafe_allow_html=True)
        monthly_total = sum(m_cv_counts.values())
        render_bar(monthly_total, MONTHLY_TEAM_GOAL, "pit-fill-boss", f"{int(monthly_total)} / {MONTHLY_TEAM_GOAL} CVs", True)
        
        st.markdown(f'<div class="header-bordered" style="border-color:#54a0ff; margin-top:20px;">🌊 TEAM QUARTERLY GOAL ({CURRENT_Q_STR})</div>', unsafe_allow_html=True)
        quarterly_total = sum(q_cv_counts.values())
        render_bar(quarterly_total, QUARTERLY_TEAM_GOAL, "pit-fill-season", f"{int(quarterly_total)} / {QUARTERLY_TEAM_GOAL} CVs", True)

        # --- Player Hub ---
        st.markdown("<br>", unsafe_allow_html=True)
        st.markdown(f'<div class="header-bordered" style="border-color:#48dbfb;">❄️ PLAYER STATS ({CURRENT_Q_STR})</div>', unsafe_allow_html=True)
        
        row1 = st.columns(2)
        row2 = st.columns(2)
        all_cols = row1 + row2
        for idx, conf in enumerate(active_team):
            with all_cols[idx]:
                render_player_card(conf, q_cv_counts[conf['name']], prev_q_cv_counts[conf['name']], sales_df, idx)

        # --- Mission Logs (简历明细) ---
        if all_mission_logs:
            st.markdown("---")
            with st.expander(f"📜 MISSION LOGS ({CURR_Q_MONTHS[-1]})", expanded=False):
                log_df = pd.DataFrame(all_mission_logs)
                player_names = [c['name'] for c in active_team]
                tabs = st.tabs(player_names)
                for idx, tab in enumerate(tabs):
                    with tab:
                        p_name = player_names[idx]
                        p_logs = log_df[log_df['Consultant'] == p_name]
                        if not p_logs.empty:
                            # 按照原版聚合
                            p_agg = p_logs.groupby(['Company', 'Position'])['Count'].sum().reset_index()
                            p_agg = p_agg.sort_values('Count', ascending=False)
                            st.dataframe(p_agg, use_container_width=True, hide_index=True, column_config={
                                "Company": st.column_config.TextColumn("TARGET COMPANY"),
                                "Position": st.column_config.TextColumn("TARGET ROLE"),
                                "Count": st.column_config.TextColumn("CVs")
                            })
                        else:
                            st.info(f"NO MISSION DATA FOR {p_name}")

if __name__ == "__main__":
    main()
