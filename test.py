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
import json
import hashlib
from pathlib import Path

# ==========================================
# 🔧 配置区域
# ==========================================
SALES_SHEET_ID = '1jniQ-GpeMINjQMebniJ_J1eLVLQIR1NGbSjTtOFP9Q8'
SALES_TAB_NAME = 'Positions'
COMMISSION_SUMMARY_ID = '1A3K3RLlVNzCSCI-AkXAh8-K99gDSpCM7L9oNOCY0Obs'
COMMISSION_TAB_NAME = 'Commission Detail'

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

QUARTERLY_INDIVIDUAL_GOAL = 87
QUARTERLY_GOAL_INTERN = 87
MONTHLY_GOAL = 116
QUARTERLY_TEAM_GOAL = 348

API_DELAY_BASE = 0.5
API_DELAY_JITTER = 0.3
MAX_RETRIES = 5
CACHE_DIR = Path("./cache")
CACHE_TTL = 3600  # 缓存有效期 1 小时

# ==========================================

st.set_page_config(page_title="Fill The Pit", page_icon="🎮", layout="wide")

# --- 🎨 完全保留你原来的 CSS 样式 ---
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
# 🆕 新增：识别 LIVE POSITIONS 岗位
# ==========================================
def get_live_positions(client):
    """从 SALES_SHEET_ID 中获取所有 LIVE POSITIONS 岗位列表"""
    try:
        sheet = safe_google_api_call(client.open_by_key, SALES_SHEET_ID, cache_prefix="live_pos_sheet")
        if not sheet:
            return []
        
        ws = safe_google_api_call(sheet.worksheet, SALES_TAB_NAME, cache_prefix="live_pos_ws")
        rows = safe_google_api_call(ws.get_all_values, cache_prefix="live_pos_rows")
        
        live_positions = []
        in_live_section = False
        
        # 遍历行，找到 LIVE POSITIONS 部分
        for row in rows:
            row_text = " ".join([str(x).strip().upper() for x in row if x.strip()])
            
            # 标记进入 LIVE POSITIONS 区域
            if "LIVE POSITIONS" in row_text:
                in_live_section = True
                continue
            
            # 标记离开 LIVE POSITIONS 区域（遇到其他分类）
            if in_live_section and any(keyword in row_text for keyword in ["FILLED", "ON HOLD", "CLOSED", "ARCHIVED"]):
                break
            
            # 提取 LIVE 岗位名称
            if in_live_section and len(row) >= 2 and row[1].strip():
                position_name = row[1].strip()
                if position_name and position_name.upper() != "POSITION":  # 排除表头
                    live_positions.append(normalize_text(position_name))
        
        return live_positions
    except Exception as e:
        st.error(f"获取 LIVE POSITIONS 失败: {e}")
        return []

def is_live_position(position_name, live_positions):
    """判断岗位是否属于 LIVE POSITIONS"""
    if not live_positions or not position_name:
        return False
    norm_pos = normalize_text(position_name)
    return any(norm_pos in live_pos or live_pos in norm_pos for live_pos in live_positions)

# ==========================================
# 🧮 缓存工具函数
# ==========================================
def get_cache_key(prefix, *args):
    key_str = f"{prefix}_{'_'.join(map(str, args))}"
    return hashlib.md5(key_str.encode()).hexdigest()

def load_from_cache(cache_key):
    CACHE_DIR.mkdir(exist_ok=True)
    cache_file = CACHE_DIR / f"{cache_key}.json"
    if not cache_file.exists():
        return None
    try:
        with open(cache_file, "r", encoding="utf-8") as f:
            data = json.load(f)
        if time.time() - data["timestamp"] < CACHE_TTL:
            return data["payload"]
        else:
            cache_file.unlink()
            return None
    except:
        return None

