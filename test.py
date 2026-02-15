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
# 🔧 配置区域
# ==========================================
now = datetime.now()
CURRENT_YEAR = now.year
CURRENT_QUARTER = (now.month - 1) // 3 + 1
CURRENT_Q_STR = f"{CURRENT_YEAR} Q{CURRENT_QUARTER}"

if CURRENT_QUARTER == 1:
    PREV_Q_STR = f"{CURRENT_YEAR - 1} Q4"
    prev_q_year = CURRENT_YEAR - 1
    prev_q_start_m = 10
else:
    PREV_Q_STR = f"{CURRENT_YEAR} Q{CURRENT_QUARTER - 1}"
    prev_q_year = CURRENT_YEAR
    prev_q_start_m = (CURRENT_QUARTER - 2) * 3 + 1

prev_q_months = [f"{prev_q_year}{m:02d}" for m in range(prev_q_start_m, prev_q_start_m + 3)]
start_m = (CURRENT_QUARTER - 1) * 3 + 1
curr_q_months = [f"{CURRENT_YEAR}{m:02d}" for m in range(start_m, start_m + 3)]
quanbu = prev_q_months + curr_q_months

CV_TARGET_QUARTERLY = 87
QUARTERLY_TEAM_GOAL = 348
SALES_SHEET_ID = '1jniQ-GpeMINjQMebniJ_J1eLVLQIR1NGbSjTtOFP9Q8'
SALES_TAB_NAME = 'Positions'

TEAM_CONFIG = [
    {"name": "Raul Solis", "id": "1vQuN-iNBRUug5J6gBMX-52jp6oogbA77SaeAf9j_zYs", "keyword": "Name",
     "base_salary": 11000},
    {"name": "Estela Peng", "id": "1sUkffAXzWnpzhhmklqBuwtoQylpR1U18zqBQ-lsp7Z4", "keyword": "姓名",
     "base_salary": 20800},
    {"name": "Ana Cruz", "id": "1VMVw5YCV12eI8I-VQSXEKg86J2IVZJEgjPJT7ggAFD0", "keyword": "Name", "base_salary": 13000},
    {"name": "Karina Albarran", "id": "1zc4ghvfjIxH0eJ2aXfopOWHqiyTDlD8yFNjBzpH07D8", "keyword": "Name",
     "base_salary": 15000},
]



# --- 🧮 辅助函数 ---
def get_quarter_str(date_obj):
    if pd.isna(date_obj): return "Unknown"
    q = (date_obj.month - 1) // 3 + 1
    return f"{date_obj.year} Q{q}"


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
    if multiplier == 0: return 0
    if candidate_salary < 20000:
        base_comm = 1000
    elif candidate_salary < 30000:
        base_comm = candidate_salary * 0.05
    elif candidate_salary < 50000:
        base_comm = candidate_salary * 1.5 * 0.05
    else:
        base_comm = candidate_salary * 2.0 * 0.05
    return base_comm * multiplier


