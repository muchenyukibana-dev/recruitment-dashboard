import streamlit as st
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import pandas as pd
import os
import time
from datetime import datetime

# ==========================================
# 🔧 配置区域
# ==========================================
SALES_SHEET_ID = '1rCmyqOUOBn-644KpCtF5FZwBMEnRGHTKSSUBxzvOSkI'
SALES_TAB_NAME = 'Positions' 

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

# 设置页面
st.set_page_config(page_title="Management Dashboard (Q3)", page_icon="💼", layout="wide")

# --- 🎨 样式设置 ---
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

# --- 🧮 佣金计算引擎 ---
def calculate_commission_tier(total_gp, base_salary):
    """判断 Level"""
    if total_gp < 3 * base_salary:
        return 0, 0
    elif total_gp < 4.5 * base_salary:
        return 1, 1
    elif total_gp < 7.5 * base_salary:
        return 2, 2
    else:
        return 3, 3

def calculate_single_deal_commission(candidate_salary, multiplier):
    """计算单笔佣金"""
    if multiplier == 0: return 0
    base_comm = 0
    if candidate_salary < 20000: base_comm = 1000
    elif candidate_salary < 30000: base_comm = candidate_salary * 0.05
    elif candidate_salary < 50000: base_comm = candidate_salary * 1.5 * 0.05
    else: base_comm = candidate_salary * 2.0 * 0.05
    return base_comm * multiplier

# --- 🔗 连接 Google ---
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

# --- 📥 获取招聘数据 ---
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

