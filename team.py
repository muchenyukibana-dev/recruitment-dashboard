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

# ==========================================

st.set_page_config(page_title="Management Dashboard", page_icon="📊", layout="wide")

# --- 🎨 CSS STYLING (Professional Dashboard) ---
st.markdown("""
    <style>
    /* Global Settings */
    .stApp {
        background-color: #0E1117; /* Dark Professional Background */
        color: #FFFFFF;
    }
    
    /* Titles */
    h1 {
        text-align: center;
        color: #FFFFFF;
        font-family: 'Helvetica Neue', sans-serif;
        font-weight: 700;
        margin-bottom: 30px;
    }
    h3 {
        color: #E0E0E0;
        border-bottom: 1px solid #444;
        padding-bottom: 10px;
    }

    /* LOAD BUTTON */
    .stButton {
        display: flex;
        justify-content: center;
    }
    .stButton>button {
        background-color: #2563EB; /* Professional Blue */
        color: white;
        border-radius: 5px;
        font-size: 20px;
        padding: 15px 40px;
        border: none;
        font-weight: bold;
        transition: background 0.3s;
    }
    .stButton>button:hover {
        background-color: #1D4ED8;
    }

    /* SUMMARY CARDS (KPIs) */
    div[data-testid="metric-container"] {
        background-color: #1F2937;
        padding: 15px;
        border-radius: 8px;
        border: 1px solid #374151;
        text-align: center;
    }
    
    /* TABLES */
    .dataframe {
        font-size: 14px !important;
    }
    
    /* CUSTOM LABELS FOR STATUS */
    .status-sent { color: #A0AEC0; font-weight: bold; }
    .status-int { color: #34D399; font-weight: bold; } /* Green */
    .status-off { color: #FBBF24; font-weight: bold; } /* Gold */
    
    </style>
    """, unsafe_allow_html=True)

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

# --- HELPER: Generate Month List ---
def get_target_months():
    """获取过去6个月的列表，用于生成历史报表"""
    months = []
    today = datetime.now()
    for i in range(6):
        year = today.year
        month = today.month - i
        while month <= 0:
            month += 12
            year -= 1
        months.append(f"{year}{month:02d}")
    return months # e.g. ['202511', '202510'...]

# --- CORE LOGIC: FETCH DATA WITH STAGE & DETAILS ---
def fetch_consultant_data(client, consultant_config, target_tab):
    sheet_id = consultant_config['id']
    target_key = consultant_config.get('keyword', 'Name')
    
    COMPANY_KEYS = ["Company", "Client", "Cliente", "公司", "客户", "客户名称", "公司名称"]
    POSITION_KEYS = ["Position", "Role", "Posición", "职位", "岗位", "职位名称", "岗位名称"]
    STAGE_KEYS = ["Stage", "Status", "Step", "阶段", "状态", "进展"]

    try:
        sheet = client.open_by_key(sheet_id)
        try:
            worksheet = sheet.worksheet(target_tab)
        except gspread.exceptions.WorksheetNotFound:
            return 0, 0, 0, []
            
        rows = worksheet.get_all_values()
        details = []
        count_sent, count_int, count_off = 0, 0, 0
        
        current_block = {"company": "Unknown", "position": "Unknown", "candidates": {}}

        def process_block(block):
            nonlocal count_sent, count_int, count_off
            processed = []
            for _, cand_data in block['candidates'].items():
                name = cand_data.get('name')
                stage = str(cand_data.get('stage', 'Sent')).lower().strip()
                if not name: continue
                
                # 状态判定逻辑 (向下兼容)
                is_off = "offer" in stage
                is_int = "interview" in stage or "面试" in stage or is_off
                is_sent = True # 所有人默认都是Sent
                
                # 计数
                if is_off: count_off += 1
                if is_int: count_int += 1 # 包含Offer的也算面试
                count_sent += 1
                
                # 标记该候选人的最高状态，用于列表展示
                status_label = "Sent"
                if is_off: status_label = "Offered"
                elif is_int: status_label = "Interviewed"
                
                processed.append({
                    "Consultant": consultant_config['name'],
                    "Company": block['company'],
                    "Position": block['position'],
                    "Status": status_label,
                    "Count": 1
                })
            return processed

        for row in rows:
            if not row: continue
            first_cell = row[0].strip()
            
            if first_cell in COMPANY_KEYS:
                details.extend(process_block(current_block))
                current_block = {"company": row[1].strip() if len(row) > 1 else "Unknown", "position": "Unknown", "candidates": {}}
            elif first_cell in POSITION_KEYS:
                current_block['position'] = row[1].strip() if len(row) > 1 else "Unknown"
            elif first_cell == target_key:
                for col_idx, cell_val in enumerate(row[1:], start=1):
                    if cell_val.strip():
                        if col_idx not in current_block['candidates']: current_block['candidates'][col_idx] = {}
                        current_block['candidates'][col_idx]['name'] = cell_val.strip()
            elif first_cell in STAGE_KEYS:
                for col_idx, cell_val in enumerate(row[1:], start=1):
                    if cell_val.strip():
                        if col_idx not in current_block['candidates']: current_block['candidates'][col_idx] = {}
                        current_block['candidates'][col_idx]['stage'] = cell_val.strip()

        details.extend(process_block(current_block))
        return count_sent, count_int, count_off, details
        
    except Exception:
        return 0, 0, 0, []

