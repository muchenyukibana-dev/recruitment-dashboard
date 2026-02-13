import streamlit as st
import streamlit.components.v1 as components
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from gspread.exceptions import APIError
import pandas as pd
import os
import time
import random
import unicodedata
from datetime import datetime, timedelta

# ==========================================
# 🔧 1. 配置与季度定义
# ==========================================
SALES_SHEET_ID = '1jniQ-GpeMINjQMebniJ_J1eLVLQIR1NGbSjTtOFP9Q8'
SALES_TAB_NAME = 'Positions'

CV_TARGET_INDIVIDUAL = 87
MONTHLY_GOAL = 116
QUARTERLY_TEAM_GOAL = 348

now = datetime.now()
curr_year = now.year
curr_q = (now.month - 1) // 3 + 1
CURRENT_Q_STR = f"{curr_year} Q{curr_q}"

# 计算上个季度的标识
if curr_q == 1:
    PREV_Q_STR = f"{curr_year - 1} Q4"
    prev_q_start_m, prev_q_year = 10, curr_year - 1
else:
    PREV_Q_STR = f"{curr_year} Q{curr_q - 1}"
    prev_q_start_m, prev_q_year = (curr_q - 2) * 3 + 1, curr_year

start_m = (curr_q - 1) * 3 + 1
CURR_Q_MONTHS = [f"{curr_year}{m:02d}" for m in range(start_m, start_m + 3)]
PREV_Q_MONTHS = [f"{prev_q_year}{m:02d}" for m in range(prev_q_start_m, prev_q_start_m + 3)]

TEAM_CONFIG_TEMPLATE = [
    {"name": "Raul Solis", "id": "1vQuN-iNBRUug5J6gBMX-52jp6oogbA77SaeAf9j_zYs", "keyword": "Name", "base_salary": 11000},
    {"name": "Estela Peng", "id": "1sUkffAXzWnpzhhmklqBuwtoQylpR1U18zqBQ-lsp7Z4", "keyword": "姓名", "base_salary": 20800},
    {"name": "Ana Cruz", "id": "1VMVw5YCV12eI8I-VQSXEKg86J2IVZJEgjPJT7ggAFD0", "keyword": "Name", "base_salary": 13000},
    {"name": "Karina Albarran", "id": "1zc4ghvfjIxH0eJ2aXfopOWHqiyTDlD8yFNjBzpH07D8", "keyword": "Name", "base_salary": 15000},
]

# ==========================================
# 🎨 2. CSS 样式 (完全还原原版)
# ==========================================
st.set_page_config(page_title="Fill The Pit", page_icon="🎮", layout="wide")

