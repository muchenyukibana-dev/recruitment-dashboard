import streamlit as st
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import pandas as pd
import os
import time
from datetime import datetime

# ==========================================
# 🔧 TEAM CONFIGURATION (含底薪配置)
# ==========================================
SALES_SHEET_ID = '1rCmyqOUOBn-644KpCtF5FZwBMEnRGHTKSSUBxzvOSkI'
SALES_TAB_NAME = 'Placed Positions' 

TEAM_CONFIG = [
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

# ==========================================

st.set_page_config(page_title="Management Dashboard", page_icon="💼", layout="wide")

# --- 🎨 CSS STYLING ---
st.markdown("""
    <style>
    .stApp { background-color: #FFFFFF; color: #000000; }
    h1, h2, h3, h4 { color: #333333 !important; font-family: 'Arial', sans-serif; }
    
    .stButton>button {
        background-color: #0056b3; color: white; border: none; border-radius: 4px;
        padding: 10px 24px; font-weight: bold;
    }
    .stButton>button:hover { background-color: #004494; color: white; }

    .dataframe { font-size: 14px !important; border: 1px solid #ddd !important; }
    
    div[data-testid="metric-container"] {
        background-color: #f8f9fa; border: 1px solid #e9ecef; padding: 15px;
        border-radius: 8px; color: #333; box-shadow: 0 2px 4px rgba(0,0,0,0.05);
    }
    
    .stProgress > div > div > div > div { background-color: #28a745; }
    </style>
    """, unsafe_allow_html=True)

# --- 🧮 COMMISSION CALCULATOR ENGINE ---
def calculate_commission_tier(total_gp, base_salary):
    """根据总GP和底薪确定 Level (GP必须达到底薪3倍)"""
    if total_gp < 3 * base_salary:
        return 0, 0 # Not Qualified
    elif total_gp < 4.5 * base_salary:
        return 1, 1 # Level 1 (Multiplier 1)
    elif total_gp < 7.5 * base_salary:
        return 2, 2 # Level 2 (Multiplier 2)
    else:
        return 3, 3 # Level 3 (Multiplier 3)

def calculate_single_deal_commission(candidate_salary, multiplier):
    """根据单个候选人薪资和当前的Multiplier计算佣金"""
    if multiplier == 0:
        return 0
    
    base_comm = 0
    if candidate_salary < 20000:
        base_comm = 1000
    elif candidate_salary < 30000:
        base_comm = candidate_salary * 0.05
    elif candidate_salary < 50000:
        base_comm = candidate_salary * 1.5 * 0.05
    else: # >= 50000
        base_comm = candidate_salary * 2.0 * 0.05
        
    return base_comm * multiplier

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

# --- DATE HELPERS ---
def get_current_quarter_dates():
    today = datetime.now()
    quarter = (today.month - 1) // 3 + 1
    start_month = (quarter - 1) * 3 + 1
    return quarter, start_month, start_month + 2, today.year

# --- FETCH RECRUITMENT DATA ---
def fetch_recruitment_stats(client, months):
    all_stats = []
    all_details = []
    
    for month in months:
        for consultant in TEAM_CONFIG:
            s, i, o, d = internal_fetch_sheet_data(client, consultant, month)
            all_stats.append({
                "Consultant": consultant['name'],
                "Month": month,
                "Sent": s, "Int": i, "Off": o
            })
            if d: all_details.extend(d)
    return pd.DataFrame(all_stats), pd.DataFrame(all_details)

def internal_fetch_sheet_data(client, conf, tab):
    try:
        sheet = client.open_by_key(conf['id'])
        ws = sheet.worksheet(tab)
        rows = ws.get_all_values()
        details = []; cs=0; ci=0; co=0
        target_key = conf.get('keyword', 'Name')
        COMPANY_KEYS = ["Company", "Client", "Cliente", "公司", "客户", "客户名称", "公司名称"]
        POSITION_KEYS = ["Position", "Role", "Posición", "职位", "岗位", "职位名称", "岗位名称"]
        STAGE_KEYS = ["Stage", "Status", "Step", "阶段", "状态", "进展"]
        
        block = {"c": "Unk", "p": "Unk", "cands": {}}
        
        def flush(b):
            res = []; nonlocal cs, ci, co
            for _, c_data in b['cands'].items():
                name = c_data.get('n'); stage = str(c_data.get('s', 'Sent')).lower()
                if not name: continue
                is_off = "offer" in stage; is_int = "interview" in stage or "面试" in stage or is_off
                if is_off: co+=1
                if is_int: ci+=1
                cs+=1
                stat = "Offered" if is_off else ("Interviewed" if is_int else "Sent")
                res.append({"Consultant": conf['name'], "Month": tab, "Company": b['c'], "Position": b['p'], "Status": stat, "Count": 1})
            return res

        for r in rows:
            if not r: continue
            fc = r[0].strip()
            if fc in COMPANY_KEYS:
                details.extend(flush(block))
                block = {"c": r[1] if len(r)>1 else "Unk", "p": "Unk", "cands": {}}
            elif fc in POSITION_KEYS: block['p'] = r[1] if len(r)>1 else "Unk"
            elif fc == target_key:
                for idx, v in enumerate(r[1:], 1):
                    if v.strip(): 
                        if idx not in block['cands']: block['cands'][idx]={}
                        block['cands'][idx]['n'] = v.strip()
            elif fc in STAGE_KEYS:
                for idx, v in enumerate(r[1:], 1):
                    if v.strip():
                        if idx not in block['cands']: block['cands'][idx]={}
                        block['cands'][idx]['s'] = v.strip()
        details.extend(flush(block))
        return cs, ci, co, details
    except: return 0,0,0,[]

# --- FETCH SALES DATA (MODIFIED GP LOGIC) ---
def fetch_sales_data(client, quarter_start_month, quarter_end_month, year):
    """读取业绩表格并应用新的 GP 计算规则"""
    try:
        sheet = client.open_by_key(SALES_SHEET_ID)
        ws = sheet.worksheet(SALES_TAB_NAME)
        rows = ws.get_all_values()
        
        if not rows: return pd.DataFrame()
        
        header = [h.strip().lower() for h in rows[0]]
        
        # 1. 查找列索引
        try:
            col_cons = -1; col_date = -1; col_sal = -1
            for idx, h in enumerate(header):
                # 修改：专门查找 "linkeazi consultant"
                if "linkeazi" in h or "consultant" in h or "顾问" in h: 
                    col_cons = idx
                if "date" in h or "payment" in h or "付款" in h: 
                    col_date = idx
                if "salary" in h or "薪资" in h or "base" in h: 
                    col_sal = idx
            
            # 注意：不再强制查找 'GP' 列，因为我们要自己算
            if -1 in [col_cons, col_date, col_sal]:
                st.error("Error: Could not find required columns (Linkeazi Consultant, Payment Date, Candidate's Salary).")
                return pd.DataFrame()
        except:
            return pd.DataFrame()

        sales_records = []
        
        for row in rows[1:]:
            if len(row) <= max(col_cons, col_date, col_sal): continue
            
            # 2. 检查日期
            date_str = row[col_date].strip()
            try:
                pay_date = None
                for fmt in ["%Y-%m-%d", "%d/%m/%Y", "%Y/%m/%d", "%m/%d/%Y", "%Y.%m.%d"]:
                    try:
                        pay_date = datetime.strptime(date_str, fmt)
                        break
                    except: pass
                
                if not pay_date: continue
                
                # 3. 过滤本季度
                if pay_date.year == year and quarter_start_month <= pay_date.month <= quarter_end_month:
                    
                    # 4. 获取并清洗 Salary
                    salary_raw = str(row[col_sal]).replace(',', '').replace('$', '').replace('MXN', '').strip()
                    salary = float(salary_raw) if salary_raw else 0
                    
                    # 5. 🔥 核心修改：GP 计算公式
                    # < 20000: 权重 1
                    # >= 20000: 权重 1.5
                    if salary < 20000:
                        calculated_gp = salary * 1.0
                    else:
                        calculated_gp = salary * 1.5
                    
                    consultant_name = row[col_cons].strip()
                    
                    # 匹配 Config
                    matched_name = "Unknown"
                    for conf in TEAM_CONFIG:
                        if conf['name'].lower() in consultant_name.lower():
                            matched_name = conf['name']
                            break
                    
                    if matched_name != "Unknown":
                        sales_records.append({
                            "Consultant": matched_name,
                            "GP": calculated_gp, # 使用计算后的 GP
                            "Candidate Salary": salary,
                            "Date": pay_date.strftime("%Y-%m-%d")
                        })
            except Exception:
                continue
                
        return pd.DataFrame(sales_records)

    except Exception as e:
        st.error(f"Sales Data Error: {e}")
        return pd.DataFrame()

# --- MAIN APP ---
def main():
    st.title("💼 Management & Performance Dashboard")
    
    col1, col2 = st.columns([1, 5])
    with col1:
        if st.button("🔄 LOAD DATA"):
            st.session_state['loaded'] = True
    
    if not st.session_state.get('loaded'):
        st.info("Click 'LOAD DATA' to fetch reports.")
        return

    client = connect_to_google()
    if not client:
        st.error("API Connection Failed.")
        return

    # Prepare Dates
    today = datetime.now()
    year = today.year
    quarter_num = (today.month - 1) // 3 + 1
    start_m = (quarter_num - 1) * 3 + 1
    end_m = start_m + 2
    
    quarter_months_str = [f"{year}{m:02d}" for m in range(start_m, end_m + 1)]

    with st.spinner("Analyzing Recruitment & Sales Data..."):
        # A. Fetch Recruitment
        rec_stats_df, rec_details_df = fetch_recruitment_stats(client, quarter_months_str)
        
        # B. Fetch Sales (Using new GP logic)
        sales_df = fetch_sales_data(client, start_m, end_m, year)
        
    # ==========================================
    # TABS LAYOUT
    # ==========================================
    tab_dash, tab_details = st.tabs(["📊 DASHBOARD (Summary)", "📝 DETAILS (Breakdown)"])

    # ------------------------------------------
    # TAB 1: DASHBOARD
    # ------------------------------------------
    with tab_dash:
        st.markdown(f"### 🎯 Recruitment Stats (Q{quarter_num})")
        if not rec_stats_df.empty:
            rec_summary = rec_stats_df.groupby('Consultant')[['Sent', 'Int', 'Off']].sum().reset_index()
            rec_summary = rec_summary.sort_values(by='Sent', ascending=False)
            
            st.dataframe(
                rec_summary, use_container_width=True, hide_index=True,
                column_config={
                    "Consultant": st.column_config.TextColumn("Consultant"),
                    "Sent": st.column_config.ProgressColumn("Sent", format="%d", min_value=0, max_value=int(rec_summary['Sent'].max() or 100)),
                    "Int": st.column_config.NumberColumn("Interviewed", format="%d"),
                    "Off": st.column_config.NumberColumn("Offered", format="%d")
                }
            )
        else:
            st.warning("No recruitment data found.")

        st.divider()

        st.markdown(f"### 💰 Financial Performance (Q{quarter_num})")
        
        financial_summary = []
        
        for conf in TEAM_CONFIG:
            c_name = conf['name']
            base = conf['base_salary']
            target = base * 3
            
            c_sales = sales_df[sales_df['Consultant'] == c_name] if not sales_df.empty else pd.DataFrame()
            total_gp = c_sales['GP'].sum() if not c_sales.empty else 0
            
            level, multiplier = calculate_commission_tier(total_gp, base)
            
            total_comm = 0
            if not c_sales.empty:
                for _, row in c_sales.iterrows():
                    comm = calculate_single_deal_commission(row['Candidate Salary'], multiplier)
                    total_comm += comm
            
            completion_rate = (total_gp / target) if target > 0 else 0
            
            financial_summary.append({
                "Consultant": c_name,
                "Base Salary": base,
                "Target (3x)": target,
                "Total GP": total_gp,
                "Completion": completion_rate,
                "Level": level,
                "Est. Commission": total_comm
            })
            
        df_fin = pd.DataFrame(financial_summary)
        df_fin = df_fin.sort_values(by='Total GP', ascending=False)
        
        st.dataframe(
            df_fin, use_container_width=True, hide_index=True,
            column_config={
                "Base Salary": st.column_config.NumberColumn("Base Salary", format="$%d"),
                "Target (3x)": st.column_config.NumberColumn("Target GP", format="$%d"),
                "Total GP": st.column_config.NumberColumn("Calculated GP", format="$%d"), # Changed Title
                "Completion": st.column_config.ProgressColumn("Target Met", format="%.1f%%", min_value=0, max_value=1),
                "Level": st.column_config.TextColumn("Tier"),
                "Est. Commission": st.column_config.NumberColumn("Commission", format="$%d"),
            }
        )

    # ------------------------------------------
    # TAB 2: DETAILS
    # ------------------------------------------
    with tab_details:
        st.markdown("### 🔍 Drill Down Details")
        
        for conf in TEAM_CONFIG:
            c_name = conf['name']
            
            fin_row = df_fin[df_fin['Consultant'] == c_name].iloc[0]
            rec_row = rec_summary[rec_summary['Consultant'] == c_name].iloc[0] if not rec_summary.empty and c_name in rec_summary['Consultant'].values else pd.Series({'Sent':0, 'Int':0, 'Off':0})
            
            header_text = f"👤 {c_name} | GP: ${fin_row['Total GP']:,.0f} (Lvl {fin_row['Level']}) | Sent: {rec_row['Sent']}"
            
            with st.expander(header_text):
                st.markdown("#### 💸 Commission Breakdown (Calculated)")
                c_sales = sales_df[sales_df['Consultant'] == c_name] if not sales_df.empty else pd.DataFrame()
                
                if not c_sales.empty:
                    multiplier = calculate_commission_tier(fin_row['Total GP'], fin_row['Base Salary'])[1]
                    # Calc commission based on salary
                    c_sales['Commission'] = c_sales['Candidate Salary'].apply(lambda s: calculate_single_deal_commission(s, multiplier))
                    
                    st.dataframe(
                        c_sales[['Date', 'Candidate Salary', 'GP', 'Commission']],
                        use_container_width=True, hide_index=True,
                        column_config={
                            "Date": st.column_config.DateColumn("Payment Date"),
                            "Candidate Salary": st.column_config.NumberColumn("Salary", format="$%d"),
                            "GP": st.column_config.NumberColumn("Calc. GP", format="$%d"),
                            "Commission": st.column_config.NumberColumn("Comm. (Est)", format="$%d"),
                        }
                    )
                    if multiplier == 0:
                        st.warning(f"⚠️ Target not met. Multiplier is 0.")
                    else:
                        st.success(f"✅ Level {fin_row['Level']} (Multiplier x{multiplier})")
                else:
                    st.info("No closed deals.")
                
                st.divider()
                
                st.markdown("#### 📝 Recruitment Logs")
                if not rec_details_df.empty:
                    c_logs = rec_details_df[rec_details_df['Consultant'] == c_name]
                    if not c_logs.empty:
                        agg = c_logs.groupby(['Month', 'Company', 'Position', 'Status'])['Count'].sum().reset_index()
                        st.dataframe(agg, use_container_width=True, hide_index=True)
                    else:
                        st.info("No recruitment logs.")
                else:
                    st.info("No data.")

if __name__ == "__main__":
    main()