# --- FETCH SALES DATA (超级侦探版 / DEBUG MODE) ---
def fetch_sales_data(client, quarter_start_month, quarter_end_month, year):
    # 打印目标范围
    st.info(f"🕵️‍♂️ 侦探模式启动: 正在寻找 {year}年 {quarter_start_month}-{quarter_end_month}月 的数据...")
    
    try:
        sheet = client.open_by_key(SALES_SHEET_ID)
        try:
            ws = sheet.worksheet(SALES_TAB_NAME)
        except:
            ws = sheet.get_worksheet(0)
            st.warning(f"⚠️ 未找到名为 '{SALES_TAB_NAME}' 的Tab，正在读取第1个Tab: {ws.title}")
            
        rows = ws.get_all_values()
        st.write(f"📊 表格总行数: {len(rows)}")
        
        found_section = False
        found_header = False
        col_cons = -1; col_onboard = -1; col_pay = -1; col_sal = -1
        sales_records = []
        
        # 关键词定义 (全部小写)
        KEYS_CONS = ["linkeazi", "consultant", "owner", "顾问"]
        KEYS_ONBOARD = ["onboard", "entry", "start", "入职"]
        KEYS_PAY = ["payment", "date", "paid", "付款"]
        KEYS_SALARY = ["salary", "base", "wage", "薪资", "底薪", "candidate"]

        for i, row in enumerate(rows):
            # 将整行拼成字符串，方便查找大标题
            row_str = " ".join([str(x).strip() for x in row]).upper()
            
            # 1. 寻找区域入口
            if not found_section:
                if "PLACED" in row_str and "POSITION" in row_str:
                    found_section = True
                    st.success(f"✅ 在第 {i+1} 行发现了 'PLACED POSITIONS' 区域！")
                continue 
            
            # 2. 在区域内寻找表头
            if found_section and not found_header:
                row_lower = [str(x).strip().lower() for x in row]
                
                # 尝试匹配列
                for idx, cell in enumerate(row_lower):
                    if any(k in cell for k in KEYS_CONS): col_cons = idx
                    if any(k in cell for k in KEYS_ONBOARD): col_onboard = idx
                    if any(k in cell for k in KEYS_PAY): 
                        # 排除掉 Onboarding 里的 date，只找 payment date
                        if "onboard" not in cell: 
                            col_pay = idx
                    if any(k in cell for k in KEYS_SALARY): col_sal = idx
                
                # 打印这一行，让你看看代码读到了什么
                # st.write(f"正在分析第 {i+1} 行表头: {row_lower}")
                
                if col_cons != -1 and col_onboard != -1 and col_sal != -1:
                    found_header = True
                    st.success(f"✅ 在第 {i+1} 行锁定表头! \n 顾问列:{col_cons+1}, 入职列:{col_onboard+1}, 薪资列:{col_sal+1}")
                continue

            # 3. 读取数据
            if found_header:
                # 遇到下一个区域停止
                if "POSITION" in row_str and "PLACED" not in row_str:
                    st.info(f"🛑 在第 {i+1} 行遇到新标题，停止读取。")
                    break 
                
                # 检查行长度
                max_idx = max(col_cons, col_onboard, col_pay, col_sal)
                if len(row) <= max_idx: continue
                
                consultant_name = row[col_cons].strip()
                if not consultant_name: continue

                # --- 🔍 日期诊断 ---
                onboard_str = row[col_onboard].strip()
                onboard_date = None
                
                # 增加更多日期格式
                formats = [
                    "%Y-%m-%d", "%Y/%m/%d", "%Y.%m.%d", 
                    "%d-%m-%Y", "%d/%m/%Y", 
                    "%d-%b-%y", "%d-%b-%Y", "%d-%B-%Y",
                    "%m/%d/%Y", "%m-%d-%Y"
                ]
                
                for fmt in formats:
                    try:
                        onboard_date = datetime.strptime(onboard_str, fmt)
                        break
                    except: pass
                
                # 如果日期解析失败，报错告诉用户
                if not onboard_date:
                    # st.warning(f"⚠️ 第 {i+1} 行 ({consultant_name}) 跳过: 入职日期 '{onboard_str}' 无法识别。")
                    continue
                
                # 检查季度
                if not (onboard_date.year == year and quarter_start_month <= onboard_date.month <= quarter_end_month):
                    # st.write(f"⚪ 第 {i+1} 行日期 {onboard_date.date()} 不在 Q3 范围内，跳过。")
                    continue

                # --- 💰 数据提取 ---
                salary_raw = str(row[col_sal]).replace(',', '').replace('$', '').replace('MXN', '').replace('CNY', '').strip()
                try: salary = float(salary_raw)
                except: salary = 0
                
                calc_gp = salary * 1.0 if salary < 20000 else salary * 1.5
                
                # 解析 Payment Date
                pay_date_str = ""
                status = "Pending"
                if col_pay != -1:
                    pay_date_str = row[col_pay].strip()
                    # 尝试解析付款日期
                    for fmt in formats:
                        try:
                            if datetime.strptime(pay_date_str, fmt):
                                status = "Paid"
                                break
                        except: pass

                # --- 👤 名字匹配诊断 ---
                matched = "Unknown"
                for conf in TEAM_CONFIG:
                    if conf['name'].lower() in consultant_name.lower():
                        matched = conf['name']
                        break
                
                if matched != "Unknown":
                    sales_records.append({
                        "Consultant": matched,
                        "GP": calc_gp,
                        "Candidate Salary": salary,
                        "Onboard Date": onboard_date.strftime("%Y-%m-%d"),
                        "Payment Date": pay_date_str,
                        "Status": status
                    })
                    # st.write(f"🟢 成功读取第 {i+1} 行: {matched} - GP: {calc_gp}")
                else:
                    st.warning(f"❓ 第 {i+1} 行名字 '{consultant_name}' 未在配置中找到匹配。")

        st.success(f"🏁 最终提取到 {len(sales_records)} 条有效记录")
        return pd.DataFrame(sales_records)

    except Exception as e:
        st.error(f"❌ 系统错误: {e}")
        return pd.DataFrame()
        