st.markdown("""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Press+Start+2P&display=swap');
    @import url('https://fonts.googleapis.com/css2?family=Fredoka+One&display=swap');

    .stApp { background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); font-family: 'Press Start 2P', monospace; }
    h1 { text-shadow: 4px 4px 0px #000; color: #FFD700 !important; text-align: center; font-size: 3.5em !important; -webkit-text-stroke: 2px #000; }
    
    .stButton { display: flex; justify-content: center; width: 100%; margin-left: 200px; }
    .stButton>button { 
        background-color: #FF4757; color: white; border: 4px solid #000; border-radius: 15px; 
        font-family: 'Press Start 2P', monospace; font-size: 24px !important; padding: 20px 40px !important;
        box-shadow: 0px 8px 0px #a71c2a; width: 100%; 
    }
    .stButton>button:hover { transform: translateY(4px); box-shadow: 0px 4px 0px #a71c2a; background-color: #ff6b81; }

    .pit-container { background-color: #eee; border: 3px solid #000; border-radius: 12px; width: 100%; position: relative; margin-bottom: 12px; overflow: hidden; box-shadow: 4px 4px 0px rgba(0,0,0,0.2); }
    .pit-height-std { height: 25px; }
    .pit-height-boss { height: 60px; border-width: 4px; }
    
    @keyframes barberpole { from { background-position: 0 0; } to { background-position: 50px 50px; } }
    @keyframes rainbow-move { 0% { background-position: 0% 50%; } 50% { background-position: 100% 50%; } 100% { background-position: 0% 50%; } }
    .pit-fill-boss { background: linear-gradient(270deg, #ff6b6b, #feca57, #48dbfb, #ff9ff3, #54a0ff); background-size: 400% 400%; animation: rainbow-move 6s ease infinite; height: 100%; display: flex; align-items: center; justify-content: flex-end; }
    .pit-fill-season { background-image: linear-gradient(45deg, #3742fa 25%, #5352ed 25%, #5352ed 50%, #3742fa 50%, #3742fa 75%, #5352ed 75%, #5352ed 100%); background-size: 50px 50px; animation: barberpole 3s linear infinite; height: 100%; display: flex; align-items: center; justify-content: flex-end; }
    .money-fill { background-image: linear-gradient(45deg, #2ed573 25%, #7bed9f 25%, #7bed9f 50%, #2ed573 50%, #2ed573 75%, #7bed9f 75%, #7bed9f 100%); background-size: 50px 50px; animation: barberpole 4s linear infinite; height: 100%; display: flex; align-items: center; justify-content: flex-end; }
    .cv-fill { background-image: linear-gradient(45deg, #ff9ff3 25%, #f368e0 25%, #f368e0 50%, #ff9ff3 50%, #ff9ff3 75%, #f368e0 75%, #f368e0 100%); background-size: 50px 50px; animation: barberpole 3s linear infinite; height: 100%; display: flex; align-items: center; justify-content: flex-end; }
    
    .player-card { background-color: #FFF; border: 4px solid #000; border-radius: 15px; padding: 20px; margin-bottom: 30px; color: #333; box-shadow: 8px 8px 0px rgba(0,0,0,0.2); }
    .card-border-1 { border-bottom: 6px solid #ff6b6b; }
    .card-border-2 { border-bottom: 6px solid #feca57; }
    .card-border-3 { border-bottom: 6px solid #48dbfb; }
    .card-border-4 { border-bottom: 6px solid #ff9ff3; }
    
    .status-badge-pass { background-color: #2ed573; color: white; padding: 8px 12px; border-radius: 20px; border: 2px solid #000; font-size: 0.6em; box-shadow: 2px 2px 0px #000; animation: bounce 1s infinite alternate; }
    .status-badge-loading { background-color: #feca57; color: #000; padding: 8px 12px; border-radius: 20px; border: 2px solid #000; font-size: 0.6em; }
    @keyframes bounce { from { transform: translateY(0); } to { transform: translateY(-2px); } }

    .comm-unlocked { background-color: #fff4e6; border: 2px solid #ff9f43; border-radius: 10px; color: #e67e22; text-align: center; padding: 10px; margin-top: 15px; font-weight: bold; font-size: 0.9em; box-shadow: inset 0 0 10px #ffeaa7;}
    .comm-locked { background-color: #f1f2f6; border: 2px solid #ced6e0; border-radius: 10px; color: #a4b0be; text-align: center; padding: 10px; margin-top: 15px; font-size: 0.8em; }
    
    .header-bordered { background-color: #FFF; border: 4px solid #000; border-radius: 15px; box-shadow: 6px 6px 0px #000; padding: 20px; text-align: center; margin-bottom: 25px; }
    .sub-label { font-family: 'Fredoka One', sans-serif; font-size: 0.8em; color: #FFF; margin-bottom: 5px; text-transform: uppercase; text-shadow: 1px 1px 0px #000; }
    
    .stat-card { background-color: #fff; border: 3px solid #000; border-radius: 10px; padding: 10px; text-align: center; box-shadow: 4px 4px 0px rgba(0,0,0,0.1); }
    .stat-val { color: #000; font-size: 1.2em; font-weight: bold; }
    .stat-name { color: #555; font-size: 0.7em; }
    </style>
    """, unsafe_allow_html=True)

# ==========================================
# ⚙️ 3. 工具函数
# ==========================================

def normalize_text(text):
    return ''.join(c for c in unicodedata.normalize('NFD', str(text)) if unicodedata.category(c) != 'Mn').lower()

