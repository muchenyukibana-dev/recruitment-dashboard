import streamlit as st
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import pandas as pd
import os
import time
from datetime import datetime
import unicodedata

# ==========================================
# 🔧 配置区域
# ==========================================
SALES_SHEET_ID = '1rCmyqOUOBn-644KpCtF5FZwBMEnRGHTKSSUBxzvOSkI'
SALES_TAB_NAME = 'Positions' 

TEAM_CONFIG = [
    {"name": "Raul Solis", "keyword": "Name", "base_salary": 11000},
    {"name": "Estela Peng", "keyword": "姓名", "base_salary": 20800},
    {"name": "Ana Cruz", "keyword": "Name", "base_salary": 13000},
    {"name": "Karina Albarran", "keyword": "Name", "base_salary": 15000},
]

# 给 TEAM_CONFIG 补全 ID (复用原来的 ID，这里简化展示，请确保你的真实代码里有 ID)
for t in TEAM_CONFIG:
    # 这里为了演示方便，我填回原来的ID，请确保这里是对的
    if t['name'] == "Raul Solis": t['id'] = "1vQuN-iNBRUug5J6gBMX-52jp6oogbA77SaeAf9j_zYs"
    elif t['name'] == "Estela Peng": t['id'] = "1sUkffAXzWnpzhhmklqBuwtoQylpR1U18zqBQ-lsp7Z4"
    elif t['name'] == "Ana Cruz": t['id'] = "1VMVw5YCV12eI8I-VQSXEKg86J2IVZJEgjPJT7ggAFD0"
    elif t['name'] == "Karina Albarran": t['id'] = "1zc4ghvfjIxH0eJ2aXfopOWHqiyTDlD8yFNjBzpH07D8"

st.set_page_config(page_title="Management Dashboard", page_icon="💼", layout="wide")

# --- 🎨 样式 ---
st.markdown("""
    <style>
    .stApp { background-color: #FFFFFF; color: #000000; }
    h1, h2, h3, h4 { color: #333333 !important; font-family: 'Arial', sans-serif; }
    .stButton>button { background-color: #0056b3; color: white; border-radius: 4px; padding: 10px 24px; font-weight: bold; }
    .stButton>button:hover { background-color: #004494; color: white; }
    .dataframe { font-size: 14px !important; border: 1px solid #ddd !important; }
    div[data-testid="metric-container"] { background-color: #f8f9fa; border: 1px solid #e9ecef; padding: 15px; border-radius: 8px; color: #333; }
    .stProgress > div > div > div > div { background-color: #28a745; }
    </style>
    """, unsafe_allow_html=True)

# --- 🧮 辅助函数 ---
def calculate_commission_tier(total_gp, base_salary):
    # 季度 Target = 月薪 * 3 * 3
    q_target = base_salary * 3 * 3
    if total_gp < q_target: return 0, 0
    elif total_gp < 4.5 * (base_salary * 3): return 1, 1
    elif total_gp < 7.5 * (base_salary * 3): return 2, 2
    else: return 3, 3

def calculate_single_deal_commission(candidate_salary, multiplier):
    if multiplier == 0: return 0
    base_comm = 0
    if candidate_salary < 20000: base_comm = 1000
    elif candidate_salary < 30000: base_comm = candidate_salary * 0.05
    elif candidate_salary < 50000: base_comm = candidate_salary * 1.5 * 0.05
    else: base_comm = candidate_salary * 2.0 * 0.05
    return base_comm * multiplier

def normalize_text(text):
    return ''.join(c for c in unicodedata.normalize('NFD', str(text)) if unicodedata.category(c) != 'Mn').lower()

def connect_to_google():
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    if "gcp_service_account" in st.secrets:
        creds = ServiceAccountCredentials.from_json_keyfile_dict(dict(st.secrets["gcp_service_account"]), scope)
    else:
        creds = ServiceAccountCredentials.from_json_keyfile_name('credentials.json', scope)
    return gspread.authorize(creds)

# --- 📥 招聘数据 (保持不变) ---
def fetch_recruitment_stats(client, months):
    all_stats = []
    all_details = []
    for month in months:
        for consultant in TEAM_CONFIG:
            s, i, o, d = internal_fetch_sheet_data(client, consultant, month)
            all_stats.append({"Consultant": consultant['name'], "Month": month, "Sent": s, "Int": i, "Off": o})
            if d: all_details.extend(d)
    return pd.DataFrame(all_stats), pd.DataFrame(all_details)