def save_to_cache(cache_key, payload):
    CACHE_DIR.mkdir(exist_ok=True)
    cache_file = CACHE_DIR / f"{cache_key}.json"
    with open(cache_file, "w", encoding="utf-8") as f:
        json.dump({
            "timestamp": time.time(),
            "payload": payload
        }, f, ensure_ascii=False)

# ==========================================
# 🧮 工具函数
# ==========================================
def exponential_backoff(retry_count):
    delay = (2 ** retry_count) * API_DELAY_BASE + random.uniform(0, API_DELAY_JITTER)
    return min(delay, 10)

def safe_google_api_call(func, *args, cache_prefix=None, **kwargs):
    if cache_prefix:
        cache_key = get_cache_key(cache_prefix, *args)
        cached = load_from_cache(cache_key)
        if cached is not None:
            return cached
    for retry in range(MAX_RETRIES):
        try:
            time.sleep(API_DELAY_BASE + random.uniform(0, API_DELAY_JITTER))
            result = func(*args, **kwargs)
            if cache_prefix and result is not None:
                save_to_cache(cache_key, result)
            return result
        except Exception as e:
            if "429" in str(e) or "quota" in str(e).lower() or "limit" in str(e).lower():
                wait = exponential_backoff(retry)
                st.warning(f"API限流，{wait:.1f}秒后重试 ({retry+1}/{MAX_RETRIES})")
                time.sleep(wait)
                continue
            else:
                st.error(f"API失败: {str(e)}")
                return None
    st.error("达到最大重试次数")
    return None

def normalize_text(text):
    if pd.isna(text):
        return ""
    return ''.join(c for c in unicodedata.normalize('NFD', str(text))
                   if unicodedata.category(c) != 'Mn').lower()

