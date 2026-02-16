import streamlit as st
import streamlit.components.v1 as components
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

TEAM_CONFIG_TEMPLATE = [
    {"name": "Raul Solis", "id": "1vQuN-iNBRUug5J6gBMX-52jp6oogbA77SaeAf9j_zYs", "keyword": "Name", "base_salary": 11000},
    {"name": "Estela Peng", "id": "1sUkffAXzWnpzhhmklqBuwtoQylpR1U18zqBQ-lsp7Z4", "keyword": "姓名", "base_salary": 20800},
    {"name": "Ana Cruz", "id": "1VMVw5YCV12eI8I-VQSXEKg86J2IVZJEgjPJT7ggAFD0", "keyword": "Name", "base_salary": 13000},
    {"name": "Karina Albarran", "id": "1zc4ghvfjIxH0eJ2aXfopOWHqiyTDlD8yFNjBzpH07D8", "keyword": "Name", "base_salary": 15000},
]

QUARTERLY_INDIVIDUAL_GOAL = 87
MONTHLY_GOAL = 116
QUARTERLY_TEAM_GOAL = 348

# ==========================================

st.set_page_config(page_title="Fill The Pit", page_icon="🎮", layout="wide")

# --- 🎨 恢复原始 CSS 样式 ---
st.markdown("""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Press+Start+2P&display=swap');
    @import url('https://fonts.googleapis.com/css2?family=Fredoka+One&display=swap');

    .stApp {
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        font-family: 'Press Start 2P', monospace;
    }

    h1 {
        text-shadow: 4px 4px 0px #000000;
        color: #FFD700 !important;
        text-align: center;
        font-size: 3.5em !important;
        margin-bottom: 20px;
        -webkit-text-stroke: 2px #000;
    }

    /* 恢复原始按钮布局 */
    .stButton {
        display: flex;
        justify-content: center;
        width: 100%;
    }
    .stButton>button {
        background-color: #FF4757;
        color: white;
        border: 4px solid #000;
        border-radius: 15px;
        font-family: 'Press Start 2P', monospace;
        font-size: 24px !important; 
        padding: 20px 40px !important; 
        box-shadow: 0px 8px 0px #a71c2a;
        transition: all 0.1s;
        width: 100%; /* 填满列容器 */
    }
    .stButton>button:hover {
        transform: translateY(4px);
        box-shadow: 0px 4px 0px #a71c2a;
        background-color: #ff6b81;
    }

    /* --- PROGRESS BARS --- */
    .pit-container {
        background-color: #eee;
        border: 3px solid #000;
        border-radius: 12px;
        width: 100%;
        position: relative;
        margin-bottom: 12px;
        box-shadow: 4px 4px 0px rgba(0,0,0,0.2);
        overflow: hidden;
    }

    .pit-height-std { height: 25px; }
    .pit-height-boss { height: 60px; border-width: 4px; }

    @keyframes barberpole {
        from { background-position: 0 0; }
        to { background-position: 50px 50px; }
    }

    .money-fill { 
        background-image: linear-gradient(45deg, #2ed573 25%, #7bed9f 25%, #7bed9f 50%, #2ed573 50%, #2ed573 75%, #7bed9f 75%, #7bed9f 100%);
        background-size: 50px 50px;
        animation: barberpole 4s linear infinite;
        height: 100%; 
    }

    .cv-fill {
        background-image: linear-gradient(45deg, #ff9ff3 25%, #f368e0 25%, #f368e0 50%, #ff9ff3 50%, #ff9ff3 75%, #f368e0 75%, #f368e0 100%);
        background-size: 50px 50px;
        animation: barberpole 3s linear infinite;
        height: 100%;
    }

    .pit-fill-boss {
        background: linear-gradient(270deg, #ff6b6b, #feca57, #48dbfb, #ff9ff3, #54a0ff);
        background-size: 400% 400%;
        height: 100%;
    }

    /* --- PLAYER CARDS --- */
    .player-card {
        background-color: #FFFFFF;
        border: 4px solid #000;
        border-radius: 15px;
        padding: 20px;
        margin-bottom: 30px;
        box-shadow: 8px 8px 0px rgba(0,0,0,0.2);
    }
    .card-border-1 { border-bottom: 8px solid #ff6b6b; }
    .card-border-2 { border-bottom: 8px solid #feca57; }
    .card-border-3 { border-bottom: 8px solid #48dbfb; }
    .card-border-4 { border-bottom: 8px solid #ff9ff3; }

    .player-header {
        display: flex;
        justify-content: space-between;
        align-items: center;
        margin-bottom: 15px;
        border-bottom: 2px dashed #ddd;
        padding-bottom: 10px;
    }
    .player-name { font-size: 1.1em; font-weight: bold; color: #2d3436; }

    .status-badge-pass { background-color: #2ed573; color: white; padding: 8px 12px; border-radius: 20px; border: 2px solid #000; font-size: 0.6em; }
    .status-badge-loading { background-color: #feca57; color: #000; padding: 8px 12px; border-radius: 20px; border: 2px solid #000; font-size: 0.6em; }

    .sub-label {
        font-family: 'Fredoka One', sans-serif;
        font-size: 0.8em;
        color: #FFFFFF;
        margin-bottom: 5px;
        text-transform: uppercase;
        text-shadow: 1px 1px 0px #000;
    }

    .header-bordered {
        background-color: #FFFFFF;
        border: 4px solid #000;
        border-radius: 15px;
        box-shadow: 6px 6px 0px #000000;
        padding: 20px;
        text-align: center;
        margin-bottom: 25px;
    }
    .stat-card { background: white; border: 3px solid #000; border-radius: 10px; padding: 10px; text-align: center; }
    </style>
    """, unsafe_allow_html=True)

