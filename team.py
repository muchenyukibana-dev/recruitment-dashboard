import streamlit as st
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import pandas as pd
import os
import time
from datetime import datetime, timedelta

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
QUARTERLY_GOAL = 342
# ==========================================

st.set_page_config(page_title="Fill The Pit", page_icon="🐱", layout="wide")

# --- 🎨 CSS STYLING (保持不变) ---
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
    
    /* Sidebar Styling */
    section[data-testid="stSidebar"] {
        background-color: #222;
        border-right: 4px solid #FFF;
    }

    /* CENTERED BUTTON WITH OFFSET */
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

    /* THE PITS (Progress Bars) */
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
    
    .cat-squad {
        position: absolute; right: -30px; top: -25px; font-size: 30px; z-index: 10; white-space: nowrap;
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
    
    .section-label { font-size: 0.8em; color: #888; text-align: center; margin-bottom: 5px; }

    /* HEADER BORDERED */
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
    
    /* Consultant Header in Logs */
    .consultant-log-header {
        color: #000000;
        background-color: #FFFFFF;
        padding: 10px;
        font-size: 0.9em;
        border: 4px solid #000000;
        margin-top: 10px;
        margin-bottom: 10px;
        text-align: center;
        font-weight: bold;
        box-shadow: 4px 4px 0px #333;
    }
    </style>
    """, unsafe_allow_html=True)

# --- HELPER FUNCTIONS ---
def get_quarter_tabs():
    today = datetime.now()
    year = today.year
    month = today.month
    quarter = (month - 1) // 3 + 1
    start_month = (quarter - 1) * 3 + 1
    tabs = []
    for m in range(start_month, start_month + 3):
        tabs.append(f"{year}{m:02d}")
    return tabs, quarter

def get_last_6_months():
    """生成过去6个月的Tab名字列表"""
    months = []
    today = datetime.now()
    for i in range(6):
        d = today - timedelta(days=30 * i)
        months.append(d.strftime("%Y%m"))
    return sorted(list(set(months)), reverse=True) # 去重并倒序

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

def fetch_consultant_data(client, consultant_config, target_tab):
    sheet_id = consultant_config['id']
    target_key = consultant_config.get('keyword', 'Name')
    COMPANY_KEYS = ["Company", "Client", "Cliente", "公司", "客户", "客户名称", "公司名称"]
    POSITION_KEYS = ["Position", "Role", "Posición", "职位", "岗位", "职位名称", "岗位名称"]

    try:
        sheet = client.open_by_key(sheet_id)
        try:
            worksheet = sheet.worksheet(target_tab)
        except gspread.exceptions.WorksheetNotFound:
            return 0, []
            
        rows = worksheet.get_all_values()
        count = 0
        details = [] 
        current_company = "Unknown"
        current_position = "Unknown"

        for row in rows:
            if not row: continue
            first_cell = row[0].strip()
            if first_cell in COMPANY_KEYS:
                current_company = row[1].strip() if len(row) > 1 else "Unknown"
            elif first_cell in POSITION_KEYS:
                current_position = row[1].strip() if len(row) > 1 else "Unknown"
            elif first_cell == target_key:
                candidates = [x for x in row[1:] if x.strip()]
                num = len(candidates)
                count += num
                if num > 0:
                    for _ in range(num):
                        details.append({
                            "Consultant": consultant_config['name'],
                            "Company": current_company,
                            "Position": current_position,
                            "Count": 1
                        })
        return count, details
    except Exception:
        return 0, []

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

# ==========================================
# 🎮 PAGE 1: THE GAME (CURRENT MONTH)
# ==========================================
def page_game():
    current_month_tab = datetime.now().strftime("%Y%m")
    quarter_tabs, quarter_num = get_quarter_tabs()
    
    st.title("🔥 FILL THE PIT 🔥")
    
    col1, col2, col3 = st.columns([1, 3, 1])
    with col2:
        start_btn = st.button(f"🚩 START THE GAME")

    if start_btn:
        client = connect_to_google()
        if not client:
            st.error("CONNECTION ERROR")
            return

        monthly_results = []
        quarterly_results = [] 
        quarterly_total_count = 0
        all_month_details = [] 
        
        with st.spinner(f"🛰️ SCANNING MONTH & Q{quarter_num} DATA..."):
            for consultant in TEAM_CONFIG:
                m_count, m_details = fetch_consultant_data(client, consultant, current_month_tab)
                all_month_details.extend(m_details)
                
                q_count = 0
                for q_tab in quarter_tabs:
                    if q_tab == current_month_tab:
                        q_count += m_count
                    else:
                        c, _ = fetch_consultant_data(client, consultant, q_tab)
                        q_count += c
                
                monthly_results.append({"name": consultant['name'], "count": m_count})
                quarterly_results.append({"name": consultant['name'], "count": q_count})
                quarterly_total_count += q_count

        time.sleep(0.5)

        # ANIMATION & RENDER
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
        
        steps = 25
        for step in range(steps + 1):
            curr_m = (monthly_total / steps) * step
            render_pit(pit_month_ph, curr_m, MONTHLY_GOAL, "pit-fill-month", "MONTH TOTAL")
            
            curr_q = (quarterly_total_count / steps) * step
            render_pit(pit_quarter_ph, curr_q, QUARTERLY_GOAL, "pit-fill-season", "SEASON TOTAL")
            
            if step == steps:
                cols_m = stats_month_ph.columns(len(monthly_results))
                for idx, res in enumerate(monthly_results):
                    with cols_m[idx]:
                        st.markdown(f"""<div class="stat-card"><div class="stat-name">{res['name']}</div><div class="stat-val">{res['count']}</div></div>""", unsafe_allow_html=True)
                
                cols_q = stats_quarter_ph.columns(len(quarterly_results))
                for idx, res in enumerate(quarterly_results):
                    with cols_q[idx]:
                        st.markdown(f"""<div class="stat-card" style="border-color: #FFFF00;"><div class="stat-name">{res['name']}</div><div class="stat-val" style="color: #000000;">{res['count']}</div></div>""", unsafe_allow_html=True)
            time.sleep(0.04)

        # MVPS
        df_m = pd.DataFrame(monthly_results)
        if not df_m.empty and monthly_total > 0:
            mvp_m = df_m.sort_values(by="count", ascending=False).iloc[0]
            mvp_month_ph.markdown(f"""<div class="mvp-card"><h3 style="color: #FFD700; margin:0; font-size: 1em;">🏆 MONTHLY MVP</h3><h2 style="color: white; margin: 10px 0;">{mvp_m['name']}</h2><h1 style="color: #000000; margin:0;">{mvp_m['count']}</h1></div>""", unsafe_allow_html=True)

        df_q = pd.DataFrame(quarterly_results)
        if not df_q.empty and quarterly_total_count > 0:
            mvp_q = df_q.sort_values(by="count", ascending=False).iloc[0]
            mvp_season_ph.markdown(f"""<div class="mvp-card" style="border-color: #00FFFF;"><h3 style="color: #00FFFF; margin:0; font-size: 1em;">🌊 SEASON MVP</h3><h2 style="color: white; margin: 10px 0;">{mvp_q['name']}</h2><h1 style="color: #FFFFFF; margin:0;">{mvp_q['count']}</h1></div>""", unsafe_allow_html=True)
            st.balloons()

        # MISSION LOGS
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
                        else:
                            st.info(f"NO DATA FOR {current_consultant}")
        elif monthly_total == 0:
            st.markdown("---")
            st.info("NO DATA FOUND FOR THIS MONTH YET.")

# ==========================================
# 📜 PAGE 2: HISTORY (NEW!)
# ==========================================
def page_history():
    st.title("📜 HISTORY LOGS")
    st.markdown("Analyze past performance and mission details.")

    client = connect_to_google()
    if not client:
        st.error("CONNECTION ERROR")
        return

    # 1. Select Month
    past_months = get_last_6_months()
    selected_month = st.selectbox("📅 SELECT MONTH TO ANALYZE", past_months)
    
    if st.button("🔎 FETCH HISTORY DATA"):
        with st.spinner(f"RETRIEVING ARCHIVES FROM {selected_month}..."):
            
            # 扫描该月所有顾问的数据
            history_results = []
            history_details = []
            
            for consultant in TEAM_CONFIG:
                c, d = fetch_consultant_data(client, consultant, selected_month)
                history_results.append({"name": consultant['name'], "count": c})
                history_details.extend(d)
                
            # 1. 概览数据
            total = sum([r['count'] for r in history_results])
            st.markdown(f'<div class="header-bordered">TOTAL CVS: {total}</div>', unsafe_allow_html=True)
            
            if total > 0:
                # 2. 图表展示
                df_res = pd.DataFrame(history_results)
                st.bar_chart(df_res.set_index("name")["count"], color="#00FF41")
                
                # 3. 详细 Mission Logs
                st.markdown("### 📝 DETAILED LOGS")
                if history_details:
                    df_all = pd.DataFrame(history_details)
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
                                st.dataframe(df_agg, use_container_width=True, hide_index=True, 
                                             column_config={"Company": st.column_config.TextColumn("COMPANY"), 
                                                            "Position": st.column_config.TextColumn("ROLE"), 
                                                            "Count": st.column_config.TextColumn("CVs")})
                            else:
                                st.info("No data recorded.")
            else:
                st.warning(f"No data found for {selected_month}. Did you create the tab?")

# ==========================================
# 🧭 MAIN NAVIGATION
# ==========================================
def main():
    # 侧边栏导航
    st.sidebar.title("🕹️ MENU")
    page = st.sidebar.radio("Go to", ["🎮 Current Mission", "📜 History Archives"])
    
    if page == "🎮 Current Mission":
        page_game()
    else:
        page_history()

if __name__ == "__main__":
    main()
