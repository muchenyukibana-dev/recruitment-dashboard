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
# 请确保这里填的是包含 PLACED POSITIONS 的那个总表名字 (比如 'Positions' 或 'Sheet1')
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

# 设置页面 (必须在第一行)
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
    if total_gp < 3 * base_salary:
        return 0, 0
    elif total_gp < 4.5 * base_salary:
        return 1, 1
    elif total_gp < 7.5 * base_salary:
        return 2, 2
    else:
        return 3, 3

def calculate_single_deal_commission(candidate_salary, multiplier):
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

# --- 📥 获取招聘数据 (Name行统计) ---
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
        
        COMPANY_KEYS = ["Company", "Client", "Cliente", "公司", "客户", "客户名称"]
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

# --- FETCH SALES DATA (DIAGNOSTIC & ROBUST VERSION) ---
def fetch_sales_data(client, quarter_start_month, quarter_end_month, year):
    # 调试信息：显示正在查找的时间范围
    st.info(f"🔍 正在扫描业绩数据... 目标年份: {year}, 月份: {quarter_start_month}-{quarter_end_month}")
    
    try:
        sheet = client.open_by_key(SALES_SHEET_ID)
        try:
            ws = sheet.worksheet(SALES_TAB_NAME)
        except:
            ws = sheet.get_worksheet(0)
            
        rows = ws.get_all_values()
        
        found_section = False
        found_header = False
        col_cons = -1; col_date = -1; col_sal = -1
        sales_records = []
        
        # 宽容的关键词列表 (全部转小写对比)
        KEYS_CONS = ["linkeazi", "consultant", "owner", "recruiter", "顾问"]
        KEYS_DATE = ["payment", "date", "paid", "付款", "日期"]
        KEYS_SALARY = ["salary", "base", "wage", "monthly", "薪资", "底薪", "月薪"]

        for i, row in enumerate(rows):
            # 将整行转为文本并大写，用于找区域标题
            row_str = " ".join([str(x).strip() for x in row]).upper()
            
            # 1. 寻找区域入口 (只要包含 PLACED 和 POSITION)
            if not found_section:
                if "PLACED" in row_str and "POSITION" in row_str:
                    found_section = True
                    st.success(f"✅ 在第 {i+1} 行找到了 'PLACED POSITIONS' 区域！")
                continue # 继续找下一行
            
            # 2. 在区域内寻找表头
            if found_section and not found_header:
                row_lower = [str(x).strip().lower() for x in row]
                
                # 打印当前行，看看程序读到了什么（调试用）
                # st.write(f"正在检查第 {i+1} 行表头: {row_lower}")

                # 尝试匹配列索引
                for idx, cell in enumerate(row_lower):
                    if any(k in cell for k in KEYS_CONS): col_cons = idx
                    if any(k in cell for k in KEYS_DATE): col_date = idx
                    if any(k in cell for k in KEYS_SALARY): col_sal = idx
                
                # 只要找到了 顾问列 和 薪资列，就认为找到了表头
                if col_cons != -1 and col_sal != -1:
                    found_header = True
                    # 如果日期列没找到，尝试默认用第7列(假设)或者报错提示
                    if col_date == -1:
                        st.error(f"⚠️ 找到了顾问和薪资列，但没找到 'Payment' 列。请检查表头是否包含 Payment 或 Date 字样。")
                    else:
                        st.success(f"✅ 成功锁定表头 (第 {i+1} 行)! 顾问列:{col_cons+1}, 日期列:{col_date+1}, 薪资列:{col_sal+1}")
                continue

            # 3. 读取数据
            if found_header:
                # 如果遇到新的大标题，停止
                if "POSITION" in row_str and "PLACED" not in row_str:
                    st.info(f"🛑 在第 {i+1} 行区域结束。")
                    break 
                
                # 确保行长度足够
                if len(row) <= max(col_cons, col_date, col_sal): continue
                
                # 获取顾问名字
                consultant_name = row[col_cons].strip()
                if not consultant_name: continue # 跳过空行

                # 解析日期
                date_str = row[col_date].strip()
                pay_date = None
                # 增加更多日期格式，适配各种写法
                formats = [
                    "%Y-%m-%d", "%Y/%m/%d", "%Y.%m.%d", # 2025-07-01
                    "%d-%m-%Y", "%d/%m/%Y",             # 01/07/2025
                    "%d-%b-%y", "%d-%b-%Y",             # 01-Jul-25
                    "%m/%d/%Y",                         # 07/01/2025 (美式)
                ]
                
                for fmt in formats:
                    try:
                        pay_date = datetime.strptime(date_str, fmt)
                        break
                    except: pass
                
                if not pay_date:
                    # 如果日期读不出来，打印个警告看看是不是格式怪异
                    # st.warning(f"⚠️ 跳过第 {i+1} 行：日期 '{date_str}' 无法识别")
                    continue
                
                # 检查年份和季度
                if pay_date.year == year and quarter_start_month <= pay_date.month <= quarter_end_month:
                    
                    # 解析薪资
                    salary_raw = str(row[col_sal]).replace(',', '').replace('$', '').replace('MXN', '').strip()
                    try:
                        salary = float(salary_raw)
                    except:
                        salary = 0
                    
                    # GP 计算
                    calc_gp = salary * 1.0 if salary < 20000 else salary * 1.5
                    
                    # 匹配顾问
                    matched = "Unknown"
                    for conf in TEAM_CONFIG:
                        # 模糊匹配：只要配置的名字出现在表格名字里就算（忽略大小写）
                        if conf['name'].lower() in consultant_name.lower():
                            matched = conf['name']
                            break
                    
                    if matched != "Unknown":
                        sales_records.append({
                            "Consultant": matched,
                            "GP": calc_gp,
                            "Candidate Salary": salary,
                            "Date": pay_date.strftime("%Y-%m-%d")
                        })
                    else:
                        st.warning(f"❓ 第 {i+1} 行名字 '{consultant_name}' 未在系统配置中找到。")

        return pd.DataFrame(sales_records)

    except Exception as e:
        st.error(f"系统错误: {e}")
        return pd.DataFrame()