# ==========================================
# 🧮 逻辑函数
# ==========================================

def normalize_text(text):
    return ''.join(c for c in unicodedata.normalize('NFD', str(text)) if unicodedata.category(c) != 'Mn').lower()

def connect_to_google():
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    if "gcp_service_account" in st.secrets:
        try:
            return gspread.authorize(ServiceAccountCredentials.from_json_keyfile_dict(dict(st.secrets["gcp_service_account"]), scope))
        except: return None
    return None

def fetch_financial_df(client, start_m, end_m, year):
    try:
        sheet = client.open_by_key(SALES_SHEET_ID)
        ws = sheet.worksheet(SALES_TAB_NAME)
        rows = ws.get_all_values()
        col_cons, col_onboard, col_sal, col_pct = -1, -1, -1, -1
        found_header, records = False, []
        for row in rows:
            row_l = [str(x).strip().lower() for x in row]
            if not found_header:
                if "onboarding" in row_l and "linkeazi" in str(row_l):
                    for i, c in enumerate(row_l):
                        if "linkeazi" in c and "consultant" in c: col_cons = i
                        if "onboarding" in c and "date" in c: col_onboard = i
                        if "candidate" in c and "salary" in c: col_sal = i
                        if "percentage" in c or "pct" in c or c == "%": col_pct = i
                    found_header = True
                    continue
            if found_header:
                if len(row) <= max(col_cons, col_onboard): continue
                c_name = row[col_cons].strip()
                if not c_name: continue
                ob_str = row[col_onboard].strip()
                ob_date = None
                for fmt in ["%Y-%m-%d", "%d/%m/%Y", "%m/%d/%Y", "%Y/%m/%d"]:
                    try: ob_date = datetime.strptime(ob_str, fmt); break
                    except: pass
                if not ob_date or not (ob_date.year == year and start_m <= ob_date.month <= end_m): continue
                matched = "Unknown"; c_norm = normalize_text(c_name)
                for conf in TEAM_CONFIG_TEMPLATE:
                    if normalize_text(conf['name']) in c_norm or c_norm in normalize_text(conf['name']):
                        matched = conf['name']; break
                if matched == "Unknown": continue
                sal = float(str(row[col_sal]).replace(',','').replace('$','').strip() or 0)
                pct = 1.0
                if col_pct != -1:
                    p_val = str(row[col_pct]).replace('%','').strip()
                    try: pct = float(p_val)/100.0 if float(p_val)>1 else float(p_val)
                    except: pass
                gp = sal * (1.0 if sal < 20000 else 1.5) * pct
                records.append({"Consultant": matched, "GP": gp})
        return pd.DataFrame(records)
    except: return pd.DataFrame()

def fetch_cv_data(client, conf, tab):
    try:
        ws = client.open_by_key(conf['id']).worksheet(tab)
        rows = ws.get_all_values()
        count, details = 0, []
        curr_co, curr_pos = "Unknown", "Unknown"
        for row in rows:
            clean = [str(x).strip() for x in row]
            try:
                idx = clean.index(conf['keyword'])
                cands = [x for x in clean[idx+1:] if x]
                count += len(cands)
                for _ in range(len(cands)): details.append({"Consultant": conf['name'], "Company": curr_co, "Position": curr_pos, "Count": 1})
            except ValueError:
                if len(clean) > 0:
                    if clean[0] in ["Company", "Client", "公司名称"]: curr_co = clean[1] if len(clean)>1 else "Unknown"
                    elif clean[0] in ["Position", "Role", "职位"]: curr_pos = clean[1] if len(clean)>1 else "Unknown"
        return count, details
    except: return 0, []

