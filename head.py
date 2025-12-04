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

st.set_page_config(page_title="Management Dashboard", page_icon="💼", layout="wide")

# --- 🎨 样式 ---
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


# --- 🧮 辅助函数 ---
def calculate_commission_tier(total_gp, base_salary):
    if total_gp < 9 * base_salary:
        return 0, 0
    elif total_gp < 13.5 * base_salary:
        return 1, 1
    elif total_gp < 22.5 * base_salary:
        return 2, 2
    else:
        return 3, 3


def calculate_single_deal_commission(candidate_salary, multiplier):
    if multiplier == 0: return 0
    base_comm = 0
    if candidate_salary < 20000:
        base_comm = 1000
    elif candidate_salary < 30000:
        base_comm = candidate_salary * 0.05
    elif candidate_salary < 50000:
        base_comm = candidate_salary * 1.5 * 0.05
    else:
        base_comm = candidate_salary * 2.0 * 0.05
    return base_comm * multiplier


def normalize_text(text):
    """去除重音符号 (Raúl -> raul)"""
    return ''.join(c for c in unicodedata.normalize('NFD', str(text)) if unicodedata.category(c) != 'Mn').lower()


# --- 🔗 连接 ---
def connect_to_google():
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    if "gcp_service_account" in st.secrets:
        try:
            creds_dict = dict(st.secrets["gcp_service_account"])
            creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
            return gspread.authorize(creds)
        except Exception:
            return None
    else:
        current_dir = os.path.dirname(os.path.abspath(__file__))
        json_path = os.path.join(current_dir, 'credentials.json')
        if os.path.exists(json_path):
            try:
                creds = ServiceAccountCredentials.from_json_keyfile_name(json_path, scope)
                return gspread.authorize(creds)
            except Exception:
                return None
        else:
            return None


# --- 📥 招聘数据 ---
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
        details = [];
        cs = 0;
        ci = 0;
        co = 0
        target_key = conf.get('keyword', 'Name')
        COMPANY_KEYS = ["Company", "Client", "Cliente", "公司", "客户"]
        POSITION_KEYS = ["Position", "Role", "Posición", "职位", "岗位"]
        STAGE_KEYS = ["Stage", "Status", "Step", "阶段", "状态"]
        block = {"c": "Unk", "p": "Unk", "cands": {}}

        def flush(b):
            res = [];
            nonlocal cs, ci, co
            for _, c_data in b['cands'].items():
                name = c_data.get('n');
                stage = str(c_data.get('s', 'Sent')).lower()
                if not name: continue
                is_off = "offer" in stage;
                is_int = "interview" in stage or "面试" in stage or is_off
                if is_off: co += 1
                if is_int: ci += 1
                cs += 1
                stat = "Offered" if is_off else ("Interviewed" if is_int else "Sent")
                res.append(
                    {"Consultant": conf['name'], "Month": tab, "Company": b['c'], "Position": b['p'], "Status": stat,
                     "Count": 1})
            return res

        for r in rows:
            if not r: continue
            fc = r[0].strip()
            if fc in COMPANY_KEYS:
                details.extend(flush(block))
                block = {"c": r[1] if len(r) > 1 else "Unk", "p": "Unk", "cands": {}}
            elif fc in POSITION_KEYS:
                block['p'] = r[1] if len(r) > 1 else "Unk"
            elif fc == target_key:
                for idx, v in enumerate(r[1:], 1):
                    if v.strip():
                        if idx not in block['cands']: block['cands'][idx] = {}
                        block['cands'][idx]['n'] = v.strip()
            elif fc in STAGE_KEYS:
                for idx, v in enumerate(r[1:], 1):
                    if v.strip():
                        if idx not in block['cands']: block['cands'][idx] = {}
                        block['cands'][idx]['s'] = v.strip()
        details.extend(flush(block))
        return cs, ci, co, details
    except:
        return 0, 0, 0, []