# --- 🚀 主程序 (Q3 测试版) ---
def main():
    st.title("💼 Management Dashboard (Q3 TEST)")
    
    col1, col2 = st.columns([1, 5])
    with col1:
        if st.button("🔄 LOAD Q3 DATA"):
            st.session_state['loaded'] = True
    
    if not st.session_state.get('loaded'):
        st.info("Click 'LOAD Q3 DATA' to fetch report.")
        return

    client = connect_to_google()
    if not client:
        st.error("API Error")
        return

    # === 🔧 测试参数 (Q3) ===
    today = datetime.now()
    year = 2025 # 确认年份
    quarter_num = 3
    start_m = 7
    end_m = 9
    quarter_months_str = [f"{year}{m:02d}" for m in range(start_m, end_m + 1)]
    # ======================

    with st.spinner("Analyzing Q3 Data..."):
        rec_stats_df, rec_details_df = fetch_recruitment_stats(client, quarter_months_str)
        sales_df = fetch_sales_data(client, start_m, end_m, year)
        
    tab_dash, tab_details = st.tabs(["📊 DASHBOARD", "📝 DETAILS"])

    # --- TAB 1: DASHBOARD ---
    with tab_dash:
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
        else:
            st.warning(f"No recruitment data found.")

        st.divider()

        st.markdown(f"### 💰 Financial Performance (Q{quarter_num})")
        financial_summary = []
        for conf in TEAM_CONFIG:
            c_name = conf['name']
            base = conf['base_salary']
            target = base * 3
            
            c_sales = sales_df[sales_df['Consultant'] == c_name] if not sales_df.empty else pd.DataFrame()
            
            # GP: 根据 Onboarding Date 在本季度的所有单子总和
            total_gp = c_sales['GP'].sum() if not c_sales.empty else 0
            
            # Level: 根据 GP 和 Base 算
            level, multiplier = calculate_commission_tier(total_gp, base)
            
            # Commission: 只有 Payment Status 为 'Paid' 的单子才计算金额
            total_comm = 0
            if not c_sales.empty:
                for _, row in c_sales.iterrows():
                    # 只有已付款的才算进“预计佣金”
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
                "Target": st.column_config.NumberColumn("Target (3x)", format="$%d"),
                "Total GP": st.column_config.NumberColumn("Actual GP (Onboarded)", format="$%d"),
                "Completion": st.column_config.ProgressColumn("Achieved", format="%.1f%%", min_value=0, max_value=1),
                "Est. Commission": st.column_config.NumberColumn("Commission (Paid Only)", format="$%d"),
            }
        )

    # --- TAB 2: DETAILS ---
    with tab_details:
        st.markdown("### 🔍 Drill Down Details")
        for conf in TEAM_CONFIG:
            c_name = conf['name']
            fin_row = df_fin[df_fin['Consultant'] == c_name].iloc[0]
            
            # Header
            header = f"👤 {c_name} | GP: ${fin_row['Total GP']:,.0f} (Lvl {fin_row['Level']})"
            
            with st.expander(header):
                st.markdown("#### 💸 Sales Breakdown")
                c_sales = sales_df[sales_df['Consultant'] == c_name] if not sales_df.empty else pd.DataFrame()
                
                if not c_sales.empty:
                    multiplier = calculate_commission_tier(fin_row['Total GP'], fin_row['Base Salary'])[1]
                    
                    # 动态计算佣金列显示
                    def get_comm_display(row):
                        if row['Status'] == 'Paid':
                            return calculate_single_deal_commission(row['Candidate Salary'], multiplier)
                        else:
                            return 0 # 未付款显示0
                            
                    c_sales['Commission'] = c_sales.apply(get_comm_display, axis=1)
                    
                    st.dataframe(
                        c_sales[['Onboard Date', 'Payment Date', 'Candidate Salary', 'GP', 'Status', 'Commission']],
                        use_container_width=True, hide_index=True,
                        column_config={
                            "Onboard Date": st.column_config.DateColumn("Onboard"),
                            "Payment Date": st.column_config.TextColumn("Payment"), # TextColumn防止空日期报错
                            "Candidate Salary": st.column_config.NumberColumn("Salary", format="$%d"),
                            "GP": st.column_config.NumberColumn("GP", format="$%d"),
                            "Commission": st.column_config.NumberColumn("Comm.", format="$%d"),
                        }
                    )
                    if multiplier > 0: st.success(f"✅ Multiplier: x{multiplier}")
                    else: st.warning("⚠️ Target not met")
                else: st.info("No sales in this quarter.")
                
                st.divider()
                st.markdown("#### 📝 Recruitment Logs")
                if not rec_details_df.empty:
                    c_logs = rec_details_df[rec_details_df['Consultant'] == c_name]
                    if not c_logs.empty:
                        agg = c_logs.groupby(['Month', 'Company', 'Position', 'Status'])['Count'].sum().reset_index()
                        agg = agg.sort_values(by='Month', ascending=False)
                        st.dataframe(agg, use_container_width=True, hide_index=True)
                    else: st.info("No logs.")
                else: st.info("No data.")

if __name__ == "__main__":
    main()