def render_bar(current, goal, color_class, label_text, is_boss=False):
    pct = min((current / goal * 100), 100) if goal > 0 else 0
    height = "pit-height-boss" if is_boss else "pit-height-std"
    st.markdown(f"""
        <div class="sub-label">{label_text} ({int(current)}/{int(goal)})</div>
        <div class="pit-container {height}"><div class="{color_class}" style="width: {pct}%;"></div></div>
    """, unsafe_allow_html=True)

# --- MAIN APP ---
def main():
    today = datetime.now()
    q_num = (today.month - 1) // 3 + 1
    start_m = (q_num - 1) * 3 + 1
    q_tabs = [f"{today.year}{m:02d}" for m in range(start_m, start_m + 3)]
    curr_tab = today.strftime("%Y%m")

    st.title("👾 FILL THE PIT 👾")
    
    # 按钮居中布局
    col_l, col_btn, col_r = st.columns([1, 2, 1])
    with col_btn:
        start_btn = st.button("🚩 PRESS START")

    if start_btn:
        client = connect_to_google()
        if not client: st.error("Connection Error"); return
        
        with st.spinner("🛰️ SCANNING DATA..."):
            sales_df = fetch_financial_df(client, start_m, start_m+2, today.year)
            team_stats = []
            all_logs = []
            for conf in TEAM_CONFIG_TEMPLATE:
                m_c, m_d = fetch_cv_data(client, conf, curr_tab)
                all_logs.extend(m_d)
                q_c = m_c
                for t in q_tabs: 
                    if t != curr_tab:
                        c, _ = fetch_cv_data(client, conf, t); q_c += c
                booked_gp = sales_df[sales_df['Consultant'] == conf['name']]['GP'].sum() if not sales_df.empty else 0
                is_lead = "Estela" in conf['name'] or "Raul" in conf['name']
                gp_target = conf['base_salary'] * (4.5 if is_lead else 9.0)
                team_stats.append({
                    "conf": conf, "m_cv": m_c, "q_cv": q_c, "gp": booked_gp, "gp_target": gp_target,
                    "is_qualified": (q_c >= QUARTERLY_INDIVIDUAL_GOAL or booked_gp >= gp_target)
                })

        # --- BOSS BARS ---
        total_m_cv = sum(s['m_cv'] for s in team_stats)
        total_q_cv = sum(s['q_cv'] for s in team_stats)
        
        st.markdown(f'<div class="header-bordered">🏆 TEAM MONTHLY ({curr_tab})</div>', unsafe_allow_html=True)
        render_bar(total_m_cv, MONTHLY_GOAL, "pit-fill-boss", "MONTHLY TEAM CVs", True)
        
        st.markdown(f'<div class="header-bordered">🌊 TEAM QUARTERLY (Q{q_num})</div>', unsafe_allow_html=True)
        render_bar(total_q_cv, QUARTERLY_TEAM_GOAL, "pit-fill-boss", "QUARTERLY TEAM CVs", True)

        # --- PLAYER HUB ---
        st.markdown("<br>", unsafe_allow_html=True)
        row1_cols = st.columns(2)
        row2_cols = st.columns(2)
        all_cols = row1_cols + row2_cols
        
        for idx, s in enumerate(team_stats):
            with all_cols[idx]:
                border = f"card-border-{(idx%4)+1}"
                status = "GOAL MET! 🌟" if s['is_qualified'] else "HUNTING... 🚀"
                badge = "status-badge-pass" if s['is_qualified'] else "status-badge-loading"
                st.markdown(f"""
                <div class="player-card {border}">
                    <div class="player-header">
                        <div class="player-name">{s['conf']['name']}</div>
                        <div class="{badge}">{status}</div>
                    </div>
                """, unsafe_allow_html=True)
                render_bar(s['gp'], s['gp_target'], "money-fill", "GP TARGET (BOOKED)")
                render_bar(s['q_cv'], QUARTERLY_INDIVIDUAL_GOAL, "cv-fill", "QUARTERLY CVs")
                st.markdown("</div>", unsafe_allow_html=True)

        # --- LOGS ---
        if all_logs:
            with st.expander("📜 MISSION LOGS"):
                df = pd.DataFrame(all_logs)
                for conf in TEAM_CONFIG_TEMPLATE:
                    st.subheader(conf['name'])
                    df_c = df[df['Consultant'] == conf['name']]
                    if not df_c.empty:
                        st.dataframe(df_c.groupby(['Company', 'Position'])['Count'].sum().reset_index(), use_container_width=True, hide_index=True)

if __name__ == "__main__":
    main()
