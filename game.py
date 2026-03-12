import streamlit as st
import streamlit.components.v1 as components
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import pandas as pd
import re
import time
from datetime import datetime, timedelta
import unicodedata
import random
from typing import Dict, List, Optional, Tuple, Any

# ==========================================
# 🔧 配置区域
# ==========================================
SALES_SHEET_ID = '1jniQ-GpeMINjQMebniJ_J1eLVLQIR1NGbSjTtOFP9Q8'
SALES_TAB_NAME = 'Positions'
COMMISSION_SUMMARY_ID = '1A3K3RLlVNzCSCI-AkXAh8-K99gDSpCM7L9oNOCY0Obs'
COMMISSION_TAB_NAME = 'Commission Detail'

# 基础配置
TEAM_CONFIG_TEMPLATE = [
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

# 🎯 Recruitment Goals
# Individual Goal: 29 per month * 3 = 87 per Quarter
QUARTERLY_INDIVIDUAL_GOAL = 87
QUARTERLY_GOAL_INTERN = 87

# Team Goals
# Monthly: 29 * 4 = 116
MONTHLY_GOAL = 116
# Quarterly Team: 87 * 4 = 348
QUARTERLY_TEAM_GOAL = 348

# 限流配置
API_DELAY_BASE = 0.5  # 基础延迟
API_DELAY_JITTER = 0.3  # 随机抖动
MAX_RETRIES = 5  # 最大重试次数

# ==========================================

st.set_page_config(page_title="Fill The Pit", page_icon="🎮", layout="wide")

# --- 🎨 PLAYFUL CSS STYLING ---
st.markdown("""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Press+Start+2P&display=swap');
    @import url('https://fonts.googleapis.com/css2?family=Fredoka+One&display=swap');

    .stApp {
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        font-family: 'Press Start 2P', monospace;
    }

    h1 {
        text-shadow: 4px 4px 0px #000000;
        color: #FFD700 !important;
        text-align: center;
        font-size: 3.5em !important;
        margin-bottom: 20px;
        -webkit-text-stroke: 2px #000;
    }

     .stButton {
        display: flex;
        justify-content: center;
        width: 100%;
        margin-left: 200px; 
    }
    .stButton>button {
        background-color: #FF4757;
        color: white;
        border: 4px solid #000;
        border-radius: 15px;
        font-family: 'Press Start 2P', monospace;
        font-size: 24px !important; 
        padding: 20px 40px !important; 
        box-shadow: 0px 8px 0px #a71c2a;
        transition: all 0.1s;
        width: 100%;
    }
    .stButton>button:hover {
        transform: translateY(4px);
        box-shadow: 0px 4px 0px #a71c2a;
        background-color: #ff6b81;
        color: #FFF;
        border-color: #000;
    }
    .stButton>button:active {
        transform: translateY(8px);
        box-shadow: 0px 0px 0px #a71c2a;
    }

    /* --- PROGRESS BARS --- */
    .pit-container {
        background-color: #eee;
        border: 3px solid #000;
        border-radius: 12px;
        width: 100%;
        position: relative;
        margin-bottom: 12px;
        box-shadow: 4px 4px 0px rgba(0,0,0,0.2);
        overflow: hidden;
    }

    .pit-height-std { height: 25px; }
    .pit-height-boss { height: 60px; border-width: 4px; }

    @keyframes barberpole {
        from { background-position: 0 0; }
        to { background-position: 50px 50px; }
    }

    @keyframes rainbow-move {
        0% { background-position: 0% 50%; }
        50% { background-position: 100% 50%; }
        100% { background-position: 0% 50%; }
    }

    .pit-fill-boss {
        background: linear-gradient(270deg, #ff6b6b, #feca57, #48dbfb, #ff9ff3, #54a0ff);
        background-size: 400% 400%;
        animation: rainbow-move 6s ease infinite;
        height: 100%;
        display: flex;
        align-items: center;
        justify-content: flex-end;
    }

    .pit-fill-season { 
        background-image: linear-gradient(45deg, #3742fa 25%, #5352ed 25%, #5352ed 50%, #3742fa 50%, #3742fa 75%, #5352ed 75%, #5352ed 100%);
        background-size: 50px 50px;
        animation: barberpole 3s linear infinite;
        height: 100%; 
        display: flex; 
        align-items: center; 
        justify-content: flex-end; 
    }

    .money-fill { 
        background-image: linear-gradient(45deg, #2ed573 25%, #7bed9f 25%, #7bed9f 50%, #2ed573 50%, #2ed573 75%, #7bed9f 75%, #7bed9f 100%);
        background-size: 50px 50px;
        animation: barberpole 4s linear infinite;
        height: 100%; 
        display: flex; 
        align-items: center; 
        justify-content: flex-end; 
    }

    .cv-fill {
        background-image: linear-gradient(45deg, #ff9ff3 25%, #f368e0 25%, #f368e0 50%, #ff9ff3 50%, #ff9ff3 75%, #f368e0 75%, #f368e0 100%);
        background-size: 50px 50px;
        animation: barberpole 3s linear infinite;
        height: 100%;
        display: flex;
        align-items: center;
        justify-content: flex-end;
    }

    .cat-squad {
        margin-right: 10px;
        font-size: 24px;
        filter: drop-shadow(2px 2px 0px rgba(0,0,0,0.5));
    }

    /* --- CARDS --- */
    .player-card {
        background-color: #FFFFFF;
        border: 4px solid #000;
        border-radius: 15px;
        padding: 20px;
        margin-bottom: 30px;
        color: #333;
        box-shadow: 8px 8px 0px rgba(0,0,0,0.2);
        transition: transform 0.2s;
    }
    .player-card:hover {
        transform: translateY(-2px);
    }

    .card-border-1 { border-bottom: 6px solid #ff6b6b; }
    .card-border-2 { border-bottom: 6px solid #feca57; }
    .card-border-3 { border-bottom: 6px solid #48dbfb; }
    .card-border-4 { border-bottom: 6px solid #ff9ff3; }

    .player-header {
        display: flex;
        justify-content: space-between;
        align-items: center;
        margin-bottom: 15px;
        border-bottom: 2px dashed #ddd;
        padding-bottom: 10px;
    }
    .player-name {
        font-size: 1.1em;
        font-weight: bold;
        color: #2d3436;
    }

    .status-badge-pass {
        background-color: #2ed573;
        color: white;
        padding: 8px 12px;
        border-radius: 20px;
        border: 2px solid #000;
        font-size: 0.6em;
        box-shadow: 2px 2px 0px #000;
        animation: bounce 1s infinite alternate;
    }
    @keyframes bounce { from { transform: translateY(0); } to { transform: translateY(-2px); } }

    .status-badge-loading {
        background-color: #feca57;
        color: #000;
        padding: 8px 12px;
        border-radius: 20px;
        border: 2px solid #000;
        font-size: 0.6em;
        box-shadow: 2px 2px 0px #000;
    }

    .sub-label {
        font-family: 'Fredoka One', sans-serif;
        font-size: 0.8em;
        color: #FFFFFF;
        margin-bottom: 5px;
        text-transform: uppercase;
        letter-spacing: 1px;
        text-shadow: 1px 1px 0px #000;
    }

    .comm-unlocked {
        background-color: #fff4e6;
        border: 2px solid #ff9f43;
        border-radius: 10px;
        color: #e67e22;
        text-align: center;
        padding: 10px;
        margin-top: 15px;
        font-weight: bold;
        font-size: 0.9em;
        box-shadow: inset 0 0 10px #ffeaa7;
    }
    .comm-locked {
        background-color: #f1f2f6;
        border: 2px solid #ced6e0;
        border-radius: 10px;
        color: #a4b0be;
        text-align: center;
        padding: 10px;
        margin-top: 15px;
        font-size: 0.8em;
    }

    .header-bordered {
        background-color: #FFFFFF;
        border: 4px solid #000;
        border-radius: 15px;
        box-shadow: 6px 6px 0px #000000;
        padding: 20px;
        text-align: center;
        margin-bottom: 25px;
        color: #2d3436;
        font-size: 1.2em;
    }

    .stat-card {
        background-color: #fff;
        border: 3px solid #000;
        border-radius: 10px;
        padding: 10px;
        text-align: center;
        box-shadow: 4px 4px 0px rgba(0,0,0,0.1);
    }
    .stat-val { color: #000; font-size: 1.2em; font-weight: bold; }
    .stat-name { color: #555; font-size: 0.8em; }

    .dataframe { font-family: 'Press Start 2P', monospace !important; font-size: 0.8em !important; }
    </style>
    """, unsafe_allow_html=True)


# ==========================================
# 🧮 工具函数
# ==========================================
def exponential_backoff(retry_count: int) -> float:
    """指数退避算法计算延迟"""
    delay = (2 ** retry_count) * API_DELAY_BASE + random.uniform(0, API_DELAY_JITTER)
    return min(delay, 10)  # 最大延迟10秒

def safe_google_api_call(func, *args, **kwargs) -> Any:
    """安全调用Google API，处理限流和重试"""
    for retry in range(MAX_RETRIES):
        try:
            # 添加随机延迟避免限流
            time.sleep(API_DELAY_BASE + random.uniform(0, API_DELAY_JITTER))
            return func(*args, **kwargs)
        except Exception as e:
            if "429" in str(e) or "quota" in str(e).lower() or "limit" in str(e).lower():
                wait_time = exponential_backoff(retry)
                st.warning(f"API限流，{wait_time:.1f}秒后重试 (第{retry+1}/{MAX_RETRIES}次)")
                time.sleep(wait_time)
                continue
            else:
                st.error(f"API调用失败: {str(e)}")
                return None
    st.error(f"达到最大重试次数 ({MAX_RETRIES})，API调用失败")
    return None

# ==========================================
# 🧮 逻辑函数
# ==========================================

def normalize_text(text):
    """标准化文本（去除重音符号、转小写）"""
    if pd.isna(text):
        return ""
    return ''.join(c for c in unicodedata.normalize('NFD', str(text)) if unicodedata.category(c) != 'Mn').lower()


def get_payout_date_from_month_key(month_key):
    """从月份标识（YYYY-MM）获取佣金发放日期（次月15号）"""
    try:
        dt = datetime.strptime(str(month_key), "%Y-%m")
        year = dt.year + (dt.month // 12)
        month = (dt.month % 12) + 1
        return datetime(year, month, 15)
    except Exception as e:
        st.warning(f"解析月份 {month_key} 失败: {e}")
        return None


def calculate_commission_tier(total_gp, base_salary, is_team_lead=False):
    """计算佣金层级"""
    if is_team_lead:
        t1, t2, t3 = 4.5, 6.75, 11.25  # Team Lead 门槛更低
    else:
        t1, t2, t3 = 9.0, 13.5, 22.5  # 普通顾问门槛

    if total_gp < t1 * base_salary:
        return 0, 0  # 0级：无佣金
    elif total_gp < t2 * base_salary:
        return 1, 1  # 1级：1倍佣金
    elif total_gp < t3 * base_salary:
        return 2, 2  # 2级：2倍佣金
    else:
        return 3, 3  # 3级：3倍佣金


def calculate_single_deal_commission(candidate_salary, multiplier):
    """计算单笔交易佣金"""
    if multiplier == 0:
        return 0

    # 基础佣金计算规则
    if candidate_salary < 20000:
        base_comm = 1000
    elif candidate_salary < 30000:
        base_comm = candidate_salary * 0.05
    elif candidate_salary < 50000:
        base_comm = candidate_salary * 1.5 * 0.05
    else:
        base_comm = candidate_salary * 2.0 * 0.05

    return base_comm * multiplier


def calculate_consultant_performance(all_sales_df, consultant_name, base_salary, quarterly_cv_count, role,
                                     is_team_lead=False):
    """计算顾问绩效（修复原代码bug）"""
    # 修复：原代码使用了未定义的sales_df变量
    sales_df = all_sales_df.copy() if all_sales_df is not None else pd.DataFrame()
    
    # 1. 先检查关键列是否存在
    if sales_df.empty or 'Consultant' not in sales_df.columns:
        return {
            "Consultant": consultant_name,
            "Booked GP": 0,
            "Paid GP": 0,
            "Level": 0,
            "Target Achieved": 0.0,
            "Is Qualified": False,
            "Est. Commission": 0
        }
    
    # 1. 基础参数
    is_intern = (role == "Intern")
    target_multiplier = 4.5 if is_team_lead else 9.0
    financial_target = base_salary * target_multiplier

    # 2. 获取该顾问的销售数据
    c_sales = sales_df[sales_df['Consultant'] == consultant_name].copy()
    booked_gp = c_sales['GP'].sum() if not c_sales.empty else 0

    # 3. 达标判断
    is_qualified = False
    target_achieved_pct = 0.0

    if is_intern:
        # 实习生只看CV数量
        if quarterly_cv_count >= QUARTERLY_GOAL_INTERN:
            is_qualified = True
            target_achieved_pct = 100.0
        else:
            target_achieved_pct = (quarterly_cv_count / QUARTERLY_GOAL_INTERN) * 100
    else:
        # 全职/主管：GP或CV任一达标即可
        financial_pct = (booked_gp / financial_target * 100) if financial_target > 0 else 0
        recruitment_pct = (quarterly_cv_count / QUARTERLY_INDIVIDUAL_GOAL * 100)

        if financial_pct >= 100 or recruitment_pct >= 100:
            is_qualified = True
            target_achieved_pct = max(financial_pct, recruitment_pct)
        else:
            target_achieved_pct = max(financial_pct, recruitment_pct)

    # 4. 佣金计算
    paid_gp = 0
    total_comm = 0
    current_level = 0

    if not is_intern:  # 实习生无佣金
        if not c_sales.empty:
            c_sales['Final Comm'] = 0.0
            c_sales['Commission Day Obj'] = pd.NaT

            # 筛选已付款的交易
            paid_sales = c_sales[c_sales['Status'] == 'Paid'].copy()

            if not paid_sales.empty:
                # 处理付款日期
                paid_sales['Payment Date Obj'] = pd.to_datetime(paid_sales['Payment Date'], errors='coerce')
                paid_sales = paid_sales.dropna(subset=['Payment Date Obj']).sort_values(by='Payment Date Obj')
                paid_sales['Pay_Month_Key'] = paid_sales['Payment Date Obj'].dt.to_period('M')
                unique_months = sorted(paid_sales['Pay_Month_Key'].unique())

                running_paid_gp = 0
                pending_indices = []

                # 按月份累计计算佣金层级
                for month_key in unique_months:
                    month_deals = paid_sales[paid_sales['Pay_Month_Key'] == month_key]
                    month_new_gp = month_deals['GP'].sum()
                    running_paid_gp += month_new_gp
                    pending_indices.extend(month_deals.index.tolist())

                    # 计算当前层级
                    level, multiplier = calculate_commission_tier(running_paid_gp, base_salary, is_team_lead)

                    if level > 0:
                        payout_date = get_payout_date_from_month_key(str(month_key))
                        # 计算每笔交易的最终佣金
                        for idx in pending_indices:
                            row = paid_sales.loc[idx]
                            deal_comm = calculate_single_deal_commission(row['Candidate Salary'], multiplier) * row[
                                'Percentage']
                            paid_sales.at[idx, 'Final Comm'] = deal_comm
                            paid_sales.at[idx, 'Commission Day Obj'] = payout_date
                        pending_indices = []

                paid_gp = running_paid_gp
                current_level, _ = calculate_commission_tier(booked_gp, base_salary, is_team_lead)

                # 只计算已到发放日期的佣金
                limit_date = datetime.now() + timedelta(days=20)
                for idx, row in paid_sales.iterrows():
                    comm_date = row['Commission Day Obj']
                    if pd.notnull(comm_date) and comm_date <= limit_date:
                        total_comm += row['Final Comm']

            # 团队主管额外佣金
            if is_team_lead and not sales_df.empty:
                mask = (sales_df['Status'] == 'Paid') & \
                       (sales_df['Consultant'] != consultant_name) & \
                       (sales_df['Consultant'] != "Estela Peng")

                pot_overrides = sales_df[mask].copy()
                pot_overrides['Payment Date Obj'] = pd.to_datetime(pot_overrides['Payment Date'], errors='coerce')

                for _, row in pot_overrides.iterrows():
                    pay_date = row['Payment Date Obj']
                    if pd.isna(pay_date):
                        continue
                    comm_pay_obj = datetime(
                        pay_date.year + (pay_date.month // 12),
                        (pay_date.month % 12) + 1,
                        15
                    )
                    if comm_pay_obj <= (datetime.now() + timedelta(days=20)):
                        total_comm += 1000

    # 5. 最终佣金：未达标则清零
    if not is_qualified:
        total_comm = 0

    return {
        "Consultant": consultant_name,
        "Booked GP": booked_gp,
        "Paid GP": paid_gp,
        "Level": current_level,
        "Target Achieved": target_achieved_pct,
        "Is Qualified": is_qualified,
        "Est. Commission": total_comm
    }


# --- 🔗 数据获取 ---
def connect_to_google():
    """连接Google Sheets（增加重试和错误处理）"""
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    try:
        if "gcp_service_account" in st.secrets:
            creds_dict = dict(st.secrets["gcp_service_account"])
            creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
            # 使用安全调用包装
            client = safe_google_api_call(gspread.authorize, creds)
            return client
        else:
            st.error("未配置GCP服务账号密钥")
            return None
    except Exception as e:
        st.error(f"Google连接失败: {str(e)}")
        return None


def get_quarter_info():
    """获取当前季度信息"""
    today = datetime.now()
    year = today.year
    month = today.month
    quarter = (month - 1) // 3 + 1
    start_month = (quarter - 1) * 3 + 1
    end_month = start_month + 2
    tabs = [f"{year}{m:02d}" for m in range(start_month, end_month + 1)]
    return tabs, quarter, start_month, end_month, year


def get_all_month_tabs(client, consultant_config):
    """获取顾问工作表中所有有效月份标签（格式：YYYYMM）"""
    try:
        # 使用安全调用包装
        sheet = safe_google_api_call(client.open_by_key, consultant_config['id'])
        if not sheet:
            return []
            
        all_tabs = safe_google_api_call(lambda: [ws.title for ws in sheet.worksheets()])
        
        if not all_tabs:
            return []

        # 筛选出 YYYYMM 格式的月份标签（正则匹配）
        month_pattern = re.compile(r'^\d{6}$')  # 匹配 6 位数字（202603 这种格式）
        valid_month_tabs = [tab for tab in all_tabs if month_pattern.match(tab)]

        # 按时间排序（旧→新）
        valid_month_tabs.sort()
        return valid_month_tabs
    except Exception as e:
        st.error(f"获取 {consultant_config['name']} 的所有月份标签失败: {e}")
        return []


def fetch_role_from_personal_sheet(client, sheet_id):
    """从个人表格获取角色信息（实习生/全职/主管）"""
    try:
        # 使用安全调用包装
        sheet = safe_google_api_call(client.open_by_key, sheet_id)
        if not sheet:
            return "Full-Time", False, "Consultant"
            
        # 优先找Credentials工作表，否则用第一个
        try:
            ws = safe_google_api_call(sheet.worksheet, 'Credentials')
        except:
            ws = safe_google_api_call(sheet.get_worksheet, 0)
        
        if not ws:
            return "Full-Time", False, "Consultant"

        # 读取标题行
        header_vals = safe_google_api_call(ws.range, 'A1:B1')
        if not header_vals:
            return "Full-Time", False, "Consultant"
            
        a1_val = header_vals[0].value.strip().lower()
        b1_val = header_vals[1].value.strip()

        title_text = "Consultant"
        if "title" in a1_val:
            title_text = b1_val

        # 判断角色类型
        is_intern = "intern" in title_text.lower()
        is_lead = "team lead" in title_text.lower() or "manager" in title_text.lower()

        role = "Intern" if is_intern else "Full-Time"
        return role, is_lead, title_text.title()

    except Exception as e:
        st.warning(f"获取角色信息失败: {str(e)}")
        return "Full-Time", False, "Consultant"


def fetch_consultant_data(client, consultant_config, target_tab):
    """获取顾问的CV数据（增加错误处理和月份信息）"""
    sheet_id = consultant_config['id']
    target_key = consultant_config.get('keyword', 'Name').strip()
    COMPANY_KEYS = ["Company", "Client", "Cliente", "公司名称", "客户"]
    POSITION_KEYS = ["Position", "Role", "Posición", "职位", "岗位"]

    try:
        # 使用安全调用包装
        sheet = safe_google_api_call(client.open_by_key, sheet_id)
        if not sheet:
            return 0, []
            
        worksheet = safe_google_api_call(sheet.worksheet, target_tab)
        if not worksheet:
            st.warning(f"工作表 {target_tab} 不存在")
            return 0, []

        rows = safe_google_api_call(worksheet.get_all_values)
        if not rows:
            return 0, []
            
        count = 0
        details = []
        current_company = "Unknown"
        current_position = "Unknown"

        for row in rows:
            if not row:
                continue

            cleaned_row = [str(x).strip() for x in row]

            # 查找关键字列（如Name/姓名）
            try:
                key_index = cleaned_row.index(target_key)
                # 统计关键字右侧非空单元格数量（CV数）
                candidates = [x for x in cleaned_row[key_index + 1:] if x]
                count += len(candidates)

                # 记录明细（增加月份信息）
                for _ in range(len(candidates)):
                    details.append({
                        "Consultant": consultant_config['name'],
                        "Company": current_company,
                        "Position": current_position,
                        "Count": 1,
                        "Month": target_tab  # 增加月份字段
                    })

            except ValueError:
                # 非关键字行，更新公司/职位信息
                first_cell = cleaned_row[0] if len(cleaned_row) > 0 else ""
                if first_cell in COMPANY_KEYS:
                    current_company = cleaned_row[1] if len(cleaned_row) > 1 else "Unknown"
                elif first_cell in POSITION_KEYS:
                    current_position = cleaned_row[1] if len(cleaned_row) > 1 else "Unknown"

        return count, details
    except Exception as e:
        st.error(f"获取 {consultant_config['name']} 数据失败: {e}")
        return 0, []


def fetch_financial_df(client, start_m, end_m, year):
    """获取财务数据（GP/薪资/佣金）"""
    try:
        # 使用安全调用包装
        sheet = safe_google_api_call(client.open_by_key, SALES_SHEET_ID)
        if not sheet:
            return pd.DataFrame()
            
        try:
            ws = safe_google_api_call(sheet.worksheet, SALES_TAB_NAME)
        except:
            ws = safe_google_api_call(sheet.get_worksheet, 0)
        
        if not ws:
            return pd.DataFrame()

        rows = safe_google_api_call(ws.get_all_values)
        if not rows:
            return pd.DataFrame()
            
        # 列索引初始化
        col_cons = -1
        col_onboard = -1
        col_pay = -1
        col_sal = -1
        col_pct = -1
        found_header = False
        records = []

        for row in rows:
            if not any(cell.strip() for cell in row):
                continue

            row_lower = [str(x).strip().lower() for x in row]

            # 查找表头行
            if not found_header:
                if any("linkeazi" in c for c in row_lower) and any("onboarding" in c for c in row_lower):
                    for idx, cell in enumerate(row_lower):
                        if "linkeazi" in cell and "consultant" in cell:
                            col_cons = idx
                        if "onboarding" in cell and "date" in cell:
                            col_onboard = idx
                        if "candidate" in cell and "salary" in cell:
                            col_sal = idx
                        if "payment" in cell and "onboard" not in cell:
                            col_pay = idx
                        if "percentage" in cell or "pct" in cell or cell == "%":
                            col_pct = idx
                    found_header = True
                    continue
            else:
                # 数据行处理
                row_upper = " ".join(row_lower).upper()
                if "POSITION" in row_upper and "PLACED" not in row_upper:
                    break
                if len(row) <= max(col_cons, col_onboard, col_sal):
                    continue

                # 顾问姓名匹配
                consultant_name = row[col_cons].strip()
                if not consultant_name:
                    continue

                # 入职日期解析
                onboard_str = row[col_onboard].strip()
                onboard_date = None
                for fmt in ["%Y-%m-%d", "%d/%m/%Y", "%Y/%m/%d", "%m/%d/%Y", "%d-%b-%y"]:
                    try:
                        onboard_date = datetime.strptime(onboard_str, fmt)
                        break
                    except:
                        pass
                if not onboard_date:
                    continue

                # 筛选本季度数据
                if not (onboard_date.year == year and start_m <= onboard_date.month <= end_m):
                    continue

                # 标准化姓名匹配
                matched = "Unknown"
                c_norm = normalize_text(consultant_name)
                for conf in TEAM_CONFIG_TEMPLATE:
                    conf_norm = normalize_text(conf['name'])
                    if conf_norm in c_norm or c_norm in conf_norm:
                        matched = conf['name']
                        break
                    if conf_norm.split()[0] in c_norm:
                        matched = conf['name']
                        break
                if matched == "Unknown":
                    continue

                # 薪资处理
                salary_raw = str(row[col_sal]).replace(',', '').replace('$', '').replace('MXN', '').strip()
                try:
                    salary = float(salary_raw)
                except:
                    salary = 0

                # 百分比处理
                pct_val = 1.0
                if col_pct != -1 and len(row) > col_pct:
                    p_str = str(row[col_pct]).replace('%', '').strip()
                    try:
                        p_float = float(p_str)
                        pct_val = p_float / 100.0 if p_float > 1.0 else p_float
                    except:
                        pct_val = 1.0

                # GP计算
                base_gp_factor = 1.0 if salary < 20000 else 1.5
                calc_gp = salary * base_gp_factor * pct_val

                # 付款状态
                pay_date_str = row[col_pay].strip() if (col_pay != -1 and len(row) > col_pay) else ""
                status = "Paid" if len(pay_date_str) > 5 else "Pending"

                records.append({
                    "Consultant": matched,
                    "GP": calc_gp,
                    "Candidate Salary": salary,
                    "Percentage": pct_val,
                    "Onboard Date": onboard_date,
                    "Payment Date": pay_date_str,
                    "Status": status
                })

        return pd.DataFrame(records)
    except Exception as e:
        st.error(f"财务数据获取失败: {e}")
        return pd.DataFrame()


def get_monthly_commission(client, consultant_name, month_key):
    """从汇总表获取月度佣金"""
    try:
        # 使用安全调用包装
        sheet = safe_google_api_call(client.open_by_key, COMMISSION_SUMMARY_ID)
        if not sheet:
            return 0.0
            
        ws = safe_google_api_call(sheet.worksheet, COMMISSION_TAB_NAME)
        if not ws:
            return 0.0
            
        data = safe_google_api_call(ws.get_all_records)
        if not data:
            return 0.0
            
        df = pd.DataFrame(data)

        if df.empty:
            return 0.0

        # 标准化匹配
        c_norm = normalize_text(consultant_name)
        match = df[
            (df['Consultant'].apply(normalize_text) == c_norm) &
            (df['Month'].astype(str) == month_key)
            ]

        return float(match.iloc[0]['Final_Commission']) if not match.empty else 0.0
    except Exception as e:
        st.warning(f"获取月度佣金失败: {e}")
        return 0.0


# --- UI渲染函数 ---
def render_bar(current_total, goal, color_class, label_text, is_monthly_boss=False):
    """渲染进度条"""
    percent = (current_total / goal) * 100 if goal > 0 else 0
    display_pct = min(percent, 100)
    container_cls = "pit-container"
    height_cls = "pit-height-boss" if is_monthly_boss else "pit-height-std"
    cats = "🎉" if percent >= 100 else ""

    st.markdown(f"""
    <div style="margin-bottom: 5px;">
        <div class="sub-label">{label_text}  ({percent:.1f}%)</div>
        <div class="{container_cls} {height_cls}">
            <div class="{color_class}" style="width: {display_pct}%;">
                <div class="cat-squad" style="top: {'15px' if is_monthly_boss else '5px'}">{cats}</div>
            </div>
        </div>
    </div>
    """, unsafe_allow_html=True)


def render_player_card(conf, fin_summary, quarterly_cv_count, card_index, monthly_commission=0.0):
    """渲染玩家卡片（顾问绩效）"""
    name = conf['name']
    role = conf.get('role', 'Full-Time')
    is_team_lead = conf.get('is_team_lead', False)
    is_intern = (role == 'Intern')
    base_salary = conf.get('base_salary', 0)
    is_qualified = monthly_commission > 0

    # 财务数据
    booked_gp = fin_summary.get("Booked GP", 0)
    target_gp = base_salary * (4.5 if is_team_lead else 9.0)

    # 状态文本
    crown = "👑" if is_team_lead else ""
    role_tag = "🎓 INTERN" if is_intern else "💼 FULL-TIME"
    title_display = conf.get('title_display', role_tag)
    current_level, _ = calculate_commission_tier(booked_gp, base_salary, is_team_lead)

    if current_level > 0:
        status_text = f"LEVEL {current_level}! 🌟"
        badge_class = "status-badge-pass"
    elif quarterly_cv_count >= 87:
        status_text = "TARGET MET! 🎯"
        badge_class = "status-badge-pass"
    else:
        status_text = "HUNTING... 🚀"
        badge_class = "status-badge-loading"

    # 卡片样式
    border_class = f"card-border-{(card_index % 4) + 1}"

    # 渲染卡片
    st.markdown(f"""
    <div class="player-card {border_class}">
        <div class="player-header">
            <div class="player-name">{name} {crown}</div>
            <span class="{badge_class}">{status_text}</span>
        </div>
    """, unsafe_allow_html=True)

    # 进度条
    if is_intern:
        # 实习生只显示CV进度
        render_bar(quarterly_cv_count, QUARTERLY_GOAL_INTERN, "cv-fill", "Q. CVs")
    else:
        # 全职/主管显示GP和CV进度
        render_bar(booked_gp, target_gp, "money-fill", "GP TARGET")
        st.markdown(f'<div style="font-size:0.6em; color:#666; margin-top:5px;">AND/OR RECRUITMENT GOAL:</div>',
                    unsafe_allow_html=True)
        render_bar(quarterly_cv_count, QUARTERLY_INDIVIDUAL_GOAL, "cv-fill", "Q. CVs")

    # 佣金显示
    if is_intern:
        st.markdown(f"""<div class="comm-locked" style="background:#eee; color:#aaa;">INTERNSHIP TRACK</div>""",
                    unsafe_allow_html=True)
    else:
        if monthly_commission > 0:
            st.markdown(f"""<div class="comm-unlocked">💰 UNLOCKED: ${monthly_commission:,.2f}</div>""",
                        unsafe_allow_html=True)
        else:
            st.markdown(f"""<div class="comm-locked">🔒 LOCKED (TARGET NOT MET)</div>""",
                        unsafe_allow_html=True)

    st.markdown("</div>", unsafe_allow_html=True)



# --- 主程序 ---
def main():
    """应用主函数"""
    # 获取季度信息
    quarter_tabs, quarter_num, start_m, end_m, year = get_quarter_info()
    current_month_tab = datetime.now().strftime("%Y%m")

    # 页面标题
    st.title("👾 FILL THE PIT 👾")
    col1, col2, col3 = st.columns([1, 3, 1])
    with col2:
        start_btn = st.button(f"🚩 PRESS START")

    if start_btn:
        # 连接Google Sheets
        client = connect_to_google()
        if not client:
            return

        # 加载团队配置（含角色信息）
        active_team_config = []
        config_status = st.empty()
        config_status.info("🔐 CONNECTING TO PLAYER PROFILES...")

        for conf in TEAM_CONFIG_TEMPLATE:
            new_conf = conf.copy()
            role, is_lead, raw_title = fetch_role_from_personal_sheet(client, conf['id'])
            new_conf['role'] = role
            new_conf['is_team_lead'] = is_lead
            new_conf['title_display'] = raw_title
            active_team_config.append(new_conf)

        config_status.empty()

        # 初始化数据容器
        monthly_results = []
        quarterly_results = []
        all_month_details = []  # 实际存储全季度明细（保留原变量名）
        consultant_cv_counts = {}

        # 加载数据
        with st.spinner(f"🛰️ SCANNING ALL HISTORICAL DATA..."):
            # 1. 获取招聘数据（CV数）- 修改为遍历所有历史月份
            for consultant in active_team_config:
                total_count = 0  # 所有历史月份总CV数
                all_details = []  # 所有历史月份明细
                m_count = 0  # 当月数量

                # 获取该顾问的所有有效月份标签
                all_month_tabs = get_all_month_tabs(client, consultant)
                if not all_month_tabs:
                    st.warning(f"{consultant['name']} 无有效月份数据")
                    monthly_results.append({"name": consultant['name'], "count": 0})
                    quarterly_results.append({"name": consultant['name'], "count": 0})
                    consultant_cv_counts[consultant['name']] = 0
                    continue

                # 遍历所有历史月份
                for month_tab in all_month_tabs:
                    c_count, c_details = fetch_consultant_data(client, consultant, month_tab)
                    total_count += c_count
                    all_details.extend(c_details)  # 收集所有历史明细

                    # 记录当月数量
                    if month_tab == current_month_tab:
                        m_count = c_count

                # 汇总到全局容器
                monthly_results.append({"name": consultant['name'], "count": m_count})
                # quarterly_results 改为存储全历史总数（保留变量名避免报错）
                quarterly_results.append({"name": consultant['name'], "count": total_count})
                consultant_cv_counts[consultant['name']] = total_count
                all_month_details.extend(all_details)  # 加入所有历史明细

            # 2. 获取财务数据（这部分完全不变）
            sales_df = fetch_financial_df(client, start_m, end_m, year)

        time.sleep(0.5)

        # --- 渲染月度团队目标进度条 ---
        st.markdown(
            f'<div class="header-bordered" style="border-color: #feca57; background: #fff;">🏆 TEAM MONTHLY GOAL ({current_month_tab})</div>',
            unsafe_allow_html=True)
        pit_month_ph = st.empty()
        stats_month_ph = st.empty()

        monthly_total = sum([r['count'] for r in monthly_results])
        steps = 15

        # 进度条动画
        for step in range(steps + 1):
            curr_m = (monthly_total / steps) * step
            render_pit_html = f"""
            <div class="sub-label" style="font-size: 1.2em; text-align:center;">{int(curr_m)} / {MONTHLY_GOAL} CVs</div>
            <div class="pit-container pit-height-boss">
                <div class="pit-fill-boss" style="width: {min((curr_m / MONTHLY_GOAL) * 100, 100)}%;">
                    <div class="cat-squad" style="font-size: 40px; top: 5px;">🔥</div>
                </div>
            </div>
            """
            pit_month_ph.markdown(render_pit_html, unsafe_allow_html=True)

            # 最后一步显示团队成员数据
            if step == steps:
                cols_m = stats_month_ph.columns(len(monthly_results))
                for idx, res in enumerate(monthly_results):
                    with cols_m[idx]:
                        st.markdown(
                            f"""<div class="stat-card"><div class="stat-name">{res['name']}</div><div class="stat-val">{res['count']}</div></div>""",
                            unsafe_allow_html=True)
            time.sleep(0.01)

        # 目标达成庆祝
        if monthly_total >= MONTHLY_GOAL:
            st.balloons()
            time.sleep(1)

        # --- 渲染季度团队目标进度条 ---
        quarterly_total = sum([r['count'] for r in quarterly_results])
        st.markdown(
            f'<div class="header-bordered" style="border-color: #54a0ff; background: #fff; margin-top: 20px;">🌊 TEAM QUARTERLY GOAL (Q{quarter_num})</div>',
            unsafe_allow_html=True)
        pit_quarter_ph = st.empty()

        # 季度进度条动画
        for step in range(steps + 1):
            curr_q = (quarterly_total / steps) * step
            render_q_html = f"""
            <div class="sub-label" style="font-size: 1.2em; text-align:center;">{int(curr_q)} / {QUARTERLY_TEAM_GOAL} CVs</div>
            <div class="pit-container pit-height-boss">
                <div class="pit-fill-season" style="width: {min((curr_q / QUARTERLY_TEAM_GOAL) * 100, 100)}%;">
                    <div class="cat-squad" style="font-size: 40px; top: 5px;">🌊</div>
                </div>
            </div>
            """
            pit_quarter_ph.markdown(render_q_html, unsafe_allow_html=True)
            time.sleep(0.01)

        # --- 渲染个人绩效卡片 ---
        st.markdown("<br>", unsafe_allow_html=True)
        st.markdown(
            f'<div class="header-bordered" style="border-color: #48dbfb;">❄️ PLAYER STATS (Q{quarter_num})</div>',
            unsafe_allow_html=True)

        row1 = st.columns(2)
        row2 = st.columns(2)
        all_cols = row1 + row2

        for idx, conf in enumerate(active_team_config):
            c_name = conf['name']
            c_cvs = consultant_cv_counts.get(c_name, 0)
            
            # 调用绩效计算函数
            perf_summary = calculate_consultant_performance(
                sales_df, c_name, conf['base_salary'], c_cvs, conf['role'], conf['is_team_lead']
            )

            # 获取月度佣金
            current_month_key = datetime.now().strftime("%Y%m")
            monthly_commission = get_monthly_commission(client, c_name, current_month_key)

            # 渲染卡片
            with all_cols[idx]:
                render_player_card(conf, perf_summary, c_cvs, idx, monthly_commission)

        # --- 渲染数据明细 ---
        if all_month_details:
            st.markdown("---")

            # 按顾问查看明细（仅当月）
            with st.expander(f"📜 MISSION LOGS ({current_month_tab})", expanded=False):
                df_all = pd.DataFrame(all_month_details)
                df_month = df_all[df_all['Month'] == current_month_tab]  # 仅当月数据
                tab_names = [c['name'] for c in active_team_config]
                tabs = st.tabs(tab_names)

                for idx, tab in enumerate(tabs):
                    with tab:
                        current_consultant = tab_names[idx]
                        df_c = df_month[df_month['Consultant'] == current_consultant]
                        if not df_c.empty:
                            df_agg = df_c.groupby(['Company', 'Position'])['Count'].sum().reset_index()
                            df_agg = df_agg.sort_values(by='Count', ascending=False)
                            df_agg['Count'] = df_agg['Count'].astype(str)
                            st.dataframe(
                                df_agg,
                                use_container_width=True,
                                hide_index=True,
                                column_config={
                                    "Company": st.column_config.TextColumn("TARGET COMPANY"),
                                    "Position": st.column_config.TextColumn("TARGET ROLE"),
                                    "Count": st.column_config.TextColumn("CVs")
                                }
                            )
                        else:
                            st.info(f"NO DATA FOR {current_consultant}")

            # 团队岗位汇总（所有历史月份）
            with st.expander("📊 CV SUMMARY BY POSITIONS", expanded=False):
                df_total = pd.DataFrame(all_month_details)
                summary_agg = df_total.groupby(['Company', 'Position'])['Count'].sum().reset_index()
                summary_agg = summary_agg.sort_values(by='Count', ascending=False)
                summary_agg.columns = ['CLIENT/COMPANY', 'TARGET ROLE', 'TOTAL CVs']

                st.dataframe(
                    summary_agg,
                    use_container_width=True,
                    hide_index=True,
                    column_config={
                        "TOTAL CVs": st.column_config.NumberColumn(
                            "TOTAL CVs",
                            help="Total number of CVs across the whole team (All Historical Months)",
                            format="%d ⭐"
                        )
                    }
                )

        elif monthly_total == 0:
            st.markdown("---")
            st.info("NO DATA FOUND IN HISTORICAL RECORDS.")


if __name__ == "__main__":
    main()
