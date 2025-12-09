import streamlit as st
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from gspread.exceptions import APIError
import pandas as pd
import os
import time
import random
from datetime import datetime, timedelta
import unicodedata

# ==========================================
# 🔧 配置区域
# ==========================================
SALES_SHEET_ID = '1jniQ-GpeMINjQMebniJ_J1eLVLQIR1NGbSjTtOFP9Q8'
SALES_TAB_NAME = 'Positions'

# 定义当前季度，用于区分"当前"和"历史"
CURRENT_YEAR = 2025
CURRENT_QUARTER = 4
CURRENT_Q_STR = f"{CURRENT_YEAR} Q{CURRENT_QUARTER}"

TEAM_CONFIG = [
    {
        "name": "Raul Solis",
        "id": "1vQuN-iNBRUug5J6gBMX-52jp6oogbA77SaeAf9j_zYs",
        "keyword": "Name",
        "base_salary": 11000,
        "role": "Consultant"
    },
    {
        "name": "Estela Peng",
        "id": "1sUkffAXzWnpzhhmklqBuwtoQylpR1U18zqBQ-lsp7Z4",
        "keyword": "姓名",
        "base_salary": 20800,
        "role": "Consultant"
    },
    {
        "name": "Ana Cruz",
        "id": "1VMVw5YCV12eI8I-VQSXEKg86J2IVZJEgjPJT7ggAFD0",
        "keyword": "Name",
        "base_salary": 13000,
        "role": "Consultant"
    },
    {
        "name": "Karina Albarran",
        "id": "1zc4ghvfjIxH0eJ2aXfopOWHqiyTDlD8yFNjBzpH07D8",
        "keyword": "Name",
        "base_salary": 15000,
        "role": "Team Lead"
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
    </style>
    """, unsafe_allow_html=True)


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


def get_commission_pay_date(payment_date):
    if pd.isna(payment_date) or not payment_date:
        return None
    try:
        year = payment_date.year + (payment_date.month // 12)
        month = (payment_date.month % 12) + 1
        return datetime(year, month, 15)
    except:
        return None


def normalize_text(text):
    return ''.join(c for c in unicodedata.normalize('NFD', str(text)) if unicodedata.category(c) != 'Mn').lower()


def safe_api_call(func, *args, **kwargs):
    max_retries = 5
    base_delay = 2
    for i in range(max_retries):
        try:
            return func(*args, **kwargs)
        except APIError as e:
            if "429" in str(e):
                wait_time = base_delay * (2 ** i) + random.uniform(0, 1)
                time.sleep(wait_time)
                if i == max_retries - 1:
                    st.error(f"⚠️ API Quota Exceeded. Please try again in a minute.")
                    raise e
            else:
                raise e
        except Exception as e:
            raise e
    return None


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


# --- 📥 数据获取 ---
def fetch_recruitment_stats(client, months):
    all_stats = []
    all_details = []
    for month in months:
        for consultant in TEAM_CONFIG:
            s, i, o, d = internal_fetch_sheet_data(client, consultant, month)
            all_stats.append({"Consultant": consultant['name'], "Month": month, "Sent": s, "Int": i, "Off": o})
            if d: all_details.extend(d)
    return pd.DataFrame(all_stats), pd.DataFrame(all_details)


def fetch_historical_recruitment_stats(client, exclude_months):
    all_stats = []
    try:
        sheet = safe_api_call(client.open_by_key, TEAM_CONFIG[0]['id'])
        worksheets = safe_api_call(sheet.worksheets)

        hist_months = []
        for ws in worksheets:
            title = ws.title.strip()
            if title.isdigit() and len(title) == 6:
                if title not in exclude_months:
                    hist_months.append(title)

        for month in hist_months:
            for consultant in TEAM_CONFIG:
                time.sleep(0.5)
                s, i, o, _ = internal_fetch_sheet_data(client, consultant, month)
                if s + i + o > 0:
                    all_stats.append({"Consultant": consultant['name'], "Month": month, "Sent": s, "Int": i, "Off": o})

        return pd.DataFrame(all_stats)
    except Exception as e:
        print(f"Historical Data Error: {e}")
        return pd.DataFrame()


def internal_fetch_sheet_data(client, conf, tab):
    try:
        sheet = safe_api_call(client.open_by_key, conf['id'])
        try:
            ws = safe_api_call(sheet.worksheet, tab)
        except:
            return 0, 0, 0, []

        rows = safe_api_call(ws.get_all_values)

        details = [];
        cs = 0;
        ci = 0;
        co = 0
        target_key = conf.get('keyword', 'Name')

        # 中文表头支持
        COMPANY_KEYS = ["Company", "Client", "Cliente", "公司", "客户", "公司名称", "客户名称"]
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

                # --- 漏斗逻辑 (Funnel Logic) ---
                # 规则:
                # 1. Sent 是分母，包含所有人 (cs+=1)
                # 2. Offered 属于 Interviewed (如果 offer, ci+=1, co+=1)
                # 3. Interviewed 属于 Sent (如果 int, ci+=1)

                is_off = "offer" in stage;
                is_int = ("interview" in stage) or ("面试" in stage) or is_off

                if is_off: co += 1
                if is_int: ci += 1
                cs += 1  # 所有人都是 Sent

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
    except Exception as e:
        return 0, 0, 0, []


def fetch_all_sales_data(client):
    try:
        sheet = safe_api_call(client.open_by_key, SALES_SHEET_ID)
        try:
            ws = safe_api_call(sheet.worksheet, SALES_TAB_NAME)
        except:
            ws = safe_api_call(sheet.get_worksheet, 0)

        rows = safe_api_call(ws.get_all_values)

        col_cons = -1;
        col_onboard = -1;
        col_pay = -1;
        col_sal = -1;
        col_pct = -1
        sales_records = []
        found_header = False
        date_formats = ["%Y-%m-%d", "%d/%m/%Y", "%Y/%m/%d", "%m/%d/%Y", "%d-%b-%y", "%Y.%m.%d"]

        for i, row in enumerate(rows):
            if not any(cell.strip() for cell in row): continue
            row_lower = [str(x).strip().lower() for x in row]

            if not found_header:
                has_cons = any("linkeazi" in c and "consultant" in c for c in row_lower)
                has_onb = any("onboarding" in c for c in row_lower)
                if has_cons and has_onb:
                    for idx, cell in enumerate(row_lower):
                        if "linkeazi" in cell and "consultant" in cell: col_cons = idx
                        if "onboarding" in cell and "date" in cell: col_onboard = idx
                        if "candidate" in cell and "salary" in cell: col_sal = idx
                        if "payment" in cell and "onboard" not in cell: col_pay = idx
                        if "percentage" in cell or cell == "%" or "pct" in cell: col_pct = idx
                    found_header = True
                    continue

            if found_header:
                row_upper = " ".join(row_lower).upper()
                if "POSITION" in row_upper and "PLACED" not in row_upper: break
                if len(row) <= max(col_cons, col_onboard, col_sal): continue

                consultant_name = row[col_cons].strip()
                if not consultant_name: continue

                onboard_str = row[col_onboard].strip()
                onboard_date = None
                for fmt in date_formats:
                    try:
                        onboard_date = datetime.strptime(onboard_str, fmt)
                        break
                    except:
                        pass
                if not onboard_date: continue

                matched = "Unknown"
                c_norm = normalize_text(consultant_name)
                for conf in TEAM_CONFIG:
                    conf_norm = normalize_text(conf['name'])
                    if conf_norm in c_norm or c_norm in conf_norm: matched = conf['name']; break
                    if conf_norm.split()[0] in c_norm: matched = conf['name']; break
                if matched == "Unknown": continue

                salary_raw = str(row[col_sal]).replace(',', '').replace('$', '').replace('MXN', '').replace('CNY',
                                                                                                            '').strip()
                try:
                    salary = float(salary_raw)
                except:
                    salary = 0

                pct_val = 1.0
                if col_pct != -1 and len(row) > col_pct:
                    p_str = str(row[col_pct]).replace('%', '').strip()
                    if p_str:
                        try:
                            p_float = float(p_str)
                            if p_float > 1.0:
                                pct_val = p_float / 100.0
                            else:
                                pct_val = p_float
                        except:
                            pct_val = 1.0

                base_gp_factor = 1.0 if salary < 20000 else 1.5
                calc_gp = salary * base_gp_factor * pct_val

                pay_date_str = ""
                pay_date_obj = None
                status = "Pending"
                if col_pay != -1 and len(row) > col_pay:
                    pay_date_str = row[col_pay].strip()
                    if len(pay_date_str) > 5:
                        status = "Paid"
                        for fmt in date_formats:
                            try:
                                pay_date_obj = datetime.strptime(pay_date_str, fmt)
                                break
                            except:
                                pass

                sales_records.append({
                    "Consultant": matched,
                    "GP": calc_gp,
                    "Candidate Salary": salary,
                    "Percentage": pct_val,
                    "Onboard Date": onboard_date,
                    "Onboard Date Str": onboard_date.strftime("%Y-%m-%d"),
                    "Payment Date": pay_date_str,
                    "Payment Date Obj": pay_date_obj,
                    "Status": status,
                    "Quarter": get_quarter_str(onboard_date)
                })
        return pd.DataFrame(sales_records)
    except Exception as e:
        st.error(f"Error fetching sales data: {e}")
        return pd.DataFrame()


import streamlit as st
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from gspread.exceptions import APIError
import pandas as pd
import os
import time
import random
from datetime import datetime, timedelta
import unicodedata

# ==========================================
# 🔧 配置区域
# ==========================================
SALES_SHEET_ID = '1rCmyqOUOBn-644KpCtF5FZwBMEnRGHTKSSUBxzvOSkI'
SALES_TAB_NAME = 'Positions'

# 定义当前季度
CURRENT_YEAR = 2025
CURRENT_QUARTER = 4
CURRENT_Q_STR = f"{CURRENT_YEAR} Q{CURRENT_QUARTER}"

TEAM_CONFIG = [
    {
        "name": "Raul Solis",
        "id": "1vQuN-iNBRUug5J6gBMX-52jp6oogbA77SaeAf9j_zYs",
        "keyword": "Name",
        "base_salary": 11000,
        "role": "Consultant"
    },
    {
        "name": "Estela Peng",
        "id": "1sUkffAXzWnpzhhmklqBuwtoQylpR1U18zqBQ-lsp7Z4",
        "keyword": "姓名",
        "base_salary": 20800,
        "role": "Consultant"
    },
    {
        "name": "Ana Cruz",
        "id": "1VMVw5YCV12eI8I-VQSXEKg86J2IVZJEgjPJT7ggAFD0",
        "keyword": "Name",
        "base_salary": 13000,
        "role": "Consultant"
    },
    {
        "name": "Karina Albarran",
        "id": "1zc4ghvfjIxH0eJ2aXfopOWHqiyTDlD8yFNjBzpH07D8",
        "keyword": "Name",
        "base_salary": 15000,
        "role": "Team Lead"
    },
]

st.set_page_config(page_title="Management Dashboard", page_icon="💼", layout="wide")

# --- 🎨 样式 ---
st.markdown("""
    <style>
    .stApp { background-color: #FFFFFF; color: #000000; }
    h1, h2, h3, h4 { color: #333333 !important; font-family: 'Arial', sans-serif; }
    .stButton>button { background-color: #0056b3; color: white; border: none; border-radius: 4px; padding: 10px 24px; font-weight: bold; }
    .stButton>button:hover { background-color: #004494; color: white; }
    .dataframe { font-size: 14px !important; border: 1px solid #ddd !important; }
    div[data-testid="metric-container"] { background-color: #f8f9fa; border: 1px solid #e9ecef; padding: 15px; border-radius: 8px; color: #333; box-shadow: 0 2px 4px rgba(0,0,0,0.05); }
    </style>
    """, unsafe_allow_html=True)


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

def get_commission_pay_date(payment_date):
    if pd.isna(payment_date) or not payment_date: return None
    try:
        year = payment_date.year + (payment_date.month // 12)
        month = (payment_date.month % 12) + 1
        return datetime(year, month, 15)
    except: return None

def get_payout_date_from_month_key(month_key):
    """
    输入 '2025-11'，返回 2025-12-15
    """
    try:
        dt = datetime.strptime(month_key, "%Y-%m")
        # 下个月
        year = dt.year + (dt.month // 12)
        month = (dt.month % 12) + 1
        return datetime(year, month, 15)
    except:
        return None

def normalize_text(text):
    return ''.join(c for c in unicodedata.normalize('NFD', str(text)) if unicodedata.category(c) != 'Mn').lower()

def safe_api_call(func, *args, **kwargs):
    max_retries = 5
    base_delay = 2
    for i in range(max_retries):
        try:
            return func(*args, **kwargs)
        except APIError as e:
            if "429" in str(e):
                time.sleep(base_delay * (2 ** i) + random.uniform(0, 1))
                if i == max_retries - 1: raise e
            else: raise e
        except Exception as e: raise e
    return None

def connect_to_google():
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    if "gcp_service_account" in st.secrets:
        try:
            creds = ServiceAccountCredentials.from_json_keyfile_dict(dict(st.secrets["gcp_service_account"]), scope)
            return gspread.authorize(creds)
        except: return None
    else:
        json_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'credentials.json')
        if os.path.exists(json_path):
            try:
                creds = ServiceAccountCredentials.from_json_keyfile_name(json_path, scope)
                return gspread.authorize(creds)
            except: return None
        return None

# --- 数据获取 (省略部分重复代码，核心逻辑在 fetch_all_sales_data) ---
def fetch_recruitment_stats(client, months):
    all_stats = []
    all_details = []
    for month in months:
        for consultant in TEAM_CONFIG:
            s, i, o, d = internal_fetch_sheet_data(client, consultant, month)
            all_stats.append({"Consultant": consultant['name'], "Month": month, "Sent": s, "Int": i, "Off": o})
            if d: all_details.extend(d)
    return pd.DataFrame(all_stats), pd.DataFrame(all_details)

def fetch_historical_recruitment_stats(client, exclude_months):
    all_stats = []
    try:
        sheet = safe_api_call(client.open_by_key, TEAM_CONFIG[0]['id'])
        worksheets = safe_api_call(sheet.worksheets)
        hist_months = [ws.title.strip() for ws in worksheets if ws.title.strip().isdigit() and len(ws.title.strip()) == 6 and ws.title.strip() not in exclude_months]
        for month in hist_months:
            for consultant in TEAM_CONFIG:
                time.sleep(0.5)
                s, i, o, _ = internal_fetch_sheet_data(client, consultant, month)
                if s+i+o > 0: all_stats.append({"Consultant": consultant['name'], "Month": month, "Sent": s, "Int": i, "Off": o})
        return pd.DataFrame(all_stats)
    except: return pd.DataFrame()

def internal_fetch_sheet_data(client, conf, tab):
    try:
        sheet = safe_api_call(client.open_by_key, conf['id'])
        try: ws = safe_api_call(sheet.worksheet, tab)
        except: return 0, 0, 0, []
        rows = safe_api_call(ws.get_all_values)
        details, cs, ci, co = [], 0, 0, 0
        target_key = conf.get('keyword', 'Name')
        COMPANY_KEYS = ["Company", "Client", "Cliente", "公司", "客户", "公司名称", "客户名称"]
        POSITION_KEYS = ["Position", "Role", "Posición", "职位", "岗位"]
        STAGE_KEYS = ["Stage", "Status", "Step", "阶段", "状态"]
        block = {"c": "Unk", "p": "Unk", "cands": {}}
        def flush(b):
            res = []
            nonlocal cs, ci, co
            for _, c_data in b['cands'].items():
                name = c_data.get('n')
                if not name: continue
                stage = str(c_data.get('s', 'Sent')).lower()
                is_off = "offer" in stage
                is_int = ("interview" in stage) or ("面试" in stage) or is_off
                if is_off: co += 1
                if is_int: ci += 1
                cs += 1
                stat = "Offered" if is_off else ("Interviewed" if is_int else "Sent")
                res.append({"Consultant": conf['name'], "Month": tab, "Company": b['c'], "Position": b['p'], "Status": stat, "Count": 1})
            return res
        for r in rows:
            if not r: continue
            fc = r[0].strip()
            if fc in COMPANY_KEYS:
                details.extend(flush(block))
                block = {"c": r[1] if len(r) > 1 else "Unk", "p": "Unk", "cands": {}}
            elif fc in POSITION_KEYS: block['p'] = r[1] if len(r) > 1 else "Unk"
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
    except: return 0, 0, 0, []

def fetch_all_sales_data(client):
    try:
        sheet = safe_api_call(client.open_by_key, SALES_SHEET_ID)
        try: ws = safe_api_call(sheet.worksheet, SALES_TAB_NAME)
        except: ws = safe_api_call(sheet.get_worksheet, 0)
        rows = safe_api_call(ws.get_all_values)
        col_cons, col_onboard, col_pay, col_sal, col_pct = -1, -1, -1, -1, -1
        sales_records = []
        found_header = False
        date_formats = ["%Y-%m-%d", "%d/%m/%Y", "%Y/%m/%d", "%m/%d/%Y", "%d-%b-%y", "%Y.%m.%d"]
        for row in rows:
            if not any(cell.strip() for cell in row): continue
            row_lower = [str(x).strip().lower() for x in row]
            if not found_header:
                if any("linkeazi" in c and "consultant" in c for c in row_lower) and any("onboarding" in c for c in row_lower):
                    for idx, cell in enumerate(row_lower):
                        if "linkeazi" in cell and "consultant" in cell: col_cons = idx
                        if "onboarding" in cell and "date" in cell: col_onboard = idx
                        if "candidate" in cell and "salary" in cell: col_sal = idx
                        if "payment" in cell and "onboard" not in cell: col_pay = idx
                        if "percentage" in cell or cell == "%" or "pct" in cell: col_pct = idx
                    found_header = True
                    continue
            if found_header:
                if "POSITION" in " ".join(row_lower).upper() and "PLACED" not in " ".join(row_lower).upper(): break
                if len(row) <= max(col_cons, col_onboard, col_sal): continue
                consultant_name = row[col_cons].strip()
                if not consultant_name: continue
                onboard_date = None
                for fmt in date_formats:
                    try: onboard_date = datetime.strptime(row[col_onboard].strip(), fmt); break
                    except: pass
                if not onboard_date: continue
                matched = "Unknown"
                c_norm = normalize_text(consultant_name)
                for conf in TEAM_CONFIG:
                    conf_norm = normalize_text(conf['name'])
                    if conf_norm in c_norm or c_norm in conf_norm: matched = conf['name']; break
                    if conf_norm.split()[0] in c_norm: matched = conf['name']; break
                if matched == "Unknown": continue
                try: salary = float(str(row[col_sal]).replace(',', '').replace('$', '').replace('MXN', '').replace('CNY', '').strip())
                except: salary = 0
                pct_val = 1.0
                if col_pct != -1 and len(row) > col_pct:
                    try:
                        p_float = float(str(row[col_pct]).replace('%', '').strip())
                        pct_val = p_float / 100.0 if p_float > 1.0 else p_float
                    except: pct_val = 1.0
                calc_gp = salary * (1.0 if salary < 20000 else 1.5) * pct_val
                pay_date_obj, status = None, "Pending"
                if col_pay != -1 and len(row) > col_pay:
                    pay_str = row[col_pay].strip()
                    if len(pay_str) > 5:
                        status = "Paid"
                        for fmt in date_formats:
                            try: pay_date_obj = datetime.strptime(pay_str, fmt); break
                            except: pass
                sales_records.append({
                    "Consultant": matched, "GP": calc_gp, "Candidate Salary": salary, "Percentage": pct_val,
                    "Onboard Date": onboard_date, "Onboard Date Str": onboard_date.strftime("%Y-%m-%d"),
                    "Payment Date": row[col_pay].strip() if col_pay!=-1 and len(row)>col_pay else "",
                    "Payment Date Obj": pay_date_obj, "Status": status, "Quarter": get_quarter_str(onboard_date)
                })
        return pd.DataFrame(sales_records)
    except Exception as e: st.error(str(e)); return pd.DataFrame()

# --- 📦 数据加载封装 ---
def load_data_from_api(client, quarter_months_str):
    rec_stats_df, rec_details_df = fetch_recruitment_stats(client, quarter_months_str)
    time.sleep(1)
    rec_hist_df = fetch_historical_recruitment_stats(client, exclude_months=quarter_months_str)
    time.sleep(1)
    all_sales_df = fetch_all_sales_data(client)
    return {"rec_stats": rec_stats_df, "rec_details": rec_details_df, "rec_hist": rec_hist_df, "sales_all": all_sales_df, "last_updated": datetime.now().strftime("%H:%M:%S")}

# --- 🚀 主程序 ---
def main():
    st.title("💼 Management Dashboard")
    client = connect_to_google()
    if not client: st.error("❌ API Error"); return
    start_m, end_m = 10, 12
    quarter_months_str = [f"{CURRENT_YEAR}{m:02d}" for m in range(start_m, end_m + 1)]
    
    col1, col2 = st.columns([1, 5])
    with col1:
        if st.button("🔄 REFRESH DATA", type="primary"):
            with st.spinner("⏳ Fetching live data..."):
                try:
                    data_package = load_data_from_api(client, quarter_months_str)
                    st.session_state['data_cache'] = data_package
                    st.success(f"Updated: {data_package['last_updated']}")
                except Exception as e: st.error(str(e))
    
    if 'data_cache' not in st.session_state:
        st.info("👋 Welcome! Click 'REFRESH DATA' to start."); st.stop()

    cache = st.session_state['data_cache']
    rec_stats_df, rec_details_df, rec_hist_df, all_sales_df = cache['rec_stats'], cache['rec_details'], cache['rec_hist'], cache['sales_all']
    st.caption(f"📅 Snapshot: {cache['last_updated']}")

    if not all_sales_df.empty:
        q4_mask = (all_sales_df['Onboard Date'].dt.year == CURRENT_YEAR) & (all_sales_df['Onboard Date'].dt.month >= start_m) & (all_sales_df['Onboard Date'].dt.month <= end_m)
        sales_df_q4 = all_sales_df[q4_mask].copy()
        sales_df_hist = all_sales_df[~q4_mask].copy()
    else: sales_df_q4, sales_df_hist = pd.DataFrame(), pd.DataFrame()

    tab_dash, tab_details = st.tabs(["📊 DASHBOARD", "📝 DETAILS"])

    with tab_dash:
        # Recruitment Stats
        st.markdown(f"### 🎯 Recruitment Stats (Q{CURRENT_QUARTER})")
        if not rec_stats_df.empty:
            rec_summary = rec_stats_df.groupby('Consultant')[['Sent', 'Int', 'Off']].sum().reset_index()
            rec_summary['Int Rate'] = (rec_summary['Int'] / rec_summary['Sent']).fillna(0)
            total_row = pd.DataFrame([{'Consultant': 'TOTAL', 'Sent': rec_summary['Sent'].sum(), 'Int': rec_summary['Int'].sum(), 'Off': rec_summary['Off'].sum(), 'Int Rate': (rec_summary['Int'].sum()/rec_summary['Sent'].sum() if rec_summary['Sent'].sum()>0 else 0)}])
            rec_summary = pd.concat([rec_summary, total_row], ignore_index=True)
            st.dataframe(rec_summary, use_container_width=True, hide_index=True, column_config={"Int Rate": st.column_config.ProgressColumn("Int/Sent Rate", format="%.1f%%", min_value=0, max_value=1)})
        else: st.warning("No data.")
        
        with st.expander("📜 Historical Recruitment Data"):
            if not rec_hist_df.empty:
                st.dataframe(rec_hist_df.groupby('Consultant')[['Sent', 'Int', 'Off']].sum().reset_index().sort_values('Sent', ascending=False), use_container_width=True, hide_index=True)
            else: st.info("No data.")
        st.divider()

        # Financial Performance
        st.markdown(f"### 💰 Financial Performance (Q{CURRENT_QUARTER})")
        financial_summary = []
        updated_sales_records = []
        team_lead_overrides = []

        for conf in TEAM_CONFIG:
            c_name = conf['name']
            base = conf['base_salary']
            is_team_lead = (conf.get('role') == "Team Lead")
            target = base * (4.5 if is_team_lead else 9.0)

            c_sales = sales_df_q4[sales_df_q4['Consultant'] == c_name].copy() if not sales_df_q4.empty else pd.DataFrame()
            
            booked_gp = 0
            paid_gp = 0
            total_comm = 0
            current_level = 0

            # --- 核心逻辑: 阈值触发回溯累积 (Threshold Triggered Catch-up) ---
            if not c_sales.empty:
                # 1. 基础字段初始化
                c_sales['Applied Level'] = 0
                c_sales['Final Comm'] = 0.0
                c_sales['Commission Day Obj'] = pd.NaT # 初始为空
                c_sales['Commission Day'] = ""         # 初始为空
                
                booked_gp = c_sales['GP'].sum()
                
                # 2. 筛选已付款的单子用于计算
                # 注意：必须按付款时间排序，模拟时间轴
                paid_sales = c_sales[c_sales['Status'] == 'Paid'].copy()
                
                if not paid_sales.empty:
                    # 确保按付款日期排序
                    paid_sales['Payment Date Obj'] = pd.to_datetime(paid_sales['Payment Date Obj'])
                    paid_sales = paid_sales.sort_values(by='Payment Date Obj')
                    
                    # 提取月份Key (YYYY-MM)
                    paid_sales['Pay_Month_Key'] = paid_sales['Payment Date Obj'].dt.to_period('M')
                    unique_months = sorted(paid_sales['Pay_Month_Key'].unique())
                    
                    running_paid_gp = 0
                    pending_indices = [] # 蓄水池：存的是 paid_sales 中的 index
                    
                    for month_key in unique_months:
                        # 获取该月新回款的单子
                        month_deals = paid_sales[paid_sales['Pay_Month_Key'] == month_key]
                        
                        # 累加 GP
                        month_new_gp = month_deals['GP'].sum()
                        running_paid_gp += month_new_gp
                        
                        # 把新单子加入"待发蓄水池"
                        pending_indices.extend(month_deals.index.tolist())
                        
                        # 检查当前累计 GP 是否达标
                        level, multiplier = calculate_commission_tier(running_paid_gp, base, is_team_lead)
                        
                        if level > 0:
                            # === 触发发放 ===
                            # 发放日期 = 本月(month_key) 的下个月 15 号
                            payout_date = get_payout_date_from_month_key(str(month_key))
                            
                            # 将蓄水池里的单子全部结算
                            for idx in pending_indices:
                                row = paid_sales.loc[idx]
                                deal_comm = calculate_single_deal_commission(row['Candidate Salary'], multiplier) * row['Percentage']
                                
                                # 更新 DataFrame
                                paid_sales.at[idx, 'Applied Level'] = level
                                paid_sales.at[idx, 'Commission Day Obj'] = payout_date
                                paid_sales.at[idx, 'Final Comm'] = deal_comm
                            
                            # 清空蓄水池 (已结算的单子不再受未来更高Level影响)
                            pending_indices = []
                        else:
                            # === 未达标 ===
                            # 单子保留在 pending_indices 里，等待未来某个月达标后一起发
                            # 暂不设置 Commission Day
                            pass
                    
                    # 更新 paid_gp 用于显示
                    paid_gp = running_paid_gp
                    current_level, _ = calculate_commission_tier(running_paid_gp, base, is_team_lead)
                    
                    # 统计可见的 Payable Commission (条件: 有日期 且 日期 <= 今天+20天)
                    # 也就是已经触发发放的佣金
                    for idx, row in paid_sales.iterrows():
                        comm_date = row['Commission Day Obj']
                        if pd.notnull(comm_date) and comm_date <= datetime.now() + timedelta(days=20):
                            total_comm += row['Final Comm']
                            
                    # 将计算结果合并回 c_sales (为了展示)
                    # c_sales 包含 Pending 单子，paid_sales 只包含 Paid 单子
                    # 我们用 update 把 paid_sales 的计算结果覆盖回 c_sales
                    c_sales.update(paid_sales)
                    
                    # 格式化日期字符串 (用于显示)
                    c_sales['Commission Day'] = c_sales['Commission Day Obj'].apply(
                        lambda x: x.strftime("%Y-%m-%d") if pd.notnull(x) else ""
                    )

                updated_sales_records.append(c_sales)

            # Team Override
            if is_team_lead:
                if not sales_df_q4.empty:
                    override_mask = (sales_df_q4['Status'] == 'Paid') & (sales_df_q4['Consultant'] != c_name) & (sales_df_q4['Consultant'] != "Estela Peng")
                    pot_overrides = sales_df_q4[override_mask].copy()
                    for _, row in pot_overrides.iterrows():
                        # Override 也需要基于 Payment Date 判定发放日
                        comm_pay_obj = get_commission_pay_date(row['Payment Date Obj'])
                        if pd.notnull(comm_pay_obj) and comm_pay_obj <= datetime.now() + timedelta(days=20):
                            bonus = 1000
                            total_comm += bonus
                            team_lead_overrides.append({"Leader": c_name, "Source": row['Consultant'], "Salary": row['Candidate Salary'], "Date": comm_pay_obj.strftime("%Y-%m-%d"), "Bonus": bonus})

            financial_summary.append({
                "Consultant": c_name, "Base Salary": base, "Target": target,
                "Booked GP": booked_gp, "Paid GP": paid_gp,
                "Achieved": (paid_gp/target*100) if target>0 else 0,
                "Level": current_level, "Est. Commission": total_comm
            })

        final_sales_df = pd.concat(updated_sales_records) if updated_sales_records else pd.DataFrame()
        override_df = pd.DataFrame(team_lead_overrides)
        
        df_fin = pd.DataFrame(financial_summary).sort_values('Paid GP', ascending=False)
        st.dataframe(df_fin, use_container_width=True, hide_index=True, column_config={
            "Base Salary": st.column_config.NumberColumn(format="$%d"),
            "Target": st.column_config.NumberColumn("Target Q", format="$%d"),
            "Booked GP": st.column_config.NumberColumn(format="$%d"),
            "Paid GP": st.column_config.NumberColumn(format="$%d"),
            "Achieved": st.column_config.ProgressColumn("Target", format="%.1f%%", min_value=0, max_value=100),
            "Est. Commission": st.column_config.NumberColumn("Payable Comm.", format="$%d"),
        })

        with st.expander("📜 Historical GP Summary (By Quarter)"):
            if not sales_df_hist.empty:
                q_totals = sales_df_hist.groupby('Quarter')['GP'].sum().reset_index()
                q_totals['Consultant'] = '📌 TOTAL'
                d_rows = sales_df_hist.groupby(['Quarter', 'Consultant'])['GP'].sum().reset_index()
                st.dataframe(pd.concat([q_totals, d_rows]).sort_values(['Quarter', 'Consultant'], ascending=[False, True]), use_container_width=True, hide_index=True, column_config={"GP": st.column_config.NumberColumn("Total GP", format="$%d")})
            else: st.info("No data.")

    with tab_details:
        st.markdown("### 🔍 Drill Down Details (Q4 Only)")
        for conf in TEAM_CONFIG:
            c_name = conf['name']
            fin_row = df_fin[df_fin['Consultant'] == c_name].iloc[0]
            header = f"👤 {c_name} | Paid GP: ${fin_row['Paid GP']:,.0f} (Current Lvl {fin_row['Level']})"
            with st.expander(header):
                st.markdown("#### 💸 Personal Commission Breakdown")
                if not final_sales_df.empty:
                    c_view = final_sales_df[final_sales_df['Consultant'] == c_name].copy()
                    if not c_view.empty:
                        c_view['Pct Display'] = c_view['Percentage'].apply(lambda x: f"{x*100:.0f}%")
                        st.dataframe(c_view[['Onboard Date Str', 'Payment Date', 'Commission Day', 'Candidate Salary', 'Pct Display', 'GP', 'Status', 'Applied Level', 'Final Comm']], use_container_width=True, hide_index=True, column_config={"Commission Day": st.column_config.TextColumn("Comm. Date"), "Final Comm": st.column_config.NumberColumn("Comm ($)", format="$%.2f")})
                    else: st.info("No deals.")
                
                if conf.get('role') == 'Team Lead':
                    st.divider(); st.markdown("#### 👥 Team Overrides")
                    if not override_df.empty:
                        my_ov = override_df[override_df['Leader'] == c_name]
                        if not my_ov.empty: st.dataframe(my_ov, use_container_width=True, hide_index=True)
                        else: st.info("None.")
                    else: st.info("None.")
                
                st.divider(); st.markdown("#### 📝 Recruitment Logs")
                if not rec_details_df.empty:
                    c_logs = rec_details_df[rec_details_df['Consultant'] == c_name]
                    if not c_logs.empty: st.dataframe(c_logs.groupby(['Month', 'Company', 'Position', 'Status'])['Count'].sum().reset_index().sort_values('Month', ascending=False), use_container_width=True, hide_index=True)
                    else: st.info("No logs.")

if __name__ == "__main__":
    main()