def internal_fetch_sheet_data(client, conf, tab):
    try:
        sheet = client.open_by_key(conf['id'])
        ws = sheet.worksheet(tab)
        rows = ws.get_all_values()
        details = []; cs=0; ci=0; co=0
        target_key = conf.get('keyword', 'Name')
        COMPANY_KEYS = ["Company", "Client", "Cliente", "公司", "客户"]
        POSITION_KEYS = ["Position", "Role", "Posición", "职位", "岗位"]
        STAGE_KEYS = ["Stage", "Status", "Step", "阶段", "状态"]
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

# --- 💰 获取业绩数据 (修复后的状态机逻辑) ---
def fetch_sales_data(client, quarter_start_month, quarter_end_month, year):
    # st.info(f"正在提取: {year}年 {quarter_start_month}-{quarter_end_month}月")
    
    try:
        sheet = client.open_by_key(SALES_SHEET_ID)
        try: ws = sheet.worksheet(SALES_TAB_NAME)
        except: ws = sheet.get_worksheet(0)
            
        rows = ws.get_all_values()
        
        # 状态机
        state = "FIND_TITLE" # 初始状态：寻找标题
        
        col_cons = -1; col_onboard = -1; col_pay = -1; col_sal = -1
        sales_records = []
        
        for row in rows:
            # 清洗行数据
            row_text = [str(x).strip() for x in row]
            row_str_upper = " ".join(row_text).upper()
            row_lower = [x.lower() for x in row_text]
            
            # 状态 1: 寻找区域标题
            if state == "FIND_TITLE":
                if "PLACED" in row_str_upper and "POSITION" in row_str_upper:
                    state = "FIND_HEADER"
                    # st.success("找到区域标题，开始寻找表头...")
                continue
            
            # 状态 2: 寻找表头
            if state == "FIND_HEADER":
                # 检查这一行是否包含关键列
                has_cons = any("linkeazi" in c or "consultant" in c for c in row_lower)
                has_onb = any("onboarding" in c for c in row_lower)
                
                if has_cons and has_onb:
                    for idx, cell in enumerate(row_lower):
                        if "linkeazi" in cell or "consultant" in cell: col_cons = idx
                        if "onboarding" in cell: col_onboard = idx
                        if "payment" in cell: col_pay = idx
                        if "candidate" in cell or "salary" in cell: col_sal = idx
                    
                    if col_cons != -1 and col_onboard != -1:
                        state = "READ_DATA"
                        # st.success("表头锁定！开始读取数据...")
                    continue
                # 如果没找到表头，就继续往下找下一行，不报错
                continue

            # 状态 3: 读取数据
            if state == "READ_DATA":
                # 结束条件：遇到下一个标题
                if "POSITION" in row_str_upper and "PLACED" not in row_str_upper:
                    break
                
                # 数据完整性检查
                if len(row) <= max(col_cons, col_onboard, col_sal): continue
                
                consultant_name = row[col_cons].strip()
                if not consultant_name: continue
                # 跳过表头重复出现的行
                if "linkeazi" in consultant_name.lower(): continue

                # 日期解析
                onboard_str = row[col_onboard].strip()
                onboard_date = None
                formats = ["%Y-%m-%d", "%d/%m/%Y", "%Y/%m/%d", "%m/%d/%Y", "%d-%b-%y", "%Y.%m.%d"]
                for fmt in formats:
                    try: 
                        onboard_date = datetime.strptime(onboard_str, fmt)
                        break
                    except: pass
                
                if not onboard_date: continue
                
                # 季度筛选
                if not (onboard_date.year == year and quarter_start_month <= onboard_date.month <= quarter_end_month):
                    continue

                # 名字匹配
                matched = "Unknown"
                c_norm = normalize_text(consultant_name)
                for conf in TEAM_CONFIG:
                    conf_norm = normalize_text(conf['name'])
                    if conf_norm in c_norm or c_norm in conf_norm:
                        matched = conf['name']
                        break
                    if conf_norm.split()[0] in c_norm: 
                        matched = conf['name']
                        break
                
                if matched == "Unknown": continue

                # 薪资与GP
                salary_raw = str(row[col_sal]).replace(',', '').replace('$', '').replace('MXN', '').replace('CNY', '').strip()
                try: salary = float(salary_raw)
                except: salary = 0
                
                calc_gp = salary * 1.0 if salary < 20000 else salary * 1.5
                
                # 付款状态
                pay_date_str = ""
                status = "Pending"
                if col_pay != -1 and len(row) > col_pay:
                    pay_date_str = row[col_pay].strip()
                    if len(pay_date_str) > 5: status = "Paid"

                sales_records.append({
                    "Consultant": matched, 
                    "GP": calc_gp, 
                    "Candidate Salary": salary,
                    "Onboard Date": onboard_date.strftime("%Y-%m-%d"), 
                    "Payment Date": pay_date_str, 
                    "Status": status
                })

        return pd.DataFrame(sales_records)

    except Exception as e:
        st.error(f"Error: {e}")
        return pd.DataFrame()

