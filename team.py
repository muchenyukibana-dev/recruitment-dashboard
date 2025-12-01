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

# 🎯 目标设置 (以总简历数为准)
MONTHLY_GOAL = 114
QUARTERLY_GOAL = 342
# ==========================================

st.set_page_config(page_title="Fill The Pit", page_icon="🐱", layout="wide")

# --- 🎨 CSS STYLING ---
st.markdown("""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Press+Start+2P&display=swap');

    html, body, [class*="css"] {
        font-family: 'Press Start 2P', monospace;
        background-color: #FFA500;
        color: #FFFFFF;
    }
    
    h1 {
        text-shadow: 4px 4px #000000;
        color: #FFD700 !important;
        text-align: center;
        font-size: 3em !important;
        margin-bottom: 20px;
    }
    
    /* SIDEBAR */
    section[data-testid="stSidebar"] { background-color: #111111; border-right: 4px solid #FFFFFF; }
    section[data-testid="stSidebar"] .stRadio label {
        background-color: #333333; color: #FFFFFF !important; padding: 15px 20px;
        margin-bottom: 10px; border: 2px solid #FFFFFF; cursor: pointer;
        font-family: 'Press Start 2P', monospace; font-size: 0.8em; display: block;
    }
    section[data-testid="stSidebar"] .stRadio label:hover {
        background-color: #FF0055; border-color: #FFFF00; transform: translate(2px, -2px);
    }
    section[data-testid="stSidebar"] .stRadio label[data-checked="true"] {
        background-color: #FFD700; color: #000000 !important; border-color: #000000;
    }

    /* BUTTON */
    .stButton { display: flex; justify-content: center; width: 100%; margin-left: 180px; }
    .stButton>button {
        background-color: #FF0055; color: white; border: 4px solid #FFFFFF;
        font-family: 'Press Start 2P', monospace; font-size: 28px !important; 
        padding: 25px 50px !important; box-shadow: 8px 8px 0px #000000; width: 100%;
    }
    .stButton>button:hover { background-color: #FF5599; transform: scale(1.02); color: yellow; border-color: yellow; }

    /* PIT */
    .pit-container {
        background-color: #222; border: 4px solid #fff; height: 60px; width: 100%;
        position: relative; margin-top: 10px; margin-bottom: 30px; box-shadow: 6px 6px 0px #000000;
    }
    .pit-fill-month { background-color: #8B4513; height: 100%; display: flex; align-items: center; justify-content: flex-end; }
    .pit-fill-season { background-color: #0000FF; height: 100%; display: flex; align-items: center; justify-content: flex-end; }
    .cat-squad { position: absolute; right: -30px; top: -25px; font-size: 30px; z-index: 10; white-space: nowrap; }

    /* STATS CARDS (Updated for Pipeline) */
    .stat-card {
        background-color: #FFA500; border: 4px solid #FFFFFF; box-shadow: 6px 6px 0px #000000;
        padding: 10px; text-align: center; margin-bottom: 15px;
    }
    .stat-name { color: #FFF; font-size: 1.1em; font-weight: bold; text-transform: uppercase; margin-bottom: 10px; border-bottom: 2px solid white; padding-bottom: 5px;}
    
    .pipeline-row { display: flex; justify-content: space-between; font-size: 0.7em; color: #000; margin-bottom: 5px; }
    .pipeline-label { text-align: left; }
    .pipeline-val { text-align: right; font-weight: bold; }
    
    .hl-sent { color: #FFFFFF; }
    .hl-int { color: #00FF41; } /* Green */
    .hl-off { color: #FFFF00; } /* Yellow */

    /* MVP Card */
    .mvp-card {
        background-color: #333; padding: 15px; border: 4px solid #FFD700;
        box-shadow: 8px 8px 0px rgba(255, 15, 0, 0.3); text-align: center; margin-top: 20px;
    }
    
    .section-label { font-size: 0.8em; color: #888; text-align: center; margin-bottom: 5px; }
    .header-bordered {
        border: 4px solid #FFFFFF; box-shadow: 6px 6px 0px #000000; padding: 15px;
        text-align: center; margin-bottom: 20px; background-color: #222; color: #FFD700; font-size: 1.5em;
    }
    
    .dataframe { font-family: 'Press Start 2P', monospace !important; font-size: 0.8em !important; color: white !important; }
    
    .consultant-log-header {
        color: #000000; background-color: #FFFFFF; padding: 10px; font-size: 0.9em;
        border: 4px solid #000000; margin-top: 10px; margin-bottom: 10px; text-align: center;
        font-weight: bold; box-shadow: 4px 4px 0px #333;
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
    months = []
    today = datetime.now()
    for i in range(6):
        year = today.year
        month = today.month - i
        while month <= 0:
            month += 12
            year -= 1
        months.append(f"{year}{month:02d}")
    return months

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

# --- CORE LOGIC: FETCH DATA WITH STAGE ---
def fetch_consultant_data(client, consultant_config, target_tab):
    sheet_id = consultant_config['id']
    target_key = consultant_config.get('keyword', 'Name')
    
    # 识别不同语言的关键词
    COMPANY_KEYS = ["Company", "Client", "Cliente", "公司", "客户", "客户名称", "公司名称"]
    POSITION_KEYS = ["Position", "Role", "Posición", "职位", "岗位", "职位名称", "岗位名称"]
    STAGE_KEYS = ["Stage", "Status", "Step", "阶段", "状态", "进展"] # 🔥 新增 Stage 关键词

    try:
        sheet = client.open_by_key(sheet_id)
        try:
            worksheet = sheet.worksheet(target_tab)
        except gspread.exceptions.WorksheetNotFound:
            return 0, 0, 0, [] # Sent, Int, Off, Details
            
        rows = worksheet.get_all_values()
        
        # 数据容器
        details = []
        
        # 统计计数器
        count_sent = 0
        count_int = 0
        count_off = 0
        
        # --- 区块处理逻辑 ---
        # 我们需要先缓存当前区块的信息，等遇到下一个公司/结束时再结算
        current_block = {
            "company": "Unknown",
            "position": "Unknown",
            "candidates": {} # 结构: {col_index: {'name': 'xxx', 'stage': 'Sent'}}
        }

        def process_block(block):
            """结算并清空当前区块"""
            nonlocal count_sent, count_int, count_off
            processed_details = []
            
            # 遍历该区块找到的所有候选人
            for col_idx, cand_data in block['candidates'].items():
                name = cand_data.get('name')
                stage = cand_data.get('stage', 'Sent') # 默认为 Sent
                
                if not name: continue
                
                # 归一化 Stage 状态
                stage_lower = str(stage).lower().strip()
                
                final_stage = "Sent" # 默认展示状态
                
                # 判定逻辑 (包含关系)
                if "offer" in stage_lower:
                    count_off += 1
                    count_int += 1 # Offer通常也意味着通过了面试，也算面试量？(看需求，这里暂独立算)
                    count_sent += 1 # 肯定是投递过的
                    final_stage = "Offered"
                elif "interview" in stage_lower or "面试" in stage_lower:
                    count_int += 1
                    count_sent += 1
                    final_stage = "Interviewed"
                elif "closed" in stage_lower or "淘汰" in stage_lower:
                    count_sent += 1
                    final_stage = "Closed"
                else:
                    # 其他情况（包括空）都算 Sent
                    count_sent += 1
                    final_stage = "Sent"
                
                # 修正：如果面试数独立统计，上面逻辑会导致 Offer 不算 Interview。
                # 通常：Sent 是总量。Interviewed 是进面量。Offered 是Offer量。
                # 这里的逻辑是：如果是Offer，它肯定包含在Sent里。
                
                processed_details.append({
                    "Consultant": consultant_config['name'],
                    "Company": block['company'],
                    "Position": block['position'],
                    "Candidate": name,
                    "Stage": final_stage,
                    "Count": 1
                })
            return processed_details

        # 开始逐行扫描
        for row in rows:
            if not row: continue
            first_cell = row[0].strip()
            
            # 1. 发现新公司 -> 结算上一个区块，开启新区块
            if first_cell in COMPANY_KEYS:
                # 结算旧的
                details.extend(process_block(current_block))
                # 重置
                current_block = {
                    "company": row[1].strip() if len(row) > 1 else "Unknown",
                    "position": "Unknown",
                    "candidates": {}
                }
            
            # 2. 发现岗位 -> 更新当前区块
            elif first_cell in POSITION_KEYS:
                current_block['position'] = row[1].strip() if len(row) > 1 else "Unknown"
                
            # 3. 发现名字 -> 记录到当前区块的 candidates 字典 (key为列号)
            elif first_cell == target_key:
                for col_idx, cell_val in enumerate(row[1:], start=1):
                    if cell_val.strip():
                        if col_idx not in current_block['candidates']:
                            current_block['candidates'][col_idx] = {}
                        current_block['candidates'][col_idx]['name'] = cell_val.strip()
            
            # 4. 发现状态 -> 更新对应列号的状态
            elif first_cell in STAGE_KEYS:
                for col_idx, cell_val in enumerate(row[1:], start=1):
                    if cell_val.strip():
                        # 如果该列还没有候选人名字，先初始化(防止Stage行在Name行之前)
                        if col_idx not in current_block['candidates']:
                            current_block['candidates'][col_idx] = {}
                        current_block['candidates'][col_idx]['stage'] = cell_val.strip()

        # 循环结束，结算最后一个区块
        details.extend(process_block(current_block))
                    
        return count_sent, count_int, count_off, details
        
    except Exception as e:
        # print(f"Error: {e}") 
        return 0, 0, 0, []

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

def render_stats_card(name, sent, interview, offer, border_color="#FFFFFF"):
    """渲染带漏斗数据的卡片"""
    return f"""
    <div class="stat-card" style="border-color: {border_color};">
        <div class="stat-name">{name}</div>
        <div class="pipeline-row">
            <span class="pipeline-label hl-sent">SENT:</span>
            <span class="pipeline-val">{sent}</span>
        </div>
        <div class="pipeline-row">
            <span class="pipeline-label hl-int">INTERVIEW:</span>
            <span class="pipeline-val">{interview}</span>
        </div>
        <div class="pipeline-row">
            <span class="pipeline-label hl-off">OFFER:</span>
            <span class="pipeline-val">{offer}</span>
        </div>
    </div>
    """

# ==========================================
# 🎮 PAGE 1: THE GAME
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
        quarterly_total_sent = 0
        all_month_details = [] 
        
        with st.spinner(f"🛰️ SCANNING MONTH & Q{quarter_num} DATA..."):
            for consultant in TEAM_CONFIG:
                # 1. Fetch Month Data
                # returns: sent, int, off, details
                m_s, m_i, m_o, m_details = fetch_consultant_data(client, consultant, current_month_tab)
                all_month_details.extend(m_details)
                
                # 2. Fetch Quarter Data
                q_s_total, q_i_total, q_o_total = 0, 0, 0
                for q_tab in quarter_tabs:
                    if q_tab == current_month_tab:
                        q_s_total += m_s
                        q_i_total += m_i
                        q_o_total += m_o
                    else:
                        s, i, o, _ = fetch_consultant_data(client, consultant, q_tab)
                        q_s_total += s
                        q_i_total += i
                        q_o_total += o
                
                monthly_results.append({
                    "name": consultant['name'], "sent": m_s, "int": m_i, "off": m_o
                })
                quarterly_results.append({
                    "name": consultant['name'], "sent": q_s_total, "int": q_i_total, "off": q_o_total
                })
                quarterly_total_sent += q_s_total

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

        monthly_total_sent = sum([r['sent'] for r in monthly_results])
        
        steps = 25
        for step in range(steps + 1):
            curr_m = (monthly_total_sent / steps) * step
            render_pit(pit_month_ph, curr_m, MONTHLY_GOAL, "pit-fill-month", "MONTH TOTAL (SENT)")
            
            curr_q = (quarterly_total_sent / steps) * step
            render_pit(pit_quarter_ph, curr_q, QUARTERLY_GOAL, "pit-fill-season", "SEASON TOTAL (SENT)")
            
            if step == steps:
                # Render Monthly Cards
                cols_m = stats_month_ph.columns(len(monthly_results))
                for idx, res in enumerate(monthly_results):
                    with cols_m[idx]:
                        html = render_stats_card(res['name'], res['sent'], res['int'], res['off'], "#FFFFFF")
                        st.markdown(html, unsafe_allow_html=True)
                
                # Render Quarterly Cards
                cols_q = stats_quarter_ph.columns(len(quarterly_results))
                for idx, res in enumerate(quarterly_results):
                    with cols_q[idx]:
                        html = render_stats_card(res['name'], res['sent'], res['int'], res['off'], "#FFFF00")
                        st.markdown(html, unsafe_allow_html=True)
            time.sleep(0.04)

        # MVPS (Based on SENT count)
        df_m = pd.DataFrame(monthly_results)
        if not df_m.empty and monthly_total_sent > 0:
            mvp_m = df_m.sort_values(by="sent", ascending=False).iloc[0]
            mvp_month_ph.markdown(f"""<div class="mvp-card"><h3 style="color: #FFD700; margin:0; font-size: 1em;">🏆 MONTHLY MVP</h3><h2 style="color: white; margin: 10px 0;">{mvp_m['name']}</h2><h1 style="color: #000000; margin:0;">{mvp_m['sent']}</h1></div>""", unsafe_allow_html=True)

        df_q = pd.DataFrame(quarterly_results)
        if not df_q.empty and quarterly_total_sent > 0:
            mvp_q = df_q.sort_values(by="sent", ascending=False).iloc[0]
            mvp_season_ph.markdown(f"""<div class="mvp-card" style="border-color: #00FFFF;"><h3 style="color: #00FFFF; margin:0; font-size: 1em;">🌊 SEASON MVP</h3><h2 style="color: white; margin: 10px 0;">{mvp_q['name']}</h2><h1 style="color: #FFFFFF; margin:0;">{mvp_q['sent']}</h1></div>""", unsafe_allow_html=True)
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
                            # 聚合时加上 Stage 列
                            df_agg = df_c.groupby(['Company', 'Position', 'Stage'])['Count'].sum().reset_index()
                            df_agg = df_agg.sort_values(by='Count', ascending=False)
                            df_agg['Count'] = df_agg['Count'].astype(str)
                            st.dataframe(df_agg, use_container_width=True, hide_index=True, 
                                         column_config={
                                             "Company": st.column_config.TextColumn("COMPANY"), 
                                             "Position": st.column_config.TextColumn("ROLE"),
                                             "Stage": st.column_config.TextColumn("STATUS"),
                                             "Count": st.column_config.TextColumn("QTY")
                                         })
                        else:
                            st.info(f"NO DATA FOR {current_consultant}")
        elif monthly_total_sent == 0:
            st.markdown("---")
            st.info("NO DATA FOUND FOR THIS MONTH YET.")

# ==========================================
# 📜 PAGE 2: HISTORY
# ==========================================
def page_history():
    st.title("📜 HISTORY ARCHIVES")
    
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        load_btn = st.button("🔎 LOAD LAST 6 MONTHS")

    if load_btn:
        client = connect_to_google()
        if not client:
            st.error("CONNECTION ERROR")
            return

        months = get_last_6_months()
        summary_data = [] # 扁平化数据用于展示
        detailed_data_map = {month: [] for month in months}

        with st.spinner("⏳ RETRIEVING ARCHIVES..."):
            progress_bar = st.progress(0)
            for i, month in enumerate(months):
                for consultant in TEAM_CONFIG:
                    s, interview, off, details = fetch_consultant_data(client, consultant, month)
                    summary_data.append({
                        "MONTH": month,
                        "CONSULTANT": consultant['name'],
                        "SENT": s,
                        "INT": interview,
                        "OFF": off
                    })
                    detailed_data_map[month].extend(details)
                progress_bar.progress((i + 1) / len(months))
            progress_bar.empty()

        # 1. 总览表格 (改为明细行形式，更清晰)
        st.markdown(f'<div class="header-bordered" style="color: #00FF41; border-color: #00FF41;">📊 MONTHLY BREAKDOWN</div>', unsafe_allow_html=True)
        
        df_summary = pd.DataFrame(summary_data)
        # 透视表: Index=Month, Columns=Consultant, Values=Sent (或者显示Sent/Int/Off的组合字串? 先简单显示Sent)
        # 为了直观对比，直接显示所有人的 Sent 数量矩阵
        df_pivot = df_summary.pivot(index="MONTH", columns="CONSULTANT", values="SENT")
        st.dataframe(df_pivot, use_container_width=True)

        st.markdown("---")
        st.markdown(f'<div class="header-bordered" style="color: #FFFF00; border-color: #FFFF00;">📂 DETAILS BY MONTH</div>', unsafe_allow_html=True)

        for month in months:
            month_total = df_pivot.loc[month].sum() if month in df_pivot.index else 0
            with st.expander(f"📅 {month} | TOTAL SENT: {month_total}"):
                details = detailed_data_map[month]
                if details:
                    df_all = pd.DataFrame(details)
                    tab_names = [c['name'] for c in TEAM_CONFIG]
                    tabs = st.tabs(tab_names)
                    for idx, tab in enumerate(tabs):
                        with tab:
                            current_consultant = tab_names[idx]
                            df_c = df_all[df_all['Consultant'] == current_consultant]
                            if not df_c.empty:
                                # History里也显示Stage
                                df_agg = df_c.groupby(['Company', 'Position', 'Stage'])['Count'].sum().reset_index()
                                df_agg = df_agg.sort_values(by='Count', ascending=False)
                                df_agg['Count'] = df_agg['Count'].astype(str)
                                st.dataframe(df_agg, use_container_width=True, hide_index=True, 
                                             column_config={
                                                 "Company": st.column_config.TextColumn("COMPANY"), 
                                                 "Position": st.column_config.TextColumn("ROLE"), 
                                                 "Stage": st.column_config.TextColumn("STATUS"),
                                                 "Count": st.column_config.TextColumn("QTY")
                                             })
                            else:
                                st.caption("No data.")
                else:
                    st.caption("No data recorded.")

# ==========================================
# 🧭 MAIN
# ==========================================
def main():
    st.sidebar.title("🕹️ MENU")
    page = st.sidebar.radio("SELECT MODE", ["🎮 Current Mission", "📜 History Archives"])
    if page == "🎮 Current Mission":
        page_game()
    else:
        page_history()

if __name__ == "__main__":
    main()
