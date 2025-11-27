import streamlit as st
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import pandas as pd
import os
import time
import json
from datetime import datetime

# ==========================================
# 🔧 TEAM CONFIGURATION
# ==========================================
TEAM_CONFIG = [
    {
        "name": "Raul Solis",
        "id": "1vQuN-iNBRUug5J6gBMX-52jp6oogbA77SaeAf9j_zYs",
        "keyword": "Name"
    },
    {
        "name": "Estela Peng",
        "id": "1sUkffAXzWnpzhhmklqBuwtoQylpR1U18zqBQ-lsp7Z4",
        "keyword": "姓名" 
    },
    {
        "name": "Ana Cruz",
        "id": "1VMVw5YCV12eI8I-VQSXEKg86J2IVZJEgjPJT7ggAFD0",
        "keyword": "Name"
    },
    {
        "name": "Karina Albarran",
        "id": "1zc4ghvfjIxH0eJ2aXfopOWHqiyTDlD8yFNjBzpH07D8",
        "keyword": "Name"
    },
]

# 🎯 目标设置
MONTHLY_GOAL = 114
QUARTERLY_GOAL = 342  # 114 * 3
# ==========================================

st.set_page_config(page_title="Team Mission", page_icon="🐱", layout="wide")

# --- 🎨 CSS STYLING ---
st.markdown("""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Press+Start+2P&display=swap');

    /* Global */
    html, body, [class*="css"] {
        font-family: 'Press Start 2P', monospace;
        background-color: #111111;
        color: #FFFFFF;
    }
    
    /* Title */
    h1 {
        text-shadow: 4px 4px #000000;
        color: #FFD700 !important;
        text-align: center;
        font-size: 2.5em !important;
        margin-bottom: 20px;
    }
    h2 {
        text-align: center;
        color: #00FFFF !important;
        font-size: 1.5em !important;
        margin-top: 40px;
    }

    /* CENTERED BUTTON */
    .stButton {
        display: flex;
        justify-content: center;
        width: 100%;
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

    /* THE PITS (Progress Bars) */
    .pit-container {
        background-color: #222;
        border: 4px solid #fff;
        height: 60px;
        width: 100%;
        position: relative;
        margin-top: 10px;
        margin-bottom: 30px;
        box-shadow: 0 0 15px rgba(0,0,0,0.8);
    }
    
    .pit-fill-month {
        background-color: #8B4513; /* Brown for Month */
        height: 100%;
        display: flex;
        align-items: center; 
        justify-content: flex-end; 
    }

    .pit-fill-season {
        background-color: #0000FF; /* Blue for Season */
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
        background-color: #222;
        border: 2px solid #555;
        padding: 10px;
        text-align: center;
        margin-bottom: 10px;
    }
    .stat-val {
        color: #00FF41;
        font-size: 1.2em;
        margin-top: 5px;
    }
    .stat-name {
        color: #FFF;
        font-size: 0.6em;
        text-transform: uppercase;
    }

    /* MVP Card */
    .mvp-card {
        background-color: #333; 
        padding: 15px; 
        border: 4px solid #FFD700; 
        text-align: center;
        margin-top: 20px;
        box-shadow: 0 0 20px rgba(255, 215, 0, 0.3);
    }
    
    .section-label {
        font-size: 0.8em; 
        color: #888; 
        text-align: center; 
        margin-bottom: 5px;
    }
    </style>
    """, unsafe_allow_html=True)

# --- HELPER: GET QUARTER MONTHS ---
def get_quarter_tabs():
    """返回本季度包含的3个月份Tab名字，例如 ['202510', '202511', '202512']"""
    today = datetime.now()
    year = today.year
    month = today.month
    
    # 计算当前季度 (1-4)
    quarter = (month - 1) // 3 + 1
    
    # 该季度的第一个月
    start_month = (quarter - 1) * 3 + 1
    
    tabs = []
    for m in range(start_month, start_month + 3):
        # 格式化为 YYYYMM
        tabs.append(f"{year}{m:02d}")
        
    return tabs, quarter

# --- GOOGLE CONNECTION ---
def connect_to_google():
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    if "gcp_service_account" in st.secrets:
        try:
            creds_dict = dict(st.secrets["gcp_service_account"])
            creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
            return gspread.authorize(creds)
        except Exception: return None
    else:
        current_dir = os.path.dirname(os.path.abspath(__file__))
        json_path = os.path.join(current_dir, 'credentials.json')
        if os.path.exists(json_path):
            try:
                creds = ServiceAccountCredentials.from_json_keyfile_name(json_path, scope)
                return gspread.authorize(creds)
            except Exception: return None
        else: return None

# --- FETCH DATA ---
def fetch_consultant_data(client, consultant_config, target_tab):
    sheet_id = consultant_config['id']
    target_key = consultant_config.get('keyword', 'Name')

    try:
        sheet = client.open_by_key(sheet_id)
        try:
            worksheet = sheet.worksheet(target_tab)
        except gspread.exceptions.WorksheetNotFound:
            return 0 # Tab not found = 0 CVs
            
        rows = worksheet.get_all_values()
        count = 0
        for row in rows:
            if not row: continue
            cleaned_row = [cell.strip() for cell in row]
            if target_key in cleaned_row:
                key_index = cleaned_row.index(target_key)
                candidates = [x for x in row[key_index + 1:] if x.strip()]
                count += len(candidates)
        return count
    except Exception:
        return 0