def get_commission_pay_date(payment_date):
    if pd.isna(payment_date) or not payment_date: return None
    try:
        p_date = pd.to_datetime(payment_date)
        year = p_date.year + (p_date.month // 12)
        month = (p_date.month % 12) + 1
        return datetime(year, month, 15)
    except:
        return None


def get_payout_date_from_month_key(month_key):
    try:
        dt = datetime.strptime(str(month_key), "%Y-%m")
        year = dt.year + (dt.month // 12)
        month = (dt.month % 12) + 1
        return datetime(year, month, 15)
    except:
        return None


def normalize_text(text):
    return ''.join(c for c in unicodedata.normalize('NFD', str(text)) if unicodedata.category(c) != 'Mn').lower()


def safe_api_call(func, *args, **kwargs):
    max_retries = 5
    for i in range(max_retries):
        try:
            return func(*args, **kwargs)
        except APIError as e:
            if "429" in str(e):
                time.sleep(2 * (2 ** i) + random.uniform(0, 1))
            else:
                raise e
    return None


def connect_to_google():
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    if "gcp_service_account" in st.secrets:
        creds = ServiceAccountCredentials.from_json_keyfile_dict(dict(st.secrets["gcp_service_account"]), scope)
        return gspread.authorize(creds)
    return None


def fetch_role_from_personal_sheet(client, sheet_id):
    try:
        sheet = safe_api_call(client.open_by_key, sheet_id)
        ws = safe_api_call(sheet.worksheet, 'Credentials')
        role = safe_api_call(ws.acell, 'B1').value
        return role.strip() if role else "Consultant"
    except:
        return "Consultant"


def fetch_recruitment_stats(client, months):
    all_stats, all_details = [], []
    for month in months:
        for consultant in TEAM_CONFIG:
            s, i, o, d = internal_fetch_sheet_data(client, consultant, month)
            all_stats.append({"Consultant": consultant['name'], "Month": month, "Sent": s, "Int": i, "Off": o})
            if d: all_details.extend(d)
    return pd.DataFrame(all_stats), pd.DataFrame(all_details)


def internal_fetch_sheet_data(client, conf, tab):
    try:
        sheet = safe_api_call(client.open_by_key, conf['id'])
        ws = safe_api_call(sheet.worksheet, tab)
        rows = safe_api_call(ws.get_all_values)
        details, cs, ci, co = [], 0, 0, 0
        target_key = conf.get('keyword', 'Name')
        COMPANY_KEYS, POSITION_KEYS, STAGE_KEYS = ["Company", "Client", "Cliente", "公司", "客户"], ["Position", "Role",
                                                                                                     "职位"], ["Stage",
                                                                                                               "Status",
                                                                                                               "阶段"]
        block = {"c": "Unk", "p": "Unk", "cands": {}}

        def flush(b):
            res = []
            nonlocal cs, ci, co
            for _, c_data in b['cands'].items():
                if not c_data.get('n'): continue
                stage = str(c_data.get('s', 'Sent')).lower()
                is_off = "offer" in stage
                is_int = ("interview" in stage) or ("面试" in stage) or is_off
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
                details.extend(flush(block));
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


def fetch_all_sales_data(client):
    # 定义保底列名，防止后续代码报 KeyError
    columns = [
        "Consultant", "GP", "Candidate Salary", "Percentage",
        "Onboard Date Obj", "Onboard Date Str", "Payment Date",
        "Payment Date Obj", "Status", "Quarter"
    ]
    try:
        sheet = safe_api_call(client.open_by_key, SALES_SHEET_ID)
        ws = safe_api_call(sheet.worksheet, SALES_TAB_NAME)
        rows = safe_api_call(ws.get_all_values)

        col_cons, col_onboard, col_pay, col_sal, col_pct = -1, -1, -1, -1, -1
        sales_records = []
        found_header = False
        date_formats = ["%Y-%m-%d", "%d/%m/%Y", "%Y/%m/%d", "%m/%d/%Y", "%d-%b-%y", "%Y.%m.%d"]

        for row in rows:
            if not any(cell.strip() for cell in row): continue
            row_lower = [str(x).strip().lower() for x in row]

            if not found_header:
                # 只要一行里同时出现了 "consultant" 和 "onboarding" 就判定为表头
                if any("consultant" in c for c in row_lower) and any("onboarding" in c for c in row_lower):
                    for idx, cell in enumerate(row_lower):
                        if "consultant" in cell: col_cons = idx
                        if "onboarding" in cell and "date" in cell: col_onboard = idx
                        if "candidate" in cell and "salary" in cell: col_sal = idx
                        if "payment" in cell and "date" in cell: col_pay = idx
                        if "percentage" in cell or cell == "%" or "pct" in cell: col_pct = idx
                    found_header = True
                    continue

            if found_header:
                if "POSITION" in " ".join(row_lower).upper() and "PLACED" not in " ".join(row_lower).upper(): break
                if len(row) <= max(col_cons, col_onboard): continue

                consultant_name = row[col_cons].strip()
                if not consultant_name: continue

                onboard_date = None
                for fmt in date_formats:
                    try:
                        onboard_date = datetime.strptime(row[col_onboard].strip(), fmt)
                        break
                    except:
                        pass
                if not onboard_date: continue

                matched = "Unknown"
                c_norm = normalize_text(consultant_name)
                for conf in TEAM_CONFIG:
                    conf_norm = normalize_text(conf['name'])
                    if conf_norm in c_norm or c_norm in conf_norm:
                        matched = conf['name']
                        break
                if matched == "Unknown": continue

                try:
                    salary = float(str(row[col_sal]).replace(',', '').replace('$', '').strip())
                except:
                    salary = 0

                pct_val = 1.0
                if col_pct != -1 and len(row) > col_pct:
                    try:
                        p_str = str(row[col_pct]).replace('%', '').strip()
                        p_float = float(p_str)
                        pct_val = p_float / 100.0 if p_float > 1.0 else p_float
                    except:
                        pct_val = 1.0

                calc_gp = salary * (1.0 if salary < 20000 else 1.5) * pct_val

                pay_date_obj, status = None, "Pending"
                if col_pay != -1 and len(row) > col_pay:
                    pay_str = row[col_pay].strip()
                    if len(pay_str) > 5:
                        status = "Paid"
                        for fmt in date_formats:
                            try:
                                pay_date_obj = datetime.strptime(pay_str, fmt)
                                break
                            except:
                                pass

                sales_records.append({
                    "Consultant": matched, "GP": calc_gp, "Candidate Salary": salary, "Percentage": pct_val,
                    "Onboard Date Obj": onboard_date, "Onboard Date Str": onboard_date.strftime("%Y-%m-%d"),
                    "Payment Date": row[col_pay].strip() if col_pay != -1 and len(row) > col_pay else "",
                    "Payment Date Obj": pay_date_obj, "Status": status, "Quarter": get_quarter_str(onboard_date)
                })

        if not sales_records:
            return pd.DataFrame(columns=columns)
        return pd.DataFrame(sales_records)
    except Exception as e:
        return pd.DataFrame(columns=columns)


@st.cache_data(ttl=600)  # 数据缓存 10 分钟，不用每次都去抓 API
def load_data_from_api(client, quanbu):
    team_data = []
    for conf in TEAM_CONFIG:
        member = conf.copy()
        member['role'] = fetch_role_from_personal_sheet(client, conf['id'])
        team_data.append(member)
    rec_stats_df, rec_details_df = fetch_recruitment_stats(client, quanbu)
    all_sales_df = fetch_all_sales_data(client)
    return {"team_data": team_data, "rec_stats": rec_stats_df, "rec_details": rec_details_df,
            "rec_hist": pd.DataFrame(), "sales_all": all_sales_df, "last_updated": datetime.now().strftime("%H:%M:%S")}


# ==========================================
# 🔧 1. 配置与季度定义
# ==========================================
# SALES_SHEET_ID = '1jniQ-GpeMINjQMebniJ_J1eLVLQIR1NGbSjTtOFP9Q8'
# SALES_TAB_NAME = 'Positions'
#
# CV_TARGET_INDIVIDUAL = 87
# MONTHLY_GOAL = 116
# QUARTERLY_TEAM_GOAL = 348
#
# now = datetime.now()
# curr_year = now.year
# curr_q = (now.month - 1) // 3 + 1
# CURRENT_Q_STR = f"{curr_year} Q{curr_q}"
#
# # 计算上个季度的标识
# if curr_q == 1:
#     PREV_Q_STR = f"{curr_year - 1} Q4"
#     prev_q_m, prev_q_y = 10, curr_year - 1
# else:
#     PREV_Q_STR = f"{curr_year} Q{curr_q - 1}"
#     prev_q_m, prev_q_y = (curr_q - 2) * 3 + 1, curr_year
#
# start_m = (curr_q - 1) * 3 + 1
# CURR_Q_MONTHS = [f"{curr_year}{m:02d}" for m in range(start_m, start_m + 3)]
# PREV_Q_MONTHS = [f"{prev_q_y}{m:02d}" for m in range(prev_q_m, prev_q_m + 3)]
#
# TEAM_CONFIG_TEMPLATE = [
#     {"name": "Raul Solis", "id": "1vQuN-iNBRUug5J6gBMX-52jp6oogbA77SaeAf9j_zYs", "keyword": "Name",
#      "base_salary": 11000},
#     {"name": "Estela Peng", "id": "1sUkffAXzWnpzhhmklqBuwtoQylpR1U18zqBQ-lsp7Z4", "keyword": "姓名",
#      "base_salary": 20800},
#     {"name": "Ana Cruz", "id": "1VMVw5YCV12eI8I-VQSXEKg86J2IVZJEgjPJT7ggAFD0", "keyword": "Name", "base_salary": 13000},
#     {"name": "Karina Albarran", "id": "1zc4ghvfjIxH0eJ2aXfopOWHqiyTDlD8yFNjBzpH07D8", "keyword": "Name",
#      "base_salary": 15000},
# ]

# ==========================================
# 🎨 2. CSS 样式 (完全还原)
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
        box-shadow: 0px 8px 0px #a71c2a; width: 100%; transition: all 0.1s;
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
# ⚙️ 3. 核心工具逻辑
# ==========================================

def normalize_text(text):
    return ''.join(c for c in unicodedata.normalize('NFD', str(text)) if unicodedata.category(c) != 'Mn').lower()


def safe_api_call(func, *args, **kwargs):
    for i in range(5):
        try:
            return func(*args, **kwargs)
        except APIError as e:
            if "429" in str(e):
                time.sleep(2 * (2 ** i) + random.uniform(0, 1))
            else:
                raise e
    return None


def calculate_commission_tier(total_gp, base_salary, is_team_lead=False):
    t1, t2, t3 = (4.5, 6.75, 11.25) if is_team_lead else (9.0, 13.5, 22.5)
    if total_gp < t1 * base_salary:
        return 0, 0
    elif total_gp < t2 * base_salary:
        return 1, 1
    elif total_gp < t3 * base_salary:
        return 2, 2
    else:
        return 3, 3


def calculate_single_deal_commission(salary, multiplier):
    if multiplier == 0: return 0
    if salary < 20000:
        base = 1000
    elif salary < 30000:
        base = salary * 0.05
    elif salary < 50000:
        base = salary * 1.5 * 0.05
    else:
        base = salary * 2.0 * 0.05
    return base * multiplier


def get_commission_pay_date(payment_date_obj):
    if pd.isna(payment_date_obj): return None
    try:
        year = payment_date_obj.year + (payment_date_obj.month // 12)
        month = (payment_date_obj.month % 12) + 1
        return datetime(year, month, 15)
    except:
        return None


# ==========================================
# 🛰️ 4. 数据爬取逻辑
# ==========================================

def connect_to_google():
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    if "gcp_service_account" in st.secrets:
        creds_dict = dict(st.secrets["gcp_service_account"])
        creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
        return gspread.authorize(creds)
    return None


def load_data_from_api(client, quanbu):
    team_data = []
    for conf in TEAM_CONFIG:
        member = conf.copy()
        member['role'] = fetch_role_from_personal_sheet(client, conf['id'])
        team_data.append(member)
    rec_stats_df, rec_details_df = fetch_recruitment_stats(client, quanbu)
    all_sales_df = fetch_all_sales_data(client)
    return {"team_data": team_data, "rec_stats": rec_stats_df, "rec_details": rec_details_df,
            "rec_hist": pd.DataFrame(), "sales_all": all_sales_df, "last_updated": datetime.now().strftime("%H:%M:%S")}


def fetch_cv_data_with_details(client, conf, tabs):
    total = 0
    details = []
    # 关键字列表
    COMP_KEYS = ["Company", "Client", "Cliente", "公司名称", "客户"]
    POS_KEYS = ["Position", "Role", "Posición", "职位", "岗位"]
    try:
        sheet = safe_api_call(client.open_by_key, conf['id'])
        for tab in tabs:
            try:
                ws = safe_api_call(sheet.worksheet, tab)
                rows = safe_api_call(ws.get_all_values)
                target_key = conf.get('keyword', 'Name')
                c_comp, c_pos = "Unknown", "Unknown"
                for r in rows:
                    if not r: continue
                    cl = [str(x).strip() for x in r]
                    if cl[0] in COMP_KEYS:
                        c_comp = cl[1] if len(cl) > 1 else "Unknown"
                    elif cl[0] in POS_KEYS:
                        c_pos = cl[1] if len(cl) > 1 else "Unknown"
                    if target_key in cl:
                        idx = cl.index(target_key)
                        cands = [x for x in cl[idx + 1:] if x]
                        total += len(cands)
                        if tab == tabs[-1] and len(cands) > 0:
                            details.append({"Consultant": conf['name'],
                                            "Company": c_comp,
                                            "Position": c_pos,
                                            "Count": len(cands)})
            except:
                continue
    except:
        pass
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
                if any("consultant" in c for c in row_l) and any("onboarding" in c for c in row_l):
                    for idx, c in enumerate(row_l):
                        if "consultant" in c: col_cons = idx
                        if "onboarding" in c and "date" in c: col_onboard = idx
                        if "salary" in c: col_sal = idx
                        if "payment" in c and "date" in c: col_pay = idx
                        if "percentage" in c or c == "%": col_pct = idx
                    found_header = True
            else:
                if len(row) <= max(col_cons, col_onboard): continue
                c_name_raw = row[col_cons].strip()
                if not c_name_raw: continue
                onboard_date = None
                for fmt in ["%Y-%m-%d", "%d/%m/%Y", "%m/%d/%Y", "%Y/%m/%d"]:
                    try:
                        onboard_date = datetime.strptime(row[col_onboard].strip(), fmt); break
                    except:
                        pass

                # --- 修改处：允许读取 2025 年及以后的数据，确保跨年追溯 ---
                if not onboard_date or onboard_date.year < 2025: continue

                q_label = f"{onboard_date.year} Q{(onboard_date.month - 1) // 3 + 1}"
                matched = "Unknown"
                for conf in TEAM_CONFIG:
                    if normalize_text(conf['name']) in normalize_text(c_name_raw): matched = conf['name']; break
                if matched == "Unknown": continue
                sal = float(str(row[col_sal]).replace(',', '').replace('$', '').strip() or 0)
                pct = 1.0
                if col_pct != -1 and len(row) > col_pct:
                    try:
                        p_val = float(str(row[col_pct]).replace('%', '').strip());
                        pct = p_val / 100 if p_val > 1 else p_val
                    except:
                        pct = 1.0
                pay_date_obj, status = None, "Pending"
                if col_pay != -1 and len(row) > col_pay and len(row[col_pay].strip()) > 5:
                    status = "Paid"
                    for fmt in ["%Y-%m-%d", "%d/%m/%Y", "%m/%d/%Y", "%Y/%d/%m"]:
                        try:
                            pay_date_obj = datetime.strptime(row[col_pay].strip(), fmt); break
                        except:
                            pass
                records.append(
                    {"Consultant": matched, "GP": sal * (1.5 if sal >= 20000 else 1.0) * pct, "Salary": sal, "Pct": pct,
                     "Status": status, "PayDateObj": pay_date_obj, "Quarter": q_label})
    except:
        pass
    return pd.DataFrame(records)


# ==========================================
# 🎨 5. UI 渲染函数
# ==========================================

def render_boss_bar(current, goal, color_class, icon):
    pct = (current / goal * 100) if goal > 0 else 0
    st.markdown(f"""
        <div class="sub-label" style="font-size: 1.2em; text-align:center;">{int(current)} / {goal} CVS</div>
        <div class="pit-container pit-height-boss">
            <div class="{color_class}" style="width: {min(pct, 100)}%;">
                <div style="margin-right:15px; font-size:40px;">{icon}</div>
            </div>
        </div>
    """, unsafe_allow_html=True)


def render_player_card(conf, q_cvs, prev_q_cvs, sales_df, idx):
    c_name = conf['name']
    role, is_lead, base = conf['role'], conf['is_team_lead'], conf['base_salary']

    # 筛选本季度和上季度数据
    c_sales_curr = sales_df[(sales_df['Consultant'] == c_name) & (sales_df['Quarter'] == CURRENT_Q_STR)]
    c_sales_prev = sales_df[(sales_df['Consultant'] == c_name) & (sales_df['Quarter'] == PREV_Q_STR)]

    booked_gp_curr = c_sales_curr['GP'].sum()
    booked_gp_prev = c_sales_prev['GP'].sum()
    target_gp = base * (4.5 if is_lead else 9.0)

    # 判定达标情况
    is_q_curr = (booked_gp_curr >= target_gp or q_cvs >= CV_TARGET_QUARTERLY) if role != "Intern" else (
                q_cvs >= CV_TARGET_QUARTERLY)
    is_q_prev = (booked_gp_prev >= target_gp or prev_q_cvs >= CV_TARGET_QUARTERLY) if role != "Intern" else (
                prev_q_cvs >= CV_TARGET_QUARTERLY)

    total_comm = 0
    
    

    # Karina commision计算 ---
    def render_player_card(conf, q_cvs, prev_q_cvs, sales_df, idx):
        c_name = conf['name']
        role, is_lead, base = conf['role'], conf['is_team_lead'], conf['base_salary']

        # ... (前面的筛选逻辑保持不变) ...

        total_comm = 0
        debug_details = []  # 用于存储明细

        # 确定发薪周期逻辑 (保持与原代码一致)
        now_date = datetime.now()
        if now_date.day <= 15:
            target_pay_year, target_pay_month = now_date.year, now_date.month
        else:
            target_pay_year = now_date.year + 1 if now_date.month == 12 else now_date.year
            target_pay_month = 1 if now_date.month == 12 else now_date.month + 1

        if role != "Intern":
            # --- 1. 计算个人成单提成 ---
            for q_label, q_df in [("本季度", c_sales_curr), ("上季度", c_sales_prev)]:
                # 判定是否达标 (is_q_curr/is_q_prev 在函数上方已定义)
                is_qualified = (
                            booked_gp_curr >= target_gp or q_cvs >= CV_TARGET_QUARTERLY) if q_label == "本季度" else (
                            booked_gp_prev >= target_gp or prev_q_cvs >= CV_TARGET_QUARTERLY)

                if is_qualified and not q_df.empty:
                    temp_df = q_df.sort_index()
                    running_gp = 0
                    for _, row in temp_df.iterrows():
                        running_gp += row['GP']
                        if row['Status'] == 'Paid':
                            p_date = get_commission_pay_date(row['PayDateObj'])
                            if p_date and p_date.year == target_pay_year and p_date.month == target_pay_month:
                                _, mult = calculate_commission_tier(running_gp, base, is_lead)
                                if mult == 0: _, mult = calculate_commission_tier(base * 10, base, is_lead)

                                deal_comm = calculate_single_deal_commission(row['Salary'], mult) * row['Pct']
                                total_comm += deal_comm
                                debug_details.append(
                                    f"🏠 个人单: {q_label} | 薪资:{row['Salary']} | 比例:{row['Pct']} | 提成:{deal_comm:,.2f}")

            # --- 2. 计算主管津贴 Overrides ---
            if is_lead:
                ov_mask = (sales_df['Status'] == 'Paid') & (sales_df['Consultant'] != c_name) & (
                            sales_df['Consultant'] != "Estela Peng")
                for _, row in sales_df[ov_mask].iterrows():
                    p_date = get_commission_pay_date(row['PayDateObj'])
                    if p_date and p_date.year == target_pay_year and p_date.month == target_pay_month:
                        bonus = 1000 * row['Pct']
                        total_comm += bonus
                        debug_details.append(
                            f"👥 团队单: 顾问:{row['Consultant']} | 比例:{row['Pct']} | 津贴:{bonus:,.2f}")

        # --- 关键的 DEBUG 显示区域 ---
        if c_name == "Karina Albarran":
            with st.expander("🔍 KARINA 佣金明细调试 (12745 是怎么来的)"):
                st.write(f"**判定身份:** {'👑 主管 (Team Lead)' if is_lead else '顾问 (Consultant)'}")
                st.write(f"**读取 B1 内容:** {role}")
                st.write(f"**本月发薪周期:** {target_pay_year}-{target_pay_month}-15")
                st.write(f"**本季度达标状态:** {'✅ 已达标' if is_q_curr else '❌ 未达标'}")
                st.write("---")
                if debug_details:
                    for line in debug_details:
                        st.write(line)
                    st.write(f"**🔥 最终总计: {total_comm:,.2f}**")
                else:
                    st.write("⚠️ 本月发薪周期内没有找到任何已付款 (Paid) 的单据。")

        # ... (后面的 UI 渲染代码保持不变) ...
    # 如果今天是 15 号（含）之前，展示本月 15 号的钱
    # 如果今天是 15 号之后，展示下个月 15 号的钱
    now_date = datetime.now()
    if now_date.day <= 15:
        target_pay_year = now_date.year
        target_pay_month = now_date.month
    else:
        target_pay_year = now_date.year + 1 if now_date.month == 12 else now_date.year
        target_pay_month = 1 if now_date.month == 12 else now_date.month + 1

    if role != "Intern":
        # 遍历本季度和上季度的单据
        for is_qualified, q_df in [(is_q_curr, c_sales_curr), (is_q_prev, c_sales_prev)]:
            if is_qualified and not q_df.empty:
                temp_df = q_df.sort_index()
                running_gp = 0
                for _, row in temp_df.iterrows():
                    running_gp += row['GP']
                    if row['Status'] == 'Paid':
                        _, mult = calculate_commission_tier(running_gp, base, is_lead)
                        # 达标保底逻辑
                        if mult == 0:
                            _, mult = calculate_commission_tier(base * 10, base, is_lead)

                        p_date = get_commission_pay_date(row['PayDateObj'])

                        # --- 核心锁定：只统计属于当前【发薪周期】的单子 ---
                        if p_date and p_date.year == target_pay_year and p_date.month == target_pay_month:
                            deal_comm = calculate_single_deal_commission(row['Salary'], mult) * row['Pct']
                            total_comm += deal_comm

        # 主管津贴 Overrides
        if is_lead and is_q_curr:
            ov_mask = (sales_df['Status'] == 'Paid') & (sales_df['Consultant'] != c_name) & (
                        sales_df['Consultant'] != "Estela Peng")
            for _, row in sales_df[ov_mask].iterrows():
                p_date = get_commission_pay_date(row['PayDateObj'])
                # 津贴同样只看当前【发薪周期】
                if p_date and p_date.year == target_pay_year and p_date.month == target_pay_month:
                    total_comm += 1000 * row['Pct']

    # --- UI 渲染部分保持不变 ---
    border = f"card-border-{(idx % 4) + 1}"
    status_tag = '<span class="status-badge-pass">LEVEL UP! 🌟</span>' if is_q_curr else '<span class="status-badge-loading">LOADING... 🚀</span>'

    st.markdown(
        f'<div class="player-card {border}"><div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:15px;"><div><b style="font-size:1.1em;">{c_name} {"👑" if is_lead else ""}</b><br><small style="color:#999;">{conf["title_display"]}</small></div>{status_tag}</div>',
        unsafe_allow_html=True)

    if role == "Intern":
        p = (q_cvs / CV_TARGET_QUARTERLY * 100)
        st.markdown(
            f'<div class="sub-label">Q. CVS ({p:.1f}%)</div><div class="pit-container pit-height-std"><div class="cv-fill" style="width:{min(p, 100)}%;"></div></div>',
            unsafe_allow_html=True)
    else:
        gp_p = (booked_gp_curr / target_gp * 100)
        st.markdown(
            f'<div class="sub-label">GP TARGET ({gp_p:.1f}%)</div><div class="pit-container pit-height-std"><div class="money-fill" style="width:{min(gp_p, 100)}%;"></div></div>',
            unsafe_allow_html=True)
        st.markdown('<div style="font-size:0.5em; color:#666; margin:5px 0;">OR RECRUITMENT GOAL:</div>',
                    unsafe_allow_html=True)
        cv_p = (q_cvs / CV_TARGET_QUARTERLY * 100)
        st.markdown(
            f'<div class="sub-label">Q. CVS ({cv_p:.1f}%)</div><div class="pit-container pit-height-std"><div class="cv-fill" style="width:{min(cv_p, 100)}%;"></div></div>',
            unsafe_allow_html=True)

    if role != "Intern":
        if total_comm > 0:
            st.markdown(f'<div class="comm-unlocked">💰 THIS MONTH: ${total_comm:,.0f}</div>', unsafe_allow_html=True)
        else:
            msg = "🔒 LOCKED (WAITING PAY)" if is_q_curr else "🔒 LOCKED (TARGET NOT MET)"
            st.markdown(f'<div class="comm-locked">{msg}</div>', unsafe_allow_html=True)
    st.markdown("</div>", unsafe_allow_html=True)


# ==========================================
# 🎮 6. 主程序
# ==========================================

def main():
    st.title("👾 FILL THE PIT 👾")
    col1, col2, col3 = st.columns([1, 3, 1])
    with col2:
        start_btn = st.button("🚩 PRESS START")

    if start_btn:
        client = connect_to_google()
        if not client: st.error("CONNECTION ERROR"); return

        active_team, m_cv_data, q_cv_counts, prev_q_counts, all_logs = [], [], {}, {}, []
        with st.spinner("🛰️ SCANNING SECTOR..."):
            sales_df = fetch_sales_history(client, now.year)
            for conf in TEAM_CONFIG:
                # --- 修改开始 ---
                # 1. 函数只返回一个值，所以我们只用一个变量 role_val 来接
                role_val = fetch_role_from_personal_sheet(client, conf['id'])

                # 2. 手动判定是否为 Lead（根据你说的，判断字符串里是否有 team lead）
                is_lead = True if "team lead" in role_val.lower() else False
                # --- 插入下面这行代码来验证 ---
                if conf['name'] == "Karina Albarran":
                    st.write(f"DEBUG: Karina 单元格读取到的值是: '{role_val}'")
                    st.write(f"DEBUG: Karina 是否被判定为主管: {is_lead}")
                # ----------------------------
                # 3. 设定 title（既然不改函数，我们就让 title 暂时等于 role_val）
                title = role_val

                # 4. 把处理好的变量塞进配置字典
                c_conf = {**conf, "role": role_val, "is_team_lead": is_lead, "title_display": title}
                # --- 修改结束 ---

                active_team.append(c_conf)

                # 抓取 CV 数据
                q_c, m_logs = fetch_cv_data_with_details(client, c_conf, curr_q_months)
                m_c = sum([l['Count'] for l in m_logs]) if m_logs else 0
                prev_q_c, _ = fetch_cv_data_with_details(client, c_conf, prev_q_months)

                q_cv_counts[conf['name']] = q_c
                m_cv_data.append({"name": conf['name'], "count": m_c})
                prev_q_counts[conf['name']] = prev_q_c
                all_logs.extend(m_logs)

        # --- Boss Bar 1: MONTHLY ---
        st.markdown(
            f'<div class="header-bordered" style="border-color:#feca57;">🏆 TEAM MONTHLY GOAL ({curr_q_months[-1]})</div>',
            unsafe_allow_html=True)
        m_total = sum([d['count'] for d in m_cv_data])
        m_bar_ph = st.empty()
        m_stat_ph = st.empty()

        # 滚动动画
        steps = 15
        for i in range(steps + 1):
            with m_bar_ph: render_boss_bar((m_total / steps) * i, QUARTERLY_TEAM_GOAL, "pit-fill-boss", "🔥")
            time.sleep(0.01)

        # 渲染个人数据方块
        with m_stat_ph:
            cols = st.columns(len(m_cv_data))
            for idx, d in enumerate(m_cv_data):
                with cols[idx]:
                    st.markdown(
                        f'<div class="stat-card"><div class="stat-name">{d["name"]}</div><div class="stat-val">{int(d["count"])}</div></div>',
                        unsafe_allow_html=True)

        # --- Boss Bar 2: QUARTERLY ---
        st.markdown(
            f'<div class="header-bordered" style="border-color:#54a0ff; margin-top:20px;">🌊 TEAM QUARTERLY GOAL ({CURRENT_Q_STR})</div>',
            unsafe_allow_html=True)
        q_total = sum(q_cv_counts.values())
        q_bar_ph = st.empty()
        for i in range(steps + 1):
            with q_bar_ph: render_boss_bar((q_total / steps) * i, QUARTERLY_TEAM_GOAL, "pit-fill-season", "🌊")
            time.sleep(0.01)

        # --- Player Hub ---
        st.markdown("<br>", unsafe_allow_html=True)
        st.markdown('<div class="header-bordered" style="border-color:#48dbfb;">❄️ PLAYER STATS</div>',
                    unsafe_allow_html=True)
        p_row1, p_row2 = st.columns(2), st.columns(2)
        all_p_cols = p_row1 + p_row2
        for i, conf in enumerate(active_team):
            with all_p_cols[i]: render_player_card(conf, q_cv_counts[conf['name']], prev_q_counts[conf['name']],
                                                   sales_df, i)

        # --- Mission Logs ---
        if all_logs:
            st.markdown("---")
            with st.expander(f"📜 MISSION LOGS ({curr_q_months[-1]})"):
                log_df = pd.DataFrame(all_logs)
                t_names = [c['name'] for c in active_team]
                tabs = st.tabs(t_names)
                for i, tab in enumerate(tabs):
                    with tab:
                        c_name = active_team[i]['name']
                        p_logs = log_df[log_df['Consultant'] == c_name]
                        if not p_logs.empty:
                            agg_df = p_logs.groupby(['Company', 'Position'])['Count'].sum().reset_index()
                            agg_df = agg_df.sort_values('Count', ascending=False)
                            st.dataframe(agg_df, use_container_width=True, hide_index=True)
                        else:
                            st.info("NO DATA")


if __name__ == "__main__":
    main()