# --- MAIN APP ---
def main():
    st.title("📊 MANAGEMENT DASHBOARD")
    st.markdown("<p style='text-align: center; color: #888;'>Monthly & Quarterly Recruitment Performance Analysis</p>", unsafe_allow_html=True)
    
    # Load Button
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        load_btn = st.button("🔄 LOAD HISTORY DATA")

    if load_btn:
        client = connect_to_google()
        if not client:
            st.error("Connection Error: Check API credentials.")
            return

        months = get_target_months() # 获取过去6个月
        
        # 数据存储结构
        summary_data = [] # 用于宏观统计表格
        detailed_data_map = {} # Key: Month, Value: List of details
        
        quarter_totals = {"Sent": 0, "Interviewed": 0, "Offered": 0}

        with st.spinner("Processing Consultant Data..."):
            progress_bar = st.progress(0)
            
            for i, month in enumerate(months):
                month_s, month_i, month_o = 0, 0, 0
                month_details = []
                
                for consultant in TEAM_CONFIG:
                    s, interview, off, details = fetch_consultant_data(client, consultant, month)
                    
                    # 累加月度总数
                    month_s += s
                    month_i += interview
                    month_o += off
                    
                    # 收集详情
                    if details:
                        month_details.extend(details)
                
                # 记录该月汇总
                summary_data.append({
                    "Month": month,
                    "SENT": month_s,
                    "INTERVIEWED": month_i,
                    "OFFERED": month_o
                })
                
                detailed_data_map[month] = month_details
                
                # 简单粗暴计算“展示的所有月份的总和”作为季度参考（或者你可以只算最近3个月）
                quarter_totals["Sent"] += month_s
                quarter_totals["Interviewed"] += month_i
                quarter_totals["Offered"] += month_o
                
                progress_bar.progress((i + 1) / len(months))
            
            progress_bar.empty()

        # ==========================================
        # 1. QUARTERLY / TOTAL SUMMARY (TOP SECTION)
        # ==========================================
        st.markdown("### 🏆 TOTAL SUMMARY (Loaded Months)")
        kpi1, kpi2, kpi3 = st.columns(3)
        kpi1.metric("TOTAL SENT", quarter_totals["Sent"])
        kpi2.metric("TOTAL INTERVIEWED", quarter_totals["Interviewed"])
        kpi3.metric("TOTAL OFFERED", quarter_totals["Offered"])
        
        st.divider()

        # ==========================================
        # 2. MONTHLY BREAKDOWN & DETAILS
        # ==========================================
        st.markdown("### 📅 MONTHLY BREAKDOWN")
        
        # 遍历月份显示数据
        for month_data in summary_data:
            m_name = month_data['Month']
            s_val = month_data['SENT']
            i_val = month_data['INTERVIEWED']
            o_val = month_data['OFFERED']
            
            # 如果该月没有任何数据，跳过不显示，或者显示灰色
            if s_val == 0:
                continue

            # 使用 Expander 作为主要容器
            with st.expander(f"{m_name} | Sent: {s_val} | Int: {i_val} | Off: {o_val}", expanded=False):
                
                # 获取该月的详细数据
                details = detailed_data_map.get(m_name, [])
                
                if details:
                    df = pd.DataFrame(details)
                    
                    # 创建 3 个标签页，分别展示 Sent / Int / Off 的具体岗位
                    tab_sent, tab_int, tab_off = st.tabs([
                        f"📄 SENT ({s_val})", 
                        f"👥 INTERVIEWED ({i_val})", 
                        f"🎉 OFFERED ({o_val})"
                    ])
                    
                    # --- Tab 1: SENT (Show All) ---
                    with tab_sent:
                        # 聚合：按顾问、公司、岗位统计
                        df_sent = df.groupby(['Consultant', 'Company', 'Position'])['Count'].sum().reset_index()
                        df_sent = df_sent.sort_values(by='Count', ascending=False)
                        st.dataframe(df_sent, use_container_width=True, hide_index=True)

                    # --- Tab 2: INTERVIEWED (Filter Status) ---
                    with tab_int:
                        # 筛选状态包含 Interviewed 或 Offered 的
                        df_i = df[df['Status'].isin(['Interviewed', 'Offered'])]
                        if not df_i.empty:
                            df_i_agg = df_i.groupby(['Consultant', 'Company', 'Position'])['Count'].sum().reset_index()
                            df_i_agg = df_i_agg.sort_values(by='Count', ascending=False)
                            st.dataframe(df_i_agg, use_container_width=True, hide_index=True)
                        else:
                            st.info("No interviews recorded.")

                    # --- Tab 3: OFFERED (Filter Status) ---
                    with tab_off:
                        # 筛选状态仅为 Offered
                        df_o = df[df['Status'] == 'Offered']
                        if not df_o.empty:
                            df_o_agg = df_o.groupby(['Consultant', 'Company', 'Position'])['Count'].sum().reset_index()
                            df_o_agg = df_o_agg.sort_values(by='Count', ascending=False)
                            st.dataframe(df_o_agg, use_container_width=True, hide_index=True)
                        else:
                            st.info("No offers recorded.")
                            
                else:
                    st.warning("Statistics found but no detailed logs available.")

if __name__ == "__main__":
    main()
