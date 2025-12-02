import streamlit as st
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import pandas as pd
import os
import time
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

# ==========================================

st.set_page_config(page_title="Management Report", page_icon="📈", layout="wide")

# --- 🎨 CSS STYLING ---
st.markdown("""
    <style>
    .stApp { background-color: #FFFFFF; color: #000000; }
    h1, h2, h3, h4 { color: #333333 !important; font-family: 'Arial', sans-serif; }
    
    /* 按钮左对齐 */
    .stButton { display: flex; justify-content: flex-start; }
    .stButton>button {
        background-color: #0056b3; color: white; border: none; border-radius: 4px;
        padding: 10px 24px; font-weight: bold;
    }
    .stButton>button:hover { background-color: #004494; color: white; }

    .dataframe { font-size: 14px !important; font-family: 'Arial', sans-serif !important; border: 1px solid #ddd !important; }
    
    .streamlit-expanderHeader {
        background-color: #f8f9fa; color: #000; font-weight: bold; border: 1px solid #ddd; border-radius: 4px;
    }
    
    /* Metrics box */
    div[data-testid="metric-container"] {
        background-color: #f1f3f5; border: 1px solid #dee2e6; padding: 10px; border-radius: 5px; color: #333; text-align: center;
    }
    div[data-testid="metric-container"] label { font-size: 0.8rem; }
    
    hr { margin-top: 20px; margin-bottom: 20px; border: 0; border-top: 1px solid #eee; }
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

# --- HELPER: Logic for Current Quarter ---
def get_quarter_months():
    today = datetime.now()
    year = today.year
    month = today.month
    quarter = (month - 1) // 3 + 1
    start_month = (quarter - 1) * 3 + 1
    months = []
    for m in range(start_month, start_month + 3):
        months.append(f"{year}{m:02d}")
    current_month_str = today.strftime("%Y%m")
    return months, current_month_str, quarter

# --- FETCH DATA ---
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
                
                is_off = "offer" in stage
                is_int = "interview" in stage or "面试" in stage or is_off
                
                if is_off: count_off += 1
                if is_int: count_int += 1
                count_sent += 1
                
                status_label = "Sent"
                if is_off: status_label = "Offered"
                elif is_int: status_label = "Interviewed"
                
                processed.append({
                    "Consultant": consultant_config['name'],
                    "Month": target_tab,
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
    st.title("📈 Recruitment Management Dashboard")
    
    # 1. Button Logic
    col1, col2 = st.columns([1, 5]) 
    with col1:
        load_btn = st.button("🔄 LOAD HISTORY")

    if load_btn:
        client = connect_to_google()
        if not client:
            st.error("API Connection Failed.")
            return

        months, current_month_str, quarter_num = get_quarter_months()
        
        all_stats = [] 
        all_details_df = pd.DataFrame() 
        
        with st.spinner(f"Fetching data for Q{quarter_num} ({', '.join(months)})..."):
            progress_bar = st.progress(0)
            
            for i, month in enumerate(months):
                for consultant in TEAM_CONFIG:
                    s, interview, off, details = fetch_consultant_data(client, consultant, month)
                    
                    all_stats.append({
                        "Consultant": consultant['name'],
                        "Month": month,
                        "Sent": s,
                        "Interviewed": interview,
                        "Offered": off
                    })
                    
                    if details:
                        all_details_df = pd.concat([all_details_df, pd.DataFrame(details)], ignore_index=True)
                
                progress_bar.progress((i + 1) / len(months))
            
            progress_bar.empty()

        stats_df = pd.DataFrame(all_stats)

        # ==========================================
        # SECTION 1: SUMMARY 
        # ==========================================
        st.header("Summary")
        col_m, col_q = st.columns(2)
        
        with col_m:
            st.subheader(f"📅 Current Month ({current_month_str})")
            month_df = stats_df[stats_df['Month'] == current_month_str].copy()
            if not month_df.empty:
                month_view = month_df[['Consultant', 'Sent', 'Interviewed', 'Offered']].sort_values(by='Sent', ascending=False)
                st.dataframe(
                    month_view, use_container_width=True, hide_index=True,
                    column_config={
                        "Consultant": st.column_config.TextColumn("Consultant", width="medium"),
                        "Sent": st.column_config.NumberColumn("Sent/M", format="%d"),
                        "Interviewed": st.column_config.NumberColumn("Interviewed/M", format="%d"),
                        "Offered": st.column_config.NumberColumn("Offered/M", format="%d"),
                    }
                )
            else:
                st.info("No data found for the current month yet.")

        with col_q:
            st.subheader(f"🚀 Current Quarter (Q{quarter_num} Total)")
            quarter_view = stats_df.groupby('Consultant')[['Sent', 'Interviewed', 'Offered']].sum().reset_index()
            quarter_view = quarter_view.sort_values(by='Sent', ascending=False)
            st.dataframe(
                quarter_view, use_container_width=True, hide_index=True,
                column_config={
                    "Consultant": st.column_config.TextColumn("Consultant", width="medium"),
                    "Sent": st.column_config.ProgressColumn("Sent/Q", format="%d", min_value=0, max_value=int(quarter_view['Sent'].max() or 100)),
                    "Interviewed": st.column_config.NumberColumn("Interviewed/Q", format="%d"),
                    "Offered": st.column_config.NumberColumn("Offered/Q", format="%d"),
                }
            )

        st.divider()

        # ==========================================
        # SECTION 2: CONSULTANT DETAILS
        # ==========================================
        st.markdown("### 👤 Consultant Details")

        consultants_order = quarter_view['Consultant'].tolist()
        
        for consultant in consultants_order:
            # 1. 标题简化：因为很难对齐，我们只放名字和最重要的 Total Sent，引导用户点击
            c_q_data = quarter_view[quarter_view['Consultant'] == consultant].iloc[0]
            
            expander_label = f"🧑‍💼 {consultant}  (Quarter Total: {c_q_data['Sent']} Sent)"
            
            with st.expander(expander_label):
                
                # 2. 内部第一部分：季度汇总大数字 (这里是完美对齐的)
                k1, k2, k3 = st.columns(3)
                k1.metric("Quarterly Sent", c_q_data['Sent'])
                k2.metric("Quarterly Interviewed", c_q_data['Interviewed'])
                k3.metric("Quarterly Offered", c_q_data['Offered'])
                
                st.markdown("---")

                # 3. 内部第二部分：月度趋势明细 (您要求的“每个月具体的统计”)
                st.markdown("#### 📅 Monthly Breakdown (月度明细)")
                c_monthly_stats = stats_df[stats_df['Consultant'] == consultant][['Month', 'Sent', 'Interviewed', 'Offered']]
                # 按月份倒序排列
                c_monthly_stats = c_monthly_stats.sort_values(by='Month', ascending=False)
                
                st.dataframe(
                    c_monthly_stats, 
                    use_container_width=True, 
                    hide_index=True,
                    column_config={
                        "Month": st.column_config.TextColumn("Month"),
                        "Sent": st.column_config.NumberColumn("Sent", format="%d"),
                        "Interviewed": st.column_config.NumberColumn("Interviewed", format="%d"),
                        "Offered": st.column_config.NumberColumn("Offered", format="%d"),
                    }
                )
                
                # 4. 内部第三部分：具体的项目明细 (Tabs)
                st.markdown("#### 📝 Project Details")
                if not all_details_df.empty:
                    c_details = all_details_df[all_details_df['Consultant'] == consultant]
                    
                    if not c_details.empty:
                        tab1, tab2, tab3 = st.tabs(["📄 SENT Details", "👥 INTERVIEWED Details", "🎉 OFFERED Details"])
                        
                        def show_agg_table(filtered_df):
                            if filtered_df.empty:
                                st.info("No data recorded.")
                            else:
                                # 增加 Month 列，让人知道是哪个月投的
                                agg = filtered_df.groupby(['Month', 'Company', 'Position'])['Count'].sum().reset_index()
                                agg = agg.sort_values(by=['Month', 'Count'], ascending=[False, False])
                                st.dataframe(agg, use_container_width=True, hide_index=True)

                        with tab1: show_agg_table(c_details) 
                        with tab2: 
                            int_df = c_details[c_details['Status'].isin(['Interviewed', 'Offered'])]
                            show_agg_table(int_df)
                        with tab3: 
                            off_df = c_details[c_details['Status'] == 'Offered']
                            show_agg_table(off_df)
                    else:
                        st.caption("No detailed logs found for this period.")
                else:
                    st.caption("No detailed logs available.")

if __name__ == "__main__":
    main()