# --- RENDER PIT ---
def render_pit(placeholder, current_total, goal, color_class, label):
    percent = (current_total / goal) * 100
    if percent > 100: percent = 100
    
    cats = "🐈" 
    if percent > 30: cats = "🐈🐈"
    if percent > 60: cats = "🐈🐈🐈"
    if percent >= 100: cats = "😻🎉"

    html = f"""
    <div class="section-label">{label}: {int(current_total)} / {goal}</div>
    <div class="pit-container">
        <div class="{color_class}" style="width: {percent}%;">
            <div class="cat-squad">{cats}</div>
        </div>
    </div>
    """
    placeholder.markdown(html, unsafe_allow_html=True)

# --- MAIN APP ---
def main():
    # 1. 计算时间
    current_month_tab = datetime.now().strftime("%Y%m")
    quarter_tabs, quarter_num = get_quarter_tabs()
    
    st.title("🔥 TEAM MISSION 🔥")
    
    col1, col2, col3 = st.columns([1, 3, 1])
    with col2:
        start_btn = st.button(f"🚩 START MISSION")

    if start_btn:
        client = connect_to_google()
        if not client:
            st.error("CONNECTION ERROR")
            return

        # ==========================================
        # 📡 PHASE 1: DATA SCANNING
        # ==========================================
        monthly_results = []
        quarterly_total_count = 0
        
        with st.spinner(f"🛰️ SCANNING MONTH & Q{quarter_num} DATA..."):
            
            for consultant in TEAM_CONFIG:
                # 1. Fetch Month Data
                m_count = fetch_consultant_data(client, consultant, current_month_tab)
                
                # 2. Fetch Quarter Data (Sum of 3 months)
                q_count = 0
                for q_tab in quarter_tabs:
                    # 如果是当前月，直接复用刚才取到的数据，省一次API请求
                    if q_tab == current_month_tab:
                        q_count += m_count
                    else:
                        q_count += fetch_consultant_data(client, consultant, q_tab)
                
                monthly_results.append({
                    "name": consultant['name'], 
                    "count": m_count
                })
                quarterly_total_count += q_count

        time.sleep(0.5)

        # ==========================================
        # 🎬 PHASE 2: ANIMATION
        # ==========================================
        
        # --- SECTION 1: MONTHLY ---
        st.markdown("## MONTHLY GOAL")
        pit_month_ph = st.empty()
        stats_month_ph = st.empty()
        mvp_ph = st.empty()
        
        # --- SECTION 2: QUARTERLY ---
        st.markdown(f"## SEASON CAMPAIGN (Q{quarter_num})")
        pit_quarter_ph = st.empty()

        monthly_total = sum([r['count'] for r in monthly_results])
        
        # Animation
        steps = 25
        for step in range(steps + 1):
            # Animate Month
            curr_m = (monthly_total / steps) * step
            render_pit(pit_month_ph, curr_m, MONTHLY_GOAL, "pit-fill-month", f"TAB {current_month_tab}")
            
            # Animate Quarter
            curr_q = (quarterly_total_count / steps) * step
            render_pit(pit_quarter_ph, curr_q, QUARTERLY_GOAL, "pit-fill-season", "QUARTER TOTAL")
            
            # Show stats at end
            if step == steps:
                cols = stats_month_ph.columns(len(monthly_results))
                for idx, res in enumerate(monthly_results):
                    with cols[idx]:
                        st.markdown(f"""
                        <div class="stat-card">
                            <div class="stat-name">{res['name']}</div>
                            <div class="stat-val">{res['count']}</div>
                        </div>
                        """, unsafe_allow_html=True)
            
            time.sleep(0.04)

        # ==========================================
        # 🏆 PHASE 3: MVP & RESULTS
        # ==========================================
        df = pd.DataFrame(monthly_results)
        if not df.empty and monthly_total > 0:
            df_sorted = df.sort_values(by="count", ascending=False)
            mvp = df_sorted.iloc[0]
            
            mvp_ph.markdown(f"""
            <div class="mvp-card">
                <h3 style="color: #FFD700; margin:0;">🏆 MONTHLY MVP 🏆</h3>
                <h2 style="color: white; margin: 10px 0;">{mvp['name']}</h2>
                <h1 style="color: #00FF41; margin:0;">{mvp['count']}</h1>
            </div>
            """, unsafe_allow_html=True)

        # Celebrations
        if monthly_total >= MONTHLY_GOAL:
            st.balloons()
            st.success("MONTHLY GOAL ACHIEVED!")
        
        if quarterly_total_count >= QUARTERLY_GOAL:
            st.balloons()
            st.markdown("""
            <div style="text-align: center; border: 4px solid #00FFFF; padding: 20px; margin-top: 20px;">
                <h1 style="color: #00FFFF !important;">🌊 SEASON VICTORY! 🌊</h1>
            </div>
            """, unsafe_allow_html=True)

if __name__ == "__main__":
    main()