def safe_api_call(func, *args, **kwargs):
    for i in range(5):
        try: return func(*args, **kwargs)
        except APIError as e:
            if "429" in str(e): time.sleep(2 * (2 ** i) + random.uniform(0, 1))
            else: raise e
    return None

def calculate_commission_tier(total_gp, base_salary, is_team_lead=False):
    t1, t2, t3 = (4.5, 6.75, 11.25) if is_team_lead else (9.0, 13.5, 22.5)
    if total_gp < t1 * base_salary: return 0, 0
    elif total_gp < t2 * base_salary: return 1, 1
    elif total_gp < t3 * base_salary: return 2, 2
    else: return 3, 3

def calculate_single_deal_commission(salary, multiplier):
    if multiplier == 0: return 0
    if salary < 20000: base = 1000
    elif salary < 30000: base = salary * 0.05
    elif salary < 50000: base = salary * 1.5 * 0.05
    else: base = salary * 2.0 * 0.05
    return base * multiplier

def get_commission_pay_date(payment_date_obj):
    if pd.isna(payment_date_obj): return None
    try:
        year = payment_date_obj.year + (payment_date_obj.month // 12)
        month = (payment_date_obj.month % 12) + 1
        return datetime(year, month, 15)
    except: return None

# ==========================================
# 🛰️ 4. 数据爬取
# ==========================================

def connect_to_google():
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    if "gcp_service_account" in st.secrets:
        creds = ServiceAccountCredentials.from_json_keyfile_dict(dict(st.secrets["gcp_service_account"]), scope)
        return gspread.authorize(creds)
    return None

def fetch_role_info(client, sheet_id):
    try:
        sheet = safe_api_call(client.open_by_key, sheet_id)
        ws = safe_api_call(sheet.worksheet, 'Credentials')
        role_raw = safe_api_call(ws.acell, 'B1').value or "Consultant"
        is_lead = "lead" in role_raw.lower() or "manager" in role_raw.lower()
        is_intern = "intern" in role_raw.lower()
        return "Intern" if is_intern else "Full-Time", is_lead, role_raw.title()
    except: return "Full-Time", False, "Consultant"

def fetch_cv_data_with_details(client, conf, tabs):
    total = 0
    details = []
    COMPANY_KEYS = ["Company", "Client", "Cliente", "公司名称", "客户"]
    POSITION_KEYS = ["Position", "Role", "Posición", "职位", "岗位"]
    try:
        sheet = safe_api_call(client.open_by_key, conf['id'])
        for tab in tabs:
            try:
                ws = safe_api_call(sheet.worksheet, tab)
                rows = safe_api_call(ws.get_all_values)
                target_key = conf.get('keyword', 'Name')
                curr_c, curr_p = "Unknown", "Unknown"
                for r in rows:
                    if not r: continue
                    cl = [str(x).strip() for x in r]
                    if cl[0] in COMPANY_KEYS: curr_c = cl[1] if len(cl)>1 else "Unknown"
                    elif cl[0] in POSITION_KEYS: curr_p = cl[1] if len(cl)>1 else "Unknown"
                    if target_key in cl:
                        idx = cl.index(target_key)
                        cands = [x for x in cl[idx+1:] if x]
                        total += len(cands)
                        if tab == tabs[-1] and len(cands) > 0:
                            details.append({"Consultant": conf['name'], "Company": curr_c, "Position": curr_p, "Count": len(cands)})
            except: continue
    except: pass
    return total, details

def fetch_sales_history(client, year):
    records = []
    try:
        sheet = safe_api_call(client.open_by_key, SALES_SHEET_ID)
        ws = safe_api_call(sheet.worksheet, SALES_TAB_NAME)
        rows = safe_api_call(ws.get_all_values)
        col_cons, col_onboard, col_pay, col_sal, col_pct = -1, -1, -1, -1, -1
        found_header = False
        for row in rows:
            row_l = [str(x).strip().lower() for x in row]
            if not found_header:
                if any("consultan