# --- 🚀 主程序 ---
def main():
    st.title("💼 Management Dashboard (Q3 TEST)")
    
    col1, col2 = st.columns([1, 5])
    with col1:
        if st.button("🔄 LOAD Q3 DATA"):
            st.session_state['loaded'] = True
    
    if not st.session_state.get('loaded'):
        st.info("Click 'LOAD Q3 DATA' to view reports.")
        return

    client = connect_to_google()
    if not client: st.error("API Error"); return

    # === 🔧 测试参数 (Q3 2025) ===
    today = datetime.now()
    year = 2025 # 确认你的年份
    quarter_num = 3
    start_m = 7
    end_m = 9
    quarter_months_str = [f"{year}{m:02d}" for m in range(start_m, end_m + 1)]
    # ==============================

    with st.spinner("Analyzing Q3 Data..."):
        rec_stats_df, rec_details_df = fetch_recruitment_stats(client, quarter_months_str)
        sales_df = fetch_sales_data(client, start_m, end_m, year)
        
    tab_dash, tab_details = st.tabs(["📊 DASHBOARD", "📝 DETAILS"])

    # TAB 1: DASHBOARD
    with tab_dash:
        # A. Recruitment Stats
        st.markdown(f"### 🎯 Recruitment Stats (Q{quarter_num})")
        if not rec_stats_df.empty:
            rec_summary = rec_stats_df.groupby('Consultant')[['Sent', 'Int', 'Off']].sum().reset_index()
            rec_summary = rec_summary.sort_values(by='Sent', ascending=False)
            st.dataframe(
                rec_summary, use_container_width=True, hide_index=True,
                column_config={
                    "Sent": st.column_config.NumberColumn("Sent/Q", format="%d"),
                    "Int": st.column_config.NumberColumn("Int/Q", format="%d"),
                    "Off": st.column_config.NumberColumn("Off/Q", format="%d")
                }
            )
        else: st.warning("No recruitment data.")

        st.divider()

        # B. Financial Stats
        st.markdown(f"### 💰 Financial Performance (Q{quarter_num})")
        financial_summary = []
        for conf in TEAM_CONFIG:
            c_name = conf['name']
            base = conf['base_salary']
            target = base * 3 * 3 # 季度 Target
            
            c_sales = sales_df[sales_df['Consultant'] == c_name] if not sales_df.empty else pd.DataFrame()
            total_gp = c_sales['GP'].sum() if not c_sales.empty else 0
            
            level, multiplier = calculate_commission_tier(total_gp, base)
            total_comm = 0
            if not c_sales.empty:
                for _, row in c_sales.iterrows():
                    if row['Status'] == 'Paid':
                        total_comm += calculate_single_deal_commission(row['Candidate Salary'], multiplier)
            
            completion_rate = (total_gp / target) if target > 0 else 0
            financial_summary.append({
                "Consultant": c_name, "Base Salary": base, "Target": target,
                "Total GP": total_gp, "Completion": completion_rate,
                "Level": level, "Est. Commission": total_comm
            })
            
        df_fin = pd.DataFrame(financial_summary).sort_values(by='Total GP', ascending=False)
        st.dataframe(
            df_fin, use_container_width=True, hide_index=True,
            column_config={
                "Base Salary": st.column_config.NumberColumn(format="$%d"),
                "Target": st.column_config.NumberColumn("Target (Q)", format="$%d"),
                "Total GP": st.column_config.NumberColumn("Actual GP", format="$%d"),
                "Completion": st.column_config.ProgressColumn("Achieved", format="%.1f%%", min_value=0, max_value=1),
                "Est. Commission": st.column_config.NumberColumn("Commission", format="$%d"),
            }
        )

    # TAB 2: DETAILS
    with tab_details:
        st.markdown("### 🔍 Drill Down Details")
        for conf in TEAM_CONFIG:
            c_name = conf['name']
            fin_row = df_fin[df_fin['Consultant'] == c_name].iloc[0]
            header = f"👤 {c_name} | GP: ${fin_row['Total GP']:,.0f} (Lvl {fin_row['Level']})"
            
            with st.expander(header):
                st.markdown("#### 💸 Commission Breakdown")