def get_payout_date_from_month_key(month_key):
    try:
        dt = datetime.strptime(str(month_key), "%Y-%m")
        year = dt.year + (dt.month // 12)
        month = (dt.month % 12) + 1
        return datetime(year, month, 15)
    except:
        return None

def calculate_commission_tier(total_gp, base_salary, is_team_lead=False):
    if is_team_lead:
        t1, t2, t3 = 4.5, 6.75, 11.25
    else:
        t1, t2, t3 = 9.0, 13.5, 22.5
    if total_gp < t1 * base_salary:
        return 0, 0
    elif total_gp < t2 * base_salary:
        return 1, 1
    elif total_gp < t3 * base_salary:
        return 2, 2
    else:
        return 3, 3

def calculate_single_deal_commission(candidate_salary, multiplier):
    if multiplier == 0:
        return 0
    if candidate_salary < 20000:
        base = 1000
    elif candidate_salary < 30000:
        base = candidate_salary * 0.05
    elif candidate_salary < 50000:
        base = candidate_salary * 1.5 * 0.05
    else:
        base = candidate_salary * 2.0 * 0.05
    return base * multiplier

def calculate_consultant_performance(all_sales_df, consultant_name, base_salary, quarterly_cv_count, role,
                                     is_team_lead=False):
    sales_df = all_sales_df.copy() if all_sales_df is not None else pd.DataFrame()
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
    is_intern = (role == "Intern")
    target_multiplier = 4.5 if is_team_lead else 9.0
    financial_target = base_salary * target_multiplier
    c_sales = sales_df[sales_df['Consultant'] == consultant_name].copy()
    booked_gp = c_sales['GP'].sum() if not c_sales.empty else 0
    is_qualified = False
    target_achieved_pct = 0.0
    if is_intern:
        if quarterly_cv_count >= QUARTERLY_GOAL_INTERN:
            is_qualified = True
            target_achieved_pct = 100.0
        else:
            target_achieved_pct = (quarterly_cv_count / QUARTERLY_GOAL_INTERN) * 100
    else:
        financial_pct = (booked_gp / financial_target * 100) if financial_target > 0 else 0
        recruitment_pct = (quarterly_cv_count / QUARTERLY_INDIVIDUAL_GOAL * 100)
        if financial_pct >= 100 or recruitment_pct >= 100:
            is_qualified = True
            target_achieved_pct = max(financial_pct, recruitment_pct)
        else:
            target_achieved_pct = max(financial_pct, recruitment_pct)
    paid_gp = 0
    total_comm = 0
    current_level = 0
    if not is_intern:
        if not c_sales.empty:
            c_sales['Final Comm'] = 0.0
            c_sales['Commission Day Obj'] = pd.NaT
            paid_sales = c_sales[c_sales['Status'] == 'Paid'].copy()
            if not paid_sales.empty:
                paid_sales['Payment Date Obj'] = pd.to_datetime(paid_sales['Payment Date'], errors='coerce')
                paid_sales = paid_sales.dropna(subset=['Payment Date Obj']).sort_values(by='Payment Date Obj')
                paid_sales['Pay_Month_Key'] = paid_sales['Payment Date Obj'].dt.to_period('M')
                unique_months = sorted(paid_sales['Pay_Month_Key'].unique())
                running_paid_gp = 0
                pending_indices = []
                for month_key in unique_months:
                    month_deals = paid_sales[paid_sales['Pay_Month_Key'] == month_key]
                    month_new_gp = month_deals['GP'].sum()
                    running_paid_gp += month_new_gp
                    pending_indices.extend(month_deals.index.tolist())
                    level, multiplier = calculate_commission_tier(running_paid_gp, base_salary, is_team_lead)
                    if level > 0:
                        payout_date = get_payout_date_from_month_key(str(month_key))
                        for idx in pending_indices:
                            row = paid_sales.loc[idx]
                            deal_comm = calculate_single_deal_commission(row['Candidate Salary'], multiplier) * row['Percentage']
                            paid_sales.at[idx, 'Final Comm'] = deal_comm
                            paid_sales.at[idx, 'Commission Day Obj'] = payout_date
                        pending_indices = []
                paid_gp = running_paid_gp
                current_level, _ = calculate_commission_tier(booked_gp, base_salary, is_team_lead)
                limit_date = datetime.now() + timedelta(days=20)
                for idx, row in paid_sales.iterrows():
                    comm_date = row['Commission Day Obj']
                    if pd.notnull(comm_date) and comm_date <= limit_date:
                        total_comm += row['Final Comm']
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

# ==========================================
# 🔗 Google 连接
# ==========================================
def connect_to_google():
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    try:
        if "gcp_service_account" in st.secrets:
            creds_dict = dict(st.secrets["gcp_service_account"])
            creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
            return safe_google_api_call(gspread.authorize, creds, cache_prefix="auth")
        else:
            st.error("未配置GCP服务账号密钥")
            return None
    except Exception as e:
        st.error(f"Google连接失败: {str(e)}")
        return None

def get_quarter_info():
    today = datetime.now()
    year = today.year
    month = today.month
    quarter = (month - 1) // 3 + 1
    start_month = (quarter - 1) * 3 + 1
    end_month = start_month + 2
    tabs = [f"{year}{m:02d}" for m in range(start_month, end_month + 1)]
    return tabs, quarter, start_month, end_month, year

def get_all_month_tabs(client, consultant_config):
    try:
        sheet = safe_google_api_call(client.open_by_key, consultant_config['id'], cache_prefix=f"tabs_{consultant_config['name']}")
        if not sheet:
            return []
        all_tabs = safe_google_api_call(lambda: [ws.title for ws in sheet.worksheets()], cache_prefix=f"ws_list_{consultant_config['name']}")
        if not all_tabs:
            return []
        month_pattern = re.compile(r'^\d{6}$')
        valid_month_tabs = [tab for tab in all_tabs if month_pattern.match(tab)]
        valid_month_tabs.sort()
        return valid_month_tabs
    except Exception as e:
        st.error(f"获取 {consultant_config['name']} 的所有月份标签失败: {e}")
        return []

def fetch_role_from_personal_sheet(client, sheet_id):
    try:
        sheet = safe_google_api_call(client.open_by_key, sheet_id, cache_prefix=f"role_sheet_{sheet_id}")
        if not sheet:
            return "Full-Time", False, "Consultant"
        try:
            ws = safe_google_api_call(sheet.worksheet, 'Credentials', cache_prefix=f"role_ws_{sheet_id}")
        except:
            ws = safe_google_api_call(sheet.get_worksheet, 0, cache_prefix=f"role_ws_def_{sheet_id}")
        if not ws:
            return "Full-Time", False, "Consultant"
        header_vals = safe_google_api_call(ws.range, 'A1:B1', cache_prefix=f"role_header_{sheet_id}")
        if not header_vals:
            return "Full-Time", False, "Consultant"
        a1_val = header_vals[0].value.strip().lower()
        b1_val = header_vals[1].value.strip()
        title_text = "Consultant"
        if "title" in a1_val:
            title_text = b1_val
        is_intern = "intern" in title_text.lower()
        is_lead = "team lead" in title_text.lower() or "manager" in title_text.lower()
        role = "Intern" if is_intern else "Full-Time"
        return role, is_lead, title_text.title()
    except Exception as e:
        st.warning(f"获取角色信息失败: {str(e)}")
        return "Full-Time", False, "Consultant"

# 🆕 修改：只统计 LIVE POSITIONS 岗位的简历
def fetch_consultant_data(client, consultant_config, target_tab, live_positions):
    sheet_id = consultant_config['id']
    target_key = consultant_config.get('keyword', 'Name').strip()
    COMPANY_KEYS = ["Company", "Client", "Cliente", "公司名称", "客户"]
    POSITION_KEYS = ["Position", "Role", "Posición", "职位", "岗位"]
    try:
        sheet = safe_google_api_call(client.open_by_key, sheet_id, cache_prefix=f"cv_sheet_{consultant_config['name']}_{target_tab}")
        if not sheet:
            return 0, []
        worksheet = safe_google_api_call(sheet.worksheet, target_tab, cache_prefix=f"cv_ws_{consultant_config['name']}_{target_tab}")
        if not worksheet:
            st.warning(f"工作表 {target_tab} 不存在")
            return 0, []
        rows = safe_google_api_call(worksheet.get_all_values, cache_prefix=f"cv_rows_{consultant_config['name']}_{target_tab}")
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
            try:
                key_index = cleaned_row.index(target_key)
                # 只统计 LIVE 岗位的简历
                if is_live_position(current_position, live_positions):
                    candidates = [x for x in cleaned_row[key_index + 1:] if x]
                    count += len(candidates)
                    for _ in range(len(candidates)):
                        details.append({
                            "Consultant": consultant_config['name'],
                            "Company": current_company,
                            "Position": current_position,
                            "Month": target_tab,
                            "Count": 1
                        })
            except ValueError:
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
    try:
        sheet = safe_google_api_call(client.open_by_key, SALES_SHEET_ID, cache_prefix="sales_sheet")
        if not sheet:
            return pd.DataFrame()
        try:
            ws = safe_google_api_call(sheet.worksheet, SALES_TAB_NAME, cache_prefix="sales_ws")
        except:
            ws = safe_google_api_call(sheet.get_worksheet, 0, cache_prefix="sales_ws_def")
        rows = safe_google_api_call(ws.get_all_values, cache_prefix="sales_rows")
        if not rows:
            return pd.DataFrame()
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
                row_upper = " ".join(row_lower).upper()
                if "POSITION" in row_upper and "PLACED" not in row_upper:
                    break
                if len(row) <= max(col_cons, col_onboard, col_sal):
                    continue
                consultant_name = row[col_cons].strip()
                if not consultant_name:
                    continue
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
                if not (onboard_date.year == year and start_m <= onboard_date.month <= end_m):
                    continue
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
                salary_raw = str(row[col_sal]).replace(',', '').replace('$', '').replace('MXN', '').strip()
                try:
                    salary = float(salary_raw)
                except:
                    salary = 0
                pct_val = 1.0
                if col_pct != -1 and len(row) > col_pct:
                    p_str = str(row[col_pct]).replace('%', '').strip()
                    try:
                        p_float = float(p_str)
                        pct_val = p_float / 100.0 if p_float > 1.0 else p_float
                    except:
                        pct_val = 1.0
                base_gp_factor = 1.0 if salary < 20000 else 1.5
                calc_gp = salary * base_gp_factor * pct_val
                pay_date_str = row[col_pay].strip() if (col_pay != -1 and len(row) > col_pay) else ""
                status = "Paid" if len(pay_date_str) > 5 else "Pending"
                records.append({
                    "Consultant": matched,
                    "GP": calc_gp,
                    "Candidate Salary": salary,
                    "Percentage": pct_val,
                    "Onboard Date": onboard_date.isoformat(),
                    "Payment Date": pay_date_str,
                    "Status": status
                })
        df = pd.DataFrame(records)
        if "Onboard Date" in df.columns:
            df["Onboard Date"] = pd.to_datetime(df["Onboard Date"])
        return df
    except Exception as e:
        st.error(f"财务数据获取失败: {e}")
        return pd.DataFrame()

def get_monthly_commission(client, consultant_name, month_key):
    try:
        sheet = safe_google_api_call(client.open_by_key, COMMISSION_SUMMARY_ID, cache_prefix=f"comm_sheet_{consultant_name}")
        if not sheet:
            return 0.0
        ws = safe_google_api_call(sheet.worksheet, COMMISSION_TAB_NAME, cache_prefix=f"comm_ws_{consultant_name}")
        if not ws:
            return 0.0
        data = safe_google_api_call(ws.get_all_records, cache_prefix=f"comm_data_{consultant_name}")
        if not data:
            return 0.0
        df = pd.DataFrame(data)
        if df.empty:
            return 0.0
        c_norm = normalize_text(consultant_name)
        match = df[
            (df['Consultant'].apply(normalize_text) == c_norm) &
            (df['Month'].astype(str) == month_key)
        ]
        return float(match.iloc[0]['Final_Commission']) if not match.empty else 0.0
    except Exception as e:
        st.warning(f"获取月度佣金失败: {e}")
        return 0.0

# ==========================================
# 🎨 UI 渲染函数
# ==========================================
def render_bar(current_total, goal, color_class, label_text, is_monthly_boss=False):
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
    name = conf['name']
    role = conf.get('role', 'Full-Time')
    is_team_lead = conf.get('is_team_lead', False)
    is_intern = (role == 'Intern')
    base_salary = conf.get('base_salary', 0)
    is_qualified = monthly_commission > 0
    booked_gp = fin_summary.get("Booked GP", 0)
    target_gp = base_salary * (4.5 if is_team_lead else 9.0)
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
    border_class = f"card-border-{(card_index % 4) + 1}"
    st.markdown(f"""
    <div class="player-card {border_class}">
        <div class="player-header">
            <div class="player-name">{name} {crown}</div>
            <span class="{badge_class}">{status_text}</span>
        </div>
    """, unsafe_allow_html=True)
    if is_intern:
        render_bar(quarterly_cv_count, QUARTERLY_GOAL_INTERN, "cv-fill", "Q. CVs (LIVE POSITIONS ONLY)")
    else:
        render_bar(booked_gp, target_gp, "money-fill", "GP TARGET")
        st.markdown(f'<div style="font-size:0.6em; color:#666; margin-top:5px;">AND/OR RECRUITMENT GOAL (LIVE POSITIONS ONLY):</div>',
                    unsafe_allow_html=True)
        render_bar(quarterly_cv_count, QUARTERLY_INDIVIDUAL_GOAL, "cv-fill", "Q. CVs")
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

# ==========================================
# 🚀 主程序（修改：加入 LIVE POSITIONS 过滤）
# ==========================================
def main():
    quarter_tabs, quarter_num, start_m, end_m, year = get_quarter_info()
    current_month_tab = datetime.now().strftime("%Y%m")
    st.title("👾 FILL THE PIT 👾")
    col1, col2, col3 = st.columns([1, 3, 1])
    with col2:
        start_btn = st.button(f"🚩 PRESS START")
    if start_btn:
        client = connect_to_google()
        if not client:
            return
        
        # 🆕 第一步：获取 LIVE POSITIONS 列表
        st.info("🔍 正在获取 LIVE POSITIONS 岗位列表...")
        live_positions = get_live_positions(client)
        if live_positions:
            st.success(f"✅ 找到 {len(live_positions)} 个 LIVE POSITIONS 岗位")
        else:
            st.warning("⚠️ 未找到 LIVE POSITIONS 岗位，将统计所有岗位数据")
        
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
        
        monthly_results = []
        quarterly_results = []
        all_month_details = []
        consultant_cv_counts = {}
        
        with st.spinner(f"🛰️ SCANNING LIVE POSITIONS RESUME DATA..."):
            for consultant in active_team_config:
                total_count = 0
                all_details = []
                m_count = 0
                all_month_tabs = get_all_month_tabs(client, consultant)
                if not all_month_tabs:
                    st.warning(f"{consultant['name']} 无有效月份数据")
                    monthly_results.append({"name": consultant['name'], "count": 0})
                    quarterly_results.append({"name": consultant['name'], "count": 0})
                    consultant_cv_counts[consultant['name']] = 0
                    continue
                
                for month_tab in all_month_tabs:
                    # 🆕 传入 live_positions 过滤数据
                    c_count, c_details = fetch_consultant_data(client, consultant, month_tab, live_positions)
                    total_count += c_count
                    all_details.extend(c_details)
                    if month_tab == current_month_tab:
                        m_count = c_count
                
                monthly_results.append({"name": consultant['name'], "count": m_count})
                quarterly_results.append({"name": consultant['name'], "count": total_count})
                consultant_cv_counts[consultant['name']] = total_count
                all_month_details.extend(all_details)
            
            sales_df = fetch_financial_df(client, start_m, end_m, year)
        
        time.sleep(0.5)
        
        # 🆕 修改标题，明确是 LIVE POSITIONS 数据
        st.markdown(
            f'<div class="header-bordered" style="border-color: #feca57; background: #fff;">🏆 TEAM MONTHLY GOAL ({current_month_tab}) - LIVE POSITIONS ONLY</div>',
            unsafe_allow_html=True)
        
        pit_month_ph = st.empty()
        stats_month_ph = st.empty()
        monthly_total = sum([r['count'] for r in monthly_results])
        steps = 15
        for step in range(steps + 1):
            curr_m = (monthly_total / steps) * step
            render_pit_html = f"""
            <div class="sub-label" style="font-size: 1.2em; text-align:center;">{int(curr_m)} / {MONTHLY_GOAL} CVs (LIVE POSITIONS)</div>
            <div class="pit-container pit-height-boss">
                <div class="pit-fill-boss" style="width: {min((curr_m / MONTHLY_GOAL) * 100, 100)}%;">
                    <div class="cat-squad" style="font-size: 40px; top: 5px;">🔥</div>
                </div>
            </div>
            """
            pit_month_ph.markdown(render_pit_html, unsafe_allow_html=True)
            if step == steps:
                cols_m = stats_month_ph.columns(len(monthly_results))
                for idx, res in enumerate(monthly_results):
                    with cols_m[idx]:
                        st.markdown(
                            f"""<div class="stat-card"><div class="stat-name">{res['name']}</div><div class="stat-val">{res['count']}</div></div>""",
                            unsafe_allow_html=True)
            time.sleep(0.01)
        
        if monthly_total >= MONTHLY_GOAL:
            st.balloons()
            time.sleep(1)
        
        quarterly_total = sum([r['count'] for r in quarterly_results])
        st.markdown(
            f'<div class="header-bordered" style="border-color: #54a0ff; background: #fff; margin-top: 20px;">🌊 TEAM QUARTERLY GOAL (Q{quarter_num}) - LIVE POSITIONS ONLY</div>',
            unsafe_allow_html=True)
        
        pit_quarter_ph = st.empty()
        for step in range(steps + 1):
            curr_q = (quarterly_total / steps) * step
            render_q_html = f"""
            <div class="sub-label" style="font-size: 1.2em; text-align:center;">{int(curr_q)} / {QUARTERLY_TEAM_GOAL} CVs (LIVE POSITIONS)</div>
            <div class="pit-container pit-height-boss">
                <div class="pit-fill-season" style="width: {min((curr_q / QUARTERLY_TEAM_GOAL) * 100, 100)}%;">
                    <div class="cat-squad" style="font-size: 40px; top: 5px;">🌊</div>
                </div>
            </div>
            """
            pit_quarter_ph.markdown(render_q_html, unsafe_allow_html=True)
            time.sleep(0.01)
        
        st.markdown("<br>", unsafe_allow_html=True)
        st.markdown(
            f'<div class="header-bordered" style="border-color: #48dbfb;">❄️ PLAYER STATS (Q{quarter_num}) - LIVE POSITIONS ONLY</div>',
            unsafe_allow_html=True)
        
        row1 = st.columns(2)
        row2 = st.columns(2)
        all_cols = row1 + row2
        
        for idx, conf in enumerate(active_team_config):
            c_name = conf['name']
            c_cvs = consultant_cv_counts.get(c_name, 0)
            perf_summary = calculate_consultant_performance(
                sales_df, c_name, conf['base_salary'], c_cvs, conf['role'], conf['is_team_lead']
            )
            current_month_key = datetime.now().strftime("%Y%m")
            monthly_commission = get_monthly_commission(client, c_name, current_month_key)
            with all_cols[idx]:
                render_player_card(conf, perf_summary, c_cvs, idx, monthly_commission)
        
        if all_month_details:
            st.markdown("---")
            with st.expander(f"📜 MISSION LOGS ({current_month_tab}) - LIVE POSITIONS ONLY", expanded=False):
                df_all = pd.DataFrame(all_month_details)
                df_month = df_all[df_all['Month'] == current_month_tab]
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
                                    "Position": st.column_config.TextColumn("TARGET ROLE (LIVE)"),
                                    "Count": st.column_config.TextColumn("CVs")
                                }
                            )
                        else:
                            st.info(f"NO LIVE POSITIONS DATA FOR {current_consultant}")
            
            with st.expander("📊 CV SUMMARY BY LIVE POSITIONS", expanded=False):
                df_total = pd.DataFrame(all_month_details)
                summary_agg = df_total.groupby(['Company', 'Position'])['Count'].sum().reset_index()
                summary_agg = summary_agg.sort_values(by='Count', ascending=False)
                summary_agg.columns = ['CLIENT/COMPANY', 'TARGET ROLE (LIVE)', 'TOTAL CVs']
                st.dataframe(
                    summary_agg,
                    use_container_width=True,
                    hide_index=True,
                    column_config={
                        "TOTAL CVs": st.column_config.NumberColumn(
                            "TOTAL CVs",
                            help="Total number of CVs for LIVE POSITIONS across the whole team",
                            format="%d ⭐"
                        )
                    }
                )
        elif monthly_total == 0:
            st.markdown("---")
            st.info("NO LIVE POSITIONS DATA FOUND IN HISTORICAL RECORDS.")

if __name__ == "__main__":
    main()
