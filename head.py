import streamlit as st
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import pandas as pd
import os
import time
from datetime import datetime, timedelta
import unicodedata

# ==========================================
# 🔧 配置区域
# ==========================================
SALES_SHEET_ID = '1jniQ-GpeMINjQMebniJ_J1eLVLQIR1NGbSjTtOFP9Q8'
SALES_TAB_NAME = 'Positions'

# 基础配置模板
TEAM_CONFIG_TEMPLATE = [
    {
        "name": "Raul Solis",
        "id": "1vQuN-iNBRUug5J6gBMX-52jp6oogbA77SaeAf9j_zYs",
        "keyword": "Name",
        "base_salary": 11000
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

# 🎯 TEAM GOALS (团队总目标)
MONTHLY_GOAL = 114
QUARTERLY_GOAL = 342
# ==========================================

st.set_page_config(page_title="Fill The Pit", page_icon="🕹️", layout="wide")

# --- 🎨 PLAYFUL & ARCADE CSS STYLING ---
st.markdown("""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Press+Start+2P&display=swap');
    @import url('https://fonts.googleapis.com/css2?family=Fredoka+One&display=swap');

    /* Global Background: Arcade Gradient */
    .stApp {
        background: linear-gradient(135deg, #6a11cb 0%, #2575fc 100%);
        font-family: 'Press Start 2P', monospace;
        color: #fff;
    }

    h1 {
        text-shadow: 4px 4px 0px #000;
        color: #ffeaa7 !important;
        text-align: center;
        font-size: 3em !important;
        margin-bottom: 20px;
        -webkit-text-stroke: 2px #000;
    }

    /* 🔘 START BUTTON: Juicy & Bouncy */
    .stButton {
        display: flex;
        justify-content: center;
        width: 100%;
        margin-left: 180px; 
    }
    .stButton>button {
        background-color: #ff7675;
        color: white;
        border: 4px solid #000;
        border-radius: 20px;
        font-family: 'Press Start 2P', monospace;
        font-size: 22px !important; 
        padding: 15px 40px !important; 
        box-shadow: 0px 8px 0px #d63031;
        transition: all 0.1s;
        width: 100%;
    }
    .stButton>button:hover {
        transform: translateY(4px);
        box-shadow: 0px 4px 0px #d63031;
        background-color: #fab1a0;
        border-color: #000;
    }
    .stButton>button:active {
        transform: translateY(8px);
        box-shadow: 0px 0px 0px #d63031;
    }

    /* --- 📊 PROGRESS BARS --- */
    
    .pit-container {
        background-color: #dfe6e9;
        border: 4px solid #000;
        border-radius: 15px;
        width: 100%;
        position: relative;
        margin-bottom: 15px;
        box-shadow: 6px 6px 0px rgba(0,0,0,0.3);
        overflow: hidden;
    }
    
    /* Heights */
    .pit-h-std { height: 30px; }
    .pit-h-med { height: 45px; } /* Monthly */
    .pit-h-big { height: 70px; border-width: 5px; } /* Quarterly (Big Boss) */

    /* Animations */
    @keyframes stripes {
        from { background-position: 0 0; }
        to { background-position: 50px 50px; }
    }
    @keyframes rainbow {
        0% { background-position: 0% 50%; }
        50% { background-position: 100% 50%; }
        100% { background-position: 0% 50%; }
    }

    /* Styles */
    .fill-gold { 
        background-image: linear-gradient(45deg, #f1c40f 25%, #f39c12 25%, #f39c12 50%, #f1c40f 50%, #f1c40f 75%, #f39c12 75%, #f39c12 100%);
        background-size: 40px 40px;
        animation: stripes 1s linear infinite;
        height: 100%; display: flex; align-items: center; justify-content: flex-end; 
    }
    
    .fill-rainbow {
        background: linear-gradient(270deg, #ff9ff3, #feca57, #ff6b6b, #48dbfb, #1dd1a1);
        background-size: 400% 400%;
        animation: rainbow 4s ease infinite;
        height: 100%; display: flex; align-items: center; justify-content: flex-end; 
    }
    
    .fill-blue { 
        background-image: linear-gradient(45deg, #54a0ff 25%, #2e86de 25%, #2e86de 50%, #54a0ff 50%, #54a0ff 75%, #2e86de 75%, #2e86de 100%);
        background-size: 30px 30px;
        animation: stripes 2s linear infinite;
        height: 100%; display: flex; align-items: center; justify-content: flex-end; 
    }
    
    .fill-green { 
        background-image: linear-gradient(45deg, #55efc4 25%, #00b894 25%, #00b894 50%, #55efc4 50%, #55efc4 75%, #00b894 75%, #00b894 100%);
        background-size: 30px 30px;
        animation: stripes 2s linear infinite;
        height: 100%; display: flex; align-items: center; justify-content: flex-end; 
    }

    .cat-icon {
        margin-right: 15px;
        font-size: 24px;
        filter: drop-shadow(2px 2px 0px rgba(0,0,0,0.5));
    }

    /* --- 🃏 PLAYER CARDS --- */
    
    .player-card {
        background-color: #fff;
        border: 4px solid #000;
        border-radius: 20px;
        padding: 20px;
        margin-bottom: 30px;
        color: #2d3436;
        box-shadow: 8px 8px 0px rgba(0,0,0,0.4);
        transition: transform 0.2s;
    }
    .player-card:hover { transform: translateY(-3px); }

    /* Card Borders */
    .bd-1 { border-bottom: 8px solid #ff6b6b; }
    .bd-2 { border-bottom: 8px solid #feca57; }
    .bd-3 { border-bottom: 8px solid #48dbfb; }
    .bd-4 { border-bottom: 8px solid #ff9ff3; }

    .player-header {
        display: flex; justify-content: space-between; align-items: center;
        border-bottom: 2px dashed #b2bec3; padding-bottom: 10px; margin-bottom: 15px;
    }
    .p-name { font-size: 1.1em; font-weight: bold; }
    .p-role { font-size: 0.6em; color: #636e72; font-family: 'Fredoka One', sans-serif; }

    /* Badges */
    .badge-pass {
        background-color: #00b894; color: white; padding: 5px 10px; 
        border: 2px solid #000; border-radius: 15px; font-size: 0.6em;
        box-shadow: 2px 2px 0px rgba(0,0,0,0.2);
    }
    .badge-load {
        background-color: #feca57; color: #2d3436; padding: 5px 10px; 
        border: 2px solid #000; border-radius: 15px; font-size: 0.6em;
        box-shadow: 2px 2px 0px rgba(0,0,0,0.2);
    }

    /* Labels */
    .sub-label {
        font-family: 'Fredoka One', sans-serif;
        font-size: 0.9em;
        color: #FFFFFF; /* ✅ 修复：白色字体 */
        margin-bottom: 6px;
        text-transform: uppercase;
        text-shadow: 2px 2px 0px #000; /* ✅ 增加阴影，对比度更强 */
        letter-spacing: 1px;
    }
    
    .card-label {
        /* 卡片内部的标签，背景是白色，所以用深色字 */
        font-family: 'Fredoka One', sans-serif;
        font-size: 0.7em;
        color: #636e72;
        margin-bottom: 5px;
        text-transform: uppercase;
    }

    /* Commission Loot Box */
    .loot-box-unlocked {
        background-color: #fff4e6; border: 3px solid #e67e22; border-radius: 12px;
        color: #d35400; text-align: center; padding: 12px; margin-top: 15px;
        font-weight: bold; font-family: 'Fredoka One', sans-serif;
        box-shadow: inset 0 0 15px #ffeaa7;
    }
    .loot-box-locked {
        background-color: #f1f2f6; border: 3px solid #ced6e0; border-radius: 12px;
        color: #a4b0be; text-align: center; padding: 12px; margin-top: 15px;
        font-family: 'Fredoka One', sans-serif;
    }

    /* Header Box */
    .header-box {
        background: #fff; border: 4px solid #000; border-radius: 20px;
        padding: 15px; text-align: center; margin-bottom: 20px;
        color: #2d3436; font-size: 1.1em;
        box-shadow: 6px 6px 0px rgba(0,0,0,0.3);
    }
    
    .stat-card {
        background-color: rgba(255,255,255,0.2); border: 2px solid #fff;
        border-radius: 10px; padding: 10px; text-align: center;
        color: #fff; margin: 5px;
    }

    .dataframe { font-family: 'Press Start 2P', monospace !important; font-size: 0.8em !important; }
    </style>
    """, unsafe_allow_html=True)


# ==========================================
# 🧮 核心逻辑 (保持功能一致)
# ==========================================

def normalize_text(text):
    return ''.join(c for c in unicodedata.normalize('NFD', str(text)) if unicodedata.category(c) != 'Mn').lower()

def get_payout_date_from_month_key(month_key):
    try:
        dt = datetime.strptime(str(month_key), "%Y-%m")
        year = dt.year + (dt.month // 12)
        month = (dt.month % 12) + 1
        return datetime(year, month, 15)
    except: return None

def calculate_commission_tier(total_gp, base_salary, is_team_lead=False):
    if is_team_lead: t1, t2, t3 = 4.5, 6.75, 11.25
    else: t1, t2, t3 = 9.0, 13.5, 22.5
    if total_gp < t1 * base_salary: return 0, 0
    elif total_gp < t2 * base_salary: return 1, 1
    elif total_gp < t3 * base_salary: return 2, 2
    else: return 3, 3

def calculate_single_deal_commission(candidate_salary, multiplier):
    if multiplier == 0: return 0
    base_comm = 0
    if candidate_salary < 20000: base_comm = 1000
    elif candidate_salary < 30000: base_comm = candidate_salary * 0.05
    elif candidate_salary < 50000: base_comm = candidate_salary * 1.5 * 0.05
    else: base_comm = candidate_salary * 2.0 * 0.05
    return base_comm * multiplier

def calculate_consultant_performance(all_sales_df, consultant_name, base_salary, is_team_lead=False):
    target = base_salary * (4.5 if is_team_lead else 9.0)
    c_sales = all_sales_df[all_sales_df['Consultant'] == consultant_name].copy()
    
    if c_sales.empty:
        return {"Booked GP": 0, "Paid GP": 0, "Level": 0, "Est. Commission": 0, "Target Achieved": 0}

    c_sales['Final Comm'] = 0.0
    c_sales['Commission Day Obj'] = pd.NaT

    booked_gp = c_sales['GP'].sum()
    paid_gp = 0; total_comm = 0; current_level = 0
    
    paid_sales = c_sales[c_sales['Status'] == 'Paid'].copy()

    if not paid_sales.empty:
        if 'Payment Date Obj' not in paid_sales.columns:
             paid_sales['Payment Date Obj'] = pd.to_datetime(paid_sales['Payment Date'], errors='coerce')
        paid_sales = paid_sales.dropna(subset=['Payment Date Obj']).sort_values(by='Payment Date Obj')
        paid_sales['Pay_Month_Key'] = paid_sales['Payment Date Obj'].dt.to_period('M')
        unique_months = sorted(paid_sales['Pay_Month_Key'].unique())
        running_paid_gp = 0; pending_indices = []

        for month_key in unique_months:
            month_deals = paid_sales[paid_sales['Pay_Month_Key'] == month_key]
            running_paid_gp += month_deals['GP'].sum()
            pending_indices.extend(month_deals.index.tolist())
            level, multiplier = calculate_commission_tier(running_paid_gp, base_salary, is_team_lead)
            if level > 0:
                payout_date = get_payout_date_from_month_key(str(month_key))
                for idx in pending_indices:
                    row = paid_sales.loc[idx]
                    paid_sales.at[idx, 'Final Comm'] = calculate_single_deal_commission(row['Candidate Salary'], multiplier) * row['Percentage']
                    paid_sales.at[idx, 'Commission Day Obj'] = payout_date
                pending_indices = []
            
        paid_gp = running_paid_gp
        current_level, _ = calculate_commission_tier(running_paid_gp, base_salary, is_team_lead)
        limit_date = datetime.now() + timedelta(days=20)
        for idx, row in paid_sales.iterrows():
            if pd.notnull(row['Commission Day Obj']) and row['Commission Day Obj'] <= limit_date:
                total_comm += row['Final Comm']

    if is_team_lead and not all_sales_df.empty:
        mask = (all_sales_df['Status'] == 'Paid') & (all_sales_df['Consultant'] != consultant_name) & (all_sales_df['Consultant'] != "Estela Peng")
        pot_overrides = all_sales_df[mask].copy()
        if 'Payment Date Obj' not in pot_overrides.columns: pot_overrides['Payment Date Obj'] = pd.to_datetime(pot_overrides['Payment Date'], errors='coerce')
        for _, row in pot_overrides.iterrows():
            if pd.isna(row['Payment Date Obj']): continue
            comm_pay_obj = datetime(row['Payment Date Obj'].year + (row['Payment Date Obj'].month // 12), (row['Payment Date Obj'].month % 12) + 1, 15)
            if comm_pay_obj <= (datetime.now() + timedelta(days=20)): total_comm += 1000 

    return {
        "Consultant": consultant_name, "Booked GP": booked_gp, "Paid GP": paid_gp,
        "Level": current_level, "Target Achieved": (paid_gp / target * 100) if target > 0 else 0,
        "Est. Commission": total_comm
    }

# --- 数据获取 ---
def connect_to_google():
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    if "gcp_service_account" in st.secrets:
        try: return gspread.authorize(ServiceAccountCredentials.from_json_keyfile_dict(dict(st.secrets["gcp_service_account"]), scope))
        except: return None
    return None

def get_quarter_info():
    today = datetime.now(); year = today.year; month = today.month
    quarter = (month - 1) // 3 + 1; start_month = (quarter - 1) * 3 + 1
    return [f"{year}{m:02d}" for m in range(start_month, start_month + 3)], quarter, start_month, start_month + 2, year

def fetch_role_from_personal_sheet(client, sheet_id):
    try:
        sheet = client.open_by_key(sheet_id)
        try: ws = sheet.worksheet('Credentials')
        except: ws = sheet.get_worksheet(0)
        header_vals = ws.range('A1:B1')
        title_text = header_vals[1].value.strip() if "title" in header_vals[0].value.strip().lower() else "Consultant"
        is_intern = "intern" in title_text.lower()
        is_lead = "team lead" in title_text.lower() or "manager" in title_text.lower()
        return ("Intern" if is_intern else "Full-Time"), is_lead, title_text.title()
    except: return "Full-Time", False, "Consultant"

def fetch_consultant_data(client, consultant_config, target_tab):
    sheet_id = consultant_config['id']
    target_key = consultant_config.get('keyword', 'Name')
    try:
        ws = client.open_by_key(sheet_id).worksheet(target_tab)
        rows = ws.get_all_values(); count = 0; details = []
        curr_co = "Unk"; curr_pos = "Unk"
        for row in rows:
            if not row: continue
            if row[0].strip() in ["Company", "Client", "Cliente", "公司"]: curr_co = row[1].strip() if len(row)>1 else "Unk"
            elif row[0].strip() in ["Position", "Role", "Posición", "职位"]: curr_pos = row[1].strip() if len(row)>1 else "Unk"
            elif row[0].strip() == target_key:
                cands = [x for x in row[1:] if x.strip()]; count += len(cands)
                for _ in cands: details.append({"Consultant": consultant_config['name'], "Company": curr_co, "Position": curr_pos, "Count": 1})
        return count, details
    except: return 0, []

def fetch_financial_df(client, start_m, end_m, year):
    try:
        sheet = client.open_by_key(SALES_SHEET_ID)
        try: ws = sheet.worksheet(SALES_TAB_NAME)
        except: ws = sheet.get_worksheet(0)
        rows = ws.get_all_values(); records = []
        col_cons=-1; col_onb=-1; col_pay=-1; col_sal=-1; col_pct=-1; found=False
        for row in rows:
            if not any(r.strip() for r in row): continue
            r_low = [str(x).strip().lower() for x in row]
            if not found:
                if any("linkeazi" in c for c in r_low) and any("onboarding" in c for c in r_low):
                    for i, c in enumerate(r_low):
                        if "linkeazi" in c: col_cons=i
                        if "onboarding" in c: col_onb=i
                        if "candidate" in c and "salary" in c: col_sal=i
                        if "payment" in c and "onboard" not in c: col_pay=i
                        if "percentage" in c or c=="%": col_pct=i
                    found=True; continue
            if found:
                if "POSITION" in " ".join(r_low).upper() and "PLACED" not in " ".join(r_low).upper(): break
                if len(row) <= max(col_cons, col_onb, col_sal): continue
                c_name = row[col_cons].strip(); onb_str = row[col_onb].strip()
                if not c_name or not onb_str: continue
                onb_date = None
                for fmt in ["%Y-%m-%d", "%d/%m/%Y", "%Y/%m/%d", "%m/%d/%Y"]:
                    try: onb_date = datetime.strptime(onb_str, fmt); break
                    except: pass
                if not onb_date or not (onb_date.year==year and start_m<=onb_date.month<=end_m): continue
                
                matched = "Unknown"
                for conf in TEAM_CONFIG_TEMPLATE:
                    if normalize_text(conf['name']) in normalize_text(c_name): matched = conf['name']; break
                if matched == "Unknown": continue

                sal_raw = str(row[col_sal]).replace(',','').replace('$','').replace('MXN','').strip()
                try: sal = float(sal_raw)
                except: sal = 0
                pct = 1.0
                if col_pct!=-1 and len(row)>col_pct:
                    try: 
                        p_f = float(str(row[col_pct]).replace('%','').strip())
                        pct = p_f/100.0 if p_f>1.0 else p_f
                    except: pass
                
                pay_str = ""; status = "Pending"
                if col_pay!=-1 and len(row)>col_pay:
                    pay_str = row[col_pay].strip()
                    if len(pay_str)>5: status = "Paid"
                
                records.append({
                    "Consultant": matched, "GP": sal*(1.0 if sal<20000 else 1.5)*pct, 
                    "Candidate Salary": sal, "Percentage": pct, "Payment Date": pay_str, "Status": status
                })
        return pd.DataFrame(records)
    except: return pd.DataFrame()


# --- 🖥️ UI RENDER ---

def render_bar(current, goal, css_class, label, height_class="pit-h-std", is_white_label=False):
    pct = (current / goal * 100) if goal > 0 else 0
    display_pct = min(pct, 100)
    
    icon = ""
    if pct >= 100: icon = "🌟"
    
    # 根据背景决定标签颜色
    lbl_class = "sub-label" if is_white_label else "card-label"

    st.markdown(f"""
    <div style="margin-bottom: 8px;">
        <div class="{lbl_class}">{label} ({int(current)}/{int(goal)})</div>
        <div class="pit-container {height_class}">
            <div class="{css_class}" style="width: {display_pct}%;">
                <div class="cat-icon" style="top: 5px;">{icon}</div>
            </div>
        </div>
    </div>
    """, unsafe_allow_html=True)

def render_player_card(conf, rec_count, fin_sum, idx):
    name = conf['name']; role = conf.get('role', 'Full-Time')
    is_intern = (role == 'Intern'); is_lead = conf.get('is_team_lead', False)
    
    # 🎯 Calculate Individual Progress for Visuals (Reduce Stress)
    # We divide the Team Goal by 4 to show individual contribution bar, but Logic remains Team-based
    # This prevents the bar from looking empty (e.g. 10/342)
    VISUAL_TARGET = QUARTERLY_GOAL / 4
    
    rec_pct_team = (rec_count / QUARTERLY_GOAL) * 100
    fin_pct = fin_sum.get("Target Achieved", 0.0)
    comm = fin_sum.get("Est. Commission", 0.0)
    
    # Pass Logic
    passed = False
    if is_intern:
        # Intern: Contribution check (Logic: did they pull their weight? approx 100% of individual share)
        # Using Team Goal / 4 as the 'Pass' mark for visual feedback
        if rec_count >= VISUAL_TARGET: passed = True
    else:
        # Full time: Either sent enough CVs OR hit financial target
        if rec_count >= VISUAL_TARGET or fin_pct >= 100: passed = True

    status_badge = '<span class="badge-pass">LEVEL UP! 🚀</span>' if passed else '<span class="badge-load">IN PROGRESS... 🐢</span>'
    bd_cls = f"bd-{(idx%4)+1}"
    crown = "👑" if is_lead else ""

    st.markdown(f"""
    <div class="player-card {bd_cls}">
        <div class="player-header">
            <div><span class="p-name">{name} {crown}</span><br><span class="p-role">{conf.get('title_display')}</span></div>
            {status_html(passed)}
        </div>
    """, unsafe_allow_html=True)
    
    # 1. Recruitment (Blue)
    render_bar(rec_count, VISUAL_TARGET, "fill-blue", "CVs SENT (Q4)", "pit-h-std", False)
    
    # 2. Financial (Green)
    if not is_intern:
        render_bar(fin_pct, 100, "fill-green", "GP TARGET", "pit-h-std", False)
    else:
        st.markdown('<div class="card-label" style="color:#b2bec3;">GP TARGET: N/A (INTERN)</div>', unsafe_allow_html=True)

    # 3. Loot Box
    if comm > 0:
        st.markdown(f'<div class="loot-box-unlocked">💰 UNLOCKED: ${comm:,.0f}</div>', unsafe_allow_html=True)
    else:
        st.markdown(f'<div class="loot-box-locked">🔒 LOCKED</div>', unsafe_allow_html=True)
    
    st.markdown("</div>", unsafe_allow_html=True)

def status_html(passed):
    if passed: return '<span class="badge-pass">LEVEL UP! 🚀</span>'
    return '<span class="badge-load">LOADING... ⏳</span>'

# --- MAIN ---
def main():
    q_tabs, q_num, sm, em, yr = get_quarter_info()
    m_tab = datetime.now().strftime("%Y%m")

    st.title("👾 FILL THE PIT 👾")
    c1,c2,c3 = st.columns([1,3,1])
    with c2: 
        if st.button("🕹️ INSERT COIN (START)"):
            st.session_state['run'] = True

    if st.session_state.get('run'):
        client = connect_to_google()
        if not client: st.error("GAME OVER: CONNECTION ERROR"); return
        
        # Load Config
        active_config = []
        for c in TEAM_CONFIG_TEMPLATE:
            nc = c.copy()
            r, l, t = fetch_role_from_personal_sheet(client, c['id'])
            nc.update({'role':r, 'is_team_lead':l, 'title_display':t})
            active_config.append(nc)
            
        # Fetch Data
        sales_df = fetch_financial_df(client, sm, em, yr)
        m_res = []; q_res = []; fin_sums = {}; all_dets = []
        
        with st.spinner("💾 LOADING SAVE DATA..."):
            for c in active_config:
                fin_sums[c['name']] = calculate_consultant_performance(sales_df, c['name'], c['base_salary'], c.get('is_team_lead'))
            
            for c in active_config:
                mc, md = fetch_consultant_data(client, c, m_tab)
                all_month_details.extend(md)
                qc = 0
                for qt in q_tabs:
                    if qt == m_tab: qc += mc
                    else: qc += fetch_consultant_data(client, c, qt)[0]
                m_res.append({'name':c['name'], 'count':mc})
                q_res.append({'name':c['name'], 'count':qc})

        # --- BOSS BARS ---
        m_total = sum([x['count'] for x in m_res])
        q_total = sum([x['count'] for x in q_res])
        
        # Monthly Bar (Medium, Gold)
        st.markdown(f'<div class="header-box" style="border-color: #f39c12;">🏆 TEAM MONTHLY GOAL ({m_tab})</div>', unsafe_allow_html=True)
        render_bar(m_total, MONTHLY_GOAL, "fill-gold", "TEAM PROGRESS", "pit-h-med", True)
        
        st.write("") # Spacer

        # Quarterly Bar (Big Boss, Rainbow) - 季度的简历统计数据 (The BIG ONE)
        st.markdown(f'<div class="header-box" style="border-color: #ff6b6b;">🔥 TEAM SEASON GOAL (Q{q_num})</div>', unsafe_allow_html=True)
        render_bar(q_total, QUARTERLY_GOAL, "fill-rainbow", "TOTAL SEASON CVs", "pit-h-big", True)

        # --- PLAYER SELECT ---
        st.markdown("<br><br>", unsafe_allow_html=True)
        cols = st.columns(2) + st.columns(2)
        
        for i, conf in enumerate(active_config):
            c_name = conf['name']
            qc = next((x['count'] for x in q_res if x['name']==c_name), 0)
            with cols[i]:
                render_player_card(conf, qc, fin_sums.get(c_name,{}), i)

        # --- LOGS ---
        if all_month_details:
            st.markdown("---")
            with st.expander(f"📜 MISSION LOGS ({m_tab})", expanded=False):
                df = pd.DataFrame(all_month_details)
                tabs = st.tabs([c['name'] for c in active_config])
                for i, t in enumerate(tabs):
                    with t:
                        sub = df[df['Consultant']==active_config[i]['name']]
                        if not sub.empty:
                            agg = sub.groupby(['Company','Position'])['Count'].sum().reset_index().sort_values('Count', ascending=False)
                            st.dataframe(agg, use_container_width=True, hide_index=True)
                        else: st.info("NO DATA")

if __name__ == "__main__":
    main()