# --- FETCH SALES DATA (增加 Company 和 Position) ---
def fetch_sales_data(client, quarter_start_month, quarter_end_month, year):
    # st.info(f"🚀 提取业绩: {year}年 Q{int((quarter_start_month-1)/3)+1}")
    try:
        sheet = client.open_by_key(SALES_SHEET_ID)
        try: ws = sheet.worksheet(SALES_TAB_NAME)
        except: ws = sheet.get_worksheet(0)
            
        rows = ws.get_all_values()
        
        found_section = False
        found_header = False
        
        # 新增 col_comp (公司) 和 col_pos (岗位)
        col_cons = -1; col_onboard = -1; col_pay = -1; col_sal = -1; col_comp = -1; col_pos = -1
        sales_records = []
        
        # 关键词库增加 Company 和 Position
        KEYS_CONS = ["linkeazi", "consultant", "owner", "顾问"]
        KEYS_ONBOARD = ["onboard", "entry", "start", "入职"]
        KEYS_PAY = ["payment", "date", "paid", "付款"]
        KEYS_SALARY = ["salary", "base", "wage", "薪资", "candidate"]
        KEYS_COMP = ["company", "client", "customer", "客户", "公司"] # 新增
        KEYS_POS = ["position", "role", "title", "岗位", "职位"]     # 新增

        for i, row in enumerate(rows):
            if not any(cell.strip() for cell in row): continue
            
            row_text = [str(x).strip() for x in row]
            row_str = " ".join(row_text).upper()
            row_lower = [x.lower() for x in row_text]

            # 1. 找区域
            if not found_section:
                if "PLACED" in row_str and "POSITION" in row_str:
                    found_section = True
                    # 强制检查下一行
                    if i + 1 < len(rows):
                        next_row = rows[i+1]
                        next_lower = [str(x).strip().lower() for x in next_row]
                        t_c=-1; t_o=-1; t_s=-1
                        for idx, cell in enumerate(next_lower):
                            if any(k in cell for k in KEYS_CONS): t_c = idx
                            if any(k in cell for k in KEYS_ONBOARD): t_o = idx
                            if any(k in cell for k in KEYS_SALARY): t_s = idx
                        
                        if t_c != -1 and t_s != -1:
                            # 重新扫描所有列
                            for idx, cell in enumerate(next_lower):
                                if any(k in cell for k in KEYS_CONS): col_cons = idx
                                if any(k in cell for k in KEYS_ONBOARD): col_onboard = idx
                                if any(k in cell for k in KEYS_PAY) and "onboard" not in cell: col_pay = idx
                                if any(k in cell for k in KEYS_SALARY): col_sal = idx
                                # 抓取公司和岗位列号
                                if any(k in cell for k in KEYS_COMP): col_comp = idx
                                if any(k in cell for k in KEYS_POS) and "placed" not in cell: col_pos = idx
                            
                            found_header = True
                            continue 
                continue 

            # 2. 找表头 (常规扫描)
            if found_section and not found_header:
                has_cons = any("linkeazi" in c and "consultant" in c for c in row_lower)
                has_onb = any("onboarding" in c for c in row_lower)
                if has_cons and has_onb:
                    for idx, cell in enumerate(row_lower):
                        if "linkeazi" in cell and "consultant" in cell: col_cons = idx
                        if "onboarding" in cell and "date" in cell: col_onboard = idx
                        if "candidate" in cell and "salary" in cell: col_sal = idx
                        if "payment" in cell: col_pay = idx
                        # 抓取公司和岗位列号
                        if any(k in cell for k in KEYS_COMP): col_comp = idx
                        if any(k in cell for k in KEYS_POS): col_pos = idx
                    found_header = True
                continue

            # 3. 读取数据
            if found_header:
                if "POSITION" in row_str and "PLACED" not in row_str: break 
                if len(row) <= max(col_cons, col_onboard, col_sal): continue
                
                consultant_name = row[col_cons].strip()
                if not consultant_name: continue 

                onboard_str = row[col_onboard].strip()
                onboard_date = None
                formats = ["%Y-%m-%d", "%d/%m/%Y", "%Y/%m/%d", "%m/%d/%Y", "%d-%b-%y", "%Y.%m.%d"]
                for fmt in formats:
                    try: 
                        onboard_date = datetime.strptime(onboard_str, fmt)
                        break
                    except: pass
                
                if not onboard_date: continue 
                if not (onboard_date.year == year and quarter_start_month <= onboard_date.month <= quarter_end_month):
                    continue

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

                salary_raw = str(row[col_sal]).replace(',', '').replace('$', '').replace('MXN', '').replace('CNY', '').strip()
                try: salary = float(salary_raw)
                except: salary = 0
                
                calc_gp = salary * 1.0 if salary < 20000 else salary * 1.5
                
                pay_date_str = ""
                status = "Pending"
                if col_pay != -1 and len(row) > col_pay:
                    pay_date_str = row[col_pay].strip()
                    if len(pay_date_str) > 5: status = "Paid"

                # 获取公司和岗位 (增加容错)
                comp_name = row[col_comp].strip() if col_comp != -1 and len(row) > col_comp else "N/A"
                pos_name = row[col_pos].strip() if col_pos != -1 and len(row) > col_pos else "N/A"

                sales_records.append({
                    "Consultant": matched, 
                    "Company": comp_name, # 新增
                    "Position": pos_name, # 新增
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
        

# --- 🚀 主程序 (阶梯佣金版) ---
def main():
    st.title("💼 Management Dashboard")
    
    col1, col2 = st.columns([1, 5])
    with col1:
        if st.button("🔄 LOAD Q3 DATA"):
            st.session_state['loaded'] = True
    
    if not st.session_state.get('loaded'):
        st.info("Click 'LOAD Q3 DATA' to view reports.")
        return

    client = connect_to_google()
    if not client: st.error("API Error"); return

    # === 🔧 生产环境设置 ===
    today = datetime.now()
    year = 2025
    quarter_num = 3
    start_m = 7
    end_m = 9
    quarter_months_str = [f"{year}{m:02d}" for m in range(start_m, end_m + 1)]
    # ======================

    with st.spinner("Analyzing Data..."):
        rec_stats_df, rec_details_df = fetch_recruitment_stats(client, quarter_months_str)
        sales_df = fetch_sales_data(client, start_m, end_m, year)
        
    tab_dash, tab_details = st.tabs(["📊 DASHBOARD", "📝 DETAILS"])

    # 1. 预计算佣金逻辑 (放在循环外，因为两个 Tab 都要用)
    # 我们需要为 sales_df 里的每一行计算出当时的 Multiplier 和 Commission
    
    financial_summary = []
    
    # 如果有销售数据，进行高级计算
    if not sales_df.empty:
        # 必须按入职日期排序，这样才能模拟"逐步达标"的过程
        sales_df = sales_df.sort_values(by='Onboard Date')
        
        # 初始化新列
        sales_df['Current_Cum_GP'] = 0.0
        sales_df['Applied_Level'] = 0
        sales_df['Applied_Multiplier'] = 0.0
        sales_df['Commission'] = 0.0
        
        # 按顾问分组进行累加计算
        for conf in TEAM_CONFIG:
            c_name = conf['name']
            base = conf['base_salary']
            target = base * 3 * 3
            
            # 筛选该顾问的单子
            c_indices = sales_df[sales_df['Consultant'] == c_name].index
            
            running_gp = 0.0
            total_comm = 0.0
            
            for idx in c_indices:
                deal_gp = sales_df.at[idx, 'GP']
                running_gp += deal_gp
                
                # 🔥 核心：根据【当前的累计GP】判断等级
                level, multiplier = calculate_commission_tier(running_gp, base)
                
                # 计算这单的佣金 (只有 Paid 才算钱，但 GP 累计不管是否 Paid)
                deal_comm = 0
                if sales_df.at[idx, 'Status'] == 'Paid':
                    deal_comm = calculate_single_deal_commission(sales_df.at[idx, 'Candidate Salary'], multiplier)
                
                # 回写到 DataFrame，方便在 Details 里展示每一单的具体情况
                sales_df.at[idx, 'Current_Cum_GP'] = running_gp
                sales_df.at[idx, 'Applied_Level'] = level
                sales_df.at[idx, 'Applied_Multiplier'] = multiplier
                sales_df.at[idx, 'Commission'] = deal_comm
                
                total_comm += deal_comm
            
            # 生成汇总数据
            completion_rate = (running_gp / target) if target > 0 else 0
            # 最终等级 (用于概览)
            final_level, _ = calculate_commission_tier(running_gp, base)
            
            financial_summary.append({
                "Consultant": c_name, "Base Salary": base, "Target": target,
                "Total GP": running_gp, "Completion": completion_rate,
                "Level": final_level, "Est. Commission": total_comm
            })
    else:
        # 如果没数据，填0
        for conf in TEAM_CONFIG:
            financial_summary.append({
                "Consultant": conf['name'], "Base Salary": conf['base_salary'], "Target": conf['base_salary']*9,
                "Total GP": 0, "Completion": 0, "Level": 0, "Est. Commission": 0
            })

    # --- TAB 1: DASHBOARD ---
    with tab_dash:
        st.markdown(f"### 🎯 Recruitment Stats (Q{quarter_num})")
        if not rec_stats_df.empty:
            rec_summary = rec_stats_df.groupby('Consultant')[['Sent', 'Int', 'Off']].sum().reset_index()
            rec_summary = rec_summary.sort_values(by='Sent', ascending=False)
            st.dataframe(rec_summary, use_container_width=True, hide_index=True)
        else: st.warning(f"No recruitment data.")

        st.divider()

        st.markdown(f"### 💰 Financial Performance (Q{quarter_num})")
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

    # --- TAB 2: DETAILS ---
    with tab_details:
        st.markdown("### 🔍 Drill Down Details")
        for conf in TEAM_CONFIG:
            c_name = conf['name']
            fin_row = df_fin[df_fin['Consultant'] == c_name].iloc[0]
            header = f"👤 {c_name} | GP: ${fin_row['Total GP']:,.0f} (Final Lvl {fin_row['Level']})"
            
            with st.expander(header):
                st.markdown("#### 💸 Commission Breakdown (Progressive)")
                
                if not sales_df.empty:
                    c_sales = sales_df[sales_df['Consultant'] == c_name].sort_values(by='Onboard Date')
                    
                    if not c_sales.empty:
                        st.dataframe(
                            c_sales[['Onboard Date', 'Company', 'Position', 'GP', 'Current_Cum_GP', 'Applied_Multiplier', 'Status', 'Commission']], 
                            use_container_width=True, hide_index=True,
                            column_config={
                                "Onboard Date": st.column_config.DateColumn("Date"),
                                "Current_Cum_GP": st.column_config.NumberColumn("Cum. GP", format="$%d"),
                                "Applied_Multiplier": st.column_config.NumberColumn("Mult.", format="x%.1f"),
                                "Commission": st.column_config.NumberColumn("Comm.", format="$%d"),
                            }
                        )
                        st.caption("注：Commission 根据该单完成时的累计 GP 实时计算倍数。")
                    else: st.info("No deals.")
                else: st.info("No deals.")
                
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
