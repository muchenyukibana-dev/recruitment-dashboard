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

# ==========================================

st.set_page_config(page_title="Fill The Pit", page_icon="🎮", layout="wide")

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
        -webkit-text-stroke: 2px #000;
    }
    .stButton {
        display: flex; justify-content: center; width: 100%;
    }
    .stButton>button {
        background-color: #FF4757; color: white; border: 4px solid #000;
        border-radius: 15px; font-family: 'Press Start 2P', monospace;
        font-size: 24px !important; padding: 20px 40px !important;
        box-shadow: 0px 8px 0px #a71c2a; transition: all 0.1s;
    }
    .stButton>button:hover {
        transform: translateY(4px); box-shadow: 0px 4px 0px #a71c2a;
        background-color: #ff6b81;
    }
    .pit-container {
        background-color: #eee; border: 3px solid #000; border-radius: 12px;
        width: 100%; position: relative; margin-bottom: 12px;
        box-shadow: 4px 4px 0px rgba(0,0,0,0.2); overflow: hidden;
    }
    .pit-height-std { height: 25px; }
    .pit-height-boss { height: 60px; border-width: 4px; }
    @keyframes barberpole {
        from { background-position: 0 0; } to { background-position: 50px 50px; }
    }
    @keyframes rainbow-move {
        0% { background-position: 0% 50%; }
        50% { background-position: 100% 50%; }
        100% { background-position: 0% 50%; }
    }
    .pit-fill-boss {
        background: linear-gradient(270deg, #ff6b6b, #feca57, #48dbfb, #ff9ff3, #54a0ff);
        background-size: 400% 400%; animation: rainbow-move 6s ease infinite;
        height: 100%; display: flex; align-items: center; justify-content: flex-end;
    }
    .pit-fill-season { 
        background-image: linear-gradient(45deg, #3742fa 25%, #5352ed 25%, #5352ed 50%, #3742fa 50%, #3742fa 75%, #5352ed 75%, #5352ed 100%);
        background-size: 50px 50px; animation: barberpole 3s linear infinite;
        height: 100%; display: flex; align-items: center; justify-content: flex-end; 
    }
    .money-fill { 
        background-image: linear-gradient(45deg, #2ed573 25%, #7bed9f 25%, #7bed9f 50%, #2ed573 50%, #2ed573 75%, #7bed9f 75%, #7bed9f 100%);
        background-size: 50px 50px; animation: barberpole 4s linear infinite;
        height: 100%; display: flex; align-items: center; justify-content: flex-end;
    }
    .cv-fill {
        background-image: linear-gradient(45deg, #ff9ff3 25%, #f368e0 25%, #f368e0 50%, #ff9ff3 50%, #ff9ff3 75%, #f368e0 75%, #f368e0 100%);
        background-size: 50px 50px; animation: barberpole 3s linear infinite;
        height: 100%; display: flex; align-items: center; justify-content: flex-end;
    }
    .cat-squad {
        margin-right: 10px; font-size: 24px;
        filter: drop-shadow(2px 2px 0px rgba(0,0,0,0.5));
    }
    .player-card {
        background-color: #FFFFFF; border: 4px solid #000; border-radius: 15px;
        padding: 20px; margin-bottom: 30px; color: #333;
        box-shadow: 8px 8px 0px rgba(0,0,0,0.2); transition: transform 0.2s;
    }
    .card-border-1 { border-bottom: 6px solid #ff6b6b; }
    .card-border-2 { border-bottom: 6px solid #feca57; }
    .card-border-3 { border-bottom: 6px solid #48dbfb; }
    .card-border-4 { border-bottom: 6px solid #ff9ff3; }
    .player-header {
        display: flex; justify-content: space-between; align-items: center;
        margin-bottom: 15px; border-bottom: 2px dashed #ddd; padding-bottom: 10px;
    }
    .player-name {
        font-size: 1.1em; font-weight: bold; color: #2d3436;
    }
    .status-badge-pass {
        background-color: #2ed573; color: white; padding: 8px 12px;
        border-radius: 20px; border: 2px solid #000; font-size: 0.6em;
        box-shadow: 2px 2px 0px #000; animation: bounce 1s infinite alternate;
    }
    @keyframes bounce { from { transform: translateY(0); } to { transform: translateY(-2px); } }
    .status-badge-loading {
        background-color: #feca57; color: #000; padding: 8px 12px;
        border-radius: 20px; border: 2px solid #000; font-size: 0.6em;
        box-shadow: 2px 2px 0px #000;
    }
    .sub-label {
        font-family: 'Fredoka One', sans-serif; font-size: 0.8em;
        color: #FFFFFF; margin-bottom: 5px; text-transform: uppercase;
        letter-spacing: 1px; text-shadow: 1px 1px 0px #000;
    }
    .comm-unlocked {
        background-color: #fff4e6; border: 2px solid #ff9f43; border-radius: 10px;
        color: #e67e22; text-align: center; padding: 10px; margin-top: 15px;
        font-weight: bold; font-size: 0.9em; box-shadow: inset 0 0 10px #ffeaa7;
    }
    .comm-locked {
        background-color: #f1f2f6; border: 2px solid #ced6e0; border-radius: 10px;
        color: #a4b0be; text-align: center; padding: 10px; margin-top: 15px;
        font-size: 0.8em;
    }
    .header-bordered {
        background-color: #FFFFFF; border: 4px solid #000; border-radius: 15px;
        box-shadow: 6px 6px 0px #000000; padding: 20px; text-align: center;
        margin-bottom: 25px; color: #2d3436; font-size: 1.2em;
    }
    .stat-card {
        background-color: #fff; border: 3px solid #000; border-radius: 10px;
        padding: 10px; text-align: center; box-shadow: 4px 4px 0px rgba(0,0,0,0.1);
    }
    .stat-val { color: #000; font-size: 1.2em; font-weight: bold; }
    .stat-name { color: #555; font-size: 0.8em; }
    </style>
""", unsafe_allow_html=True)

# ==========================================
# 🧮 工具函数
# ==========================================
def exponential_backoff(retry_count):
    delay = (2 ** retry_count) * API_DELAY_BASE + random.uniform(0, API_DELAY_JITTER)
    return min(delay, 10)

def safe_google_api_call(func, *args, **kwargs):
    for retry in range(MAX_RETRIES):
        try:
            time.sleep(API_DELAY_BASE + random.uniform(0, API_DELAY_JITTER))
            return func(*args, **kwargs)
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

# ==========================================
# 🔍 核心：按【季度】判断是否达标（历史季度不随本月变化）
# ==========================================
def is_qualified_by_quarter(role, cv_qtr, gp_qtr, base_salary, is_team_lead):
    is_intern = (role == "Intern")
    if is_intern:
        return cv_qtr >= QUARTERLY_GOAL_INTERN
    target_multi = 4.5 if is_team_lead else 9.0
    fin_target = base_salary * target_multi
    fin_ok = (gp_qtr >= fin_target)
    rec_ok = (cv_qtr >= QUARTERLY_INDIVIDUAL_GOAL)
    return fin_ok or rec_ok

# ==========================================
# 🧮 佣金：按历史季度结算，不看本月
# ==========================================
def calculate_real_commission_by_deal_quarter(
    all_sales_df, consultant_name, base_salary, role, is_team_lead, cv_by_quarter
):
    sales_df = all_sales_df.copy() if all_sales_df is not None else pd.DataFrame()
    is_intern = (role == "Intern")
    if sales_df.empty or "Consultant" not in sales_df.columns:
        return 0.0, 0.0, 0

    c_sales = sales_df[sales_df["Consultant"] == consultant_name].copy()
    if c_sales.empty:
        return 0.0, 0.0, 0

    c_sales["Onboard Date Obj"] = pd.to_datetime(c_sales["Onboard Date"], errors="coerce")
    c_sales = c_sales.dropna(subset=["Onboard Date Obj"])

    total_paid_gp = 0.0
    total_comm = 0.0
    booked_gp = c_sales["GP"].sum()
    current_level, _ = calculate_commission_tier(booked_gp, base_salary, is_team_lead)

    for _, row in c_sales.iterrows():
        status = row["Status"]
        if status != "Paid":
            continue
        pay_date_str = row["Payment Date"]
        pay_obj = pd.to_datetime(pay_date_str, errors="coerce")
        if pd.isna(pay_obj):
            continue
        payout_date = get_payout_date_from_month_key(f"{pay_obj.year}-{pay_obj.month:02d}")
        if not payout_date or payout_date > datetime.now() + timedelta(days=20):
            continue

        # 取这笔单所在季度
        deal_dt = row["Onboard Date Obj"]
        deal_year = deal_dt.year
        deal_qtr = (deal_dt.month - 1) // 3 + 1
        qtr_key = f"{deal_year}Q{deal_qtr}"

        # 该季度的CV & GP
        cv_q = cv_by_quarter.get(qtr_key, 0)
        gp_q = 0.0
        mask_q = (
            (c_sales["Onboard Date Obj"].dt.year == deal_year) &
            (c_sales["Onboard Date Obj"].dt.quarter == deal_qtr)
        )
        gp_q = c_sales.loc[mask_q, "GP"].sum()

        # 关键：只看【当时季度】是否达标，不看本月
        q_qualified = is_qualified_by_quarter(role, cv_q, gp_q, base_salary, is_team_lead)
        if not q_qualified:
            continue

        level, mul = calculate_commission_tier(gp_q, base_salary, is_team_lead)
        comm = calculate_single_deal_commission(row["Candidate Salary"], mul) * row["Percentage"]
        total_comm += comm
        total_paid_gp += row["GP"]

    # Team Lead 额外
    if is_team_lead and not is_intern:
        mask = (
            (sales_df["Status"] == "Paid") &
            (sales_df["Consultant"] != consultant_name) &
            (sales_df["Consultant"] != "Estela Peng")
        )
        others = sales_df[mask].copy()
        others["Payment Date Obj"] = pd.to_datetime(others["Payment Date"], errors="coerce")
        others = others.dropna(subset=["Payment Date Obj"])
        for _, r in others.iterrows():
            pd_obj = r["Payment Date Obj"]
            payout = datetime(pd_obj.year + (pd_obj.month // 12), (pd_obj.month % 12) + 1, 15)
            if payout <= datetime.now() + timedelta(days=20):
                total_comm += 1000

    return total_paid_gp, total_comm, current_level

# ==========================================
# 🔗 Google 连接
# ==========================================
def connect_to_google():
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    try:
        if "gcp_service_account" in st.secrets:
            creds_dict = dict(st.secrets["gcp_service_account"])
            creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
            return safe_google_api_call(gspread.authorize, creds)
        else:
            st.error("未配置GCP密钥")
            return None
    except Exception as e:
        st.error(f"连接失败: {e}")
        return None

def get_quarter_info():
    today = datetime.now()
    y = today.year
    m = today.month
    q = (m - 1) // 3 + 1
    s = (q - 1) * 3 + 1
    e = s + 2
    qtr_tabs = [f"{y}{mm:02d}" for mm in range(s, e+1)]
    return qtr_tabs, q, s, e, y

def get_all_month_tabs(client, cfg):
    try:
        sheet = safe_google_api_call(client.open_by_key, cfg["id"])
        if not sheet:
            return []
        titles = safe_google_api_call(lambda: [w.title for w in sheet.worksheets()])
        valid = [t for t in titles if re.fullmatch(r"\d{6}", t)]
        valid.sort()
        return valid
    except:
        return []

def fetch_role(client, sheet_id):
    try:
        sheet = safe_google_api_call(client.open_by_key, sheet_id)
        if not sheet:
            return "Full-Time", False, "Consultant"
        try:
            ws = safe_google_api_call(sheet.worksheet, "Credentials")
        except:
            ws = safe_google_api_call(sheet.get_worksheet, 0)
        if not ws:
            return "Full-Time", False, "Consultant"
        rng = safe_google_api_call(ws.range, "A1:B1")
        if not rng:
            return "Full-Time", False, "Consultant"
        a1 = rng[0].value.strip().lower()
        b1 = rng[1].value.strip()
        title = b1 if "title" in a1 else "Consultant"
        is_intern = "intern" in title.lower()
        is_lead = "team lead" in title.lower() or "manager" in title.lower()
        role = "Intern" if is_intern else "Full-Time"
        return role, is_lead, title.title()
    except:
        return "Full-Time", False, "Consultant"

def fetch_cv_one_month(client, cfg, month_tab):
    sid = cfg["id"]
    key = cfg.get("keyword", "Name")
    comp = ["Company", "Client", "Cliente", "公司名称", "客户"]
    pos = ["Position", "Role", "Posición", "职位", "岗位"]
    try:
        sheet = safe_google_api_call(client.open_by_key, sid)
        ws = safe_google_api_call(sheet.worksheet, month_tab)
        if not ws:
            return 0, []
        rows = safe_google_api_call(ws.get_all_values)
        cnt = 0
        det = []
        curr_c = "Unknown"
        curr_p = "Unknown"
        for r in rows:
            if not r:
                continue
            cl = [str(x).strip() for x in r]
            try:
                i = cl.index(key)
                cs = [x for x in cl[i+1:] if x]
                cnt += len(cs)
                for _ in cs:
                    det.append({
                        "Consultant": cfg["name"],
                        "Company": curr_c,
                        "Position": curr_p,
                        "Month": month_tab
                    })
            except ValueError:
                if cl and cl[0] in comp:
                    curr_c = cl[1] if len(cl) > 1 else "Unknown"
                elif cl and cl[0] in pos:
                    curr_p = cl[1] if len(cl) > 1 else "Unknown"
        return cnt, det
    except:
        return 0, []

def fetch_financial_df(client, year, s, e):
    try:
        sheet = safe_google_api_call(client.open_by_key, SALES_SHEET_ID)
        if not sheet:
            return pd.DataFrame()
        try:
            ws = safe_google_api_call(sheet.worksheet, SALES_TAB_NAME)
        except:
            ws = safe_google_api_call(sheet.get_worksheet, 0)
        rows = safe_google_api_call(ws.get_all_values)
        if not rows:
            return pd.DataFrame()
        cc, co, cp, cs, cpt = -1,-1,-1,-1,-1
        found = False
        rec = []
        for r in rows:
            if not any(c.strip() for c in r):
                continue
            rl = [str(x).strip().lower() for x in r]
            if not found:
                if any("linkeazi" in c for c in rl) and any("onboarding" in c for c in rl):
                    for i, c in enumerate(rl):
                        if "linkeazi" in c and "consultant" in c: cc=i
                        if "onboarding" in c and "date" in c: co=i
                        if "candidate" in c and "salary" in c: cs=i
                        if "payment" in c and "onboard" not in c: cp=i
                        if "percentage" in c or "pct" in c or c=="%": cpt=i
                    found=True
                    continue
            else:
                ru = " ".join(rl).upper()
                if "POSITION" in ru and "PLACED" not in ru:
                    break
                if len(r) <= max(cc,co,cs):
                    continue
                name = r[cc].strip()
                if not name:
                    continue
                od_str = r[co].strip()
                od = None
                for f in ["%Y-%m-%d","%d/%m/%Y","%Y/%m/%d","%m/%d/%Y","%d-%b-%y"]:
                    try:
                        od = datetime.strptime(od_str, f)
                        break
                    except:
                        pass
                if not od:
                    continue
                if not (od.year == year and s <= od.month <= e):
                    continue
                match = "Unknown"
                n_norm = normalize_text(name)
                for t in TEAM_CONFIG_TEMPLATE:
                    t_norm = normalize_text(t["name"])
                    if t_norm in n_norm or n_norm in t_norm:
                        match = t["name"]
                        break
                if match == "Unknown":
                    continue
                sal_raw = str(r[cs]).replace(',','').replace('$','').replace('MXN','').strip()
                try:
                    sal = float(sal_raw)
                except:
                    sal=0
                pct = 1.0
                if cpt!=-1 and len(r)>cpt:
                    ps = str(r[cpt]).replace('%','').strip()
                    try:
                        pf = float(ps)
                        pct = pf/100 if pf>1 else pf
                    except:
                        pct=1.0
                factor = 1.0 if sal<20000 else 1.5
                gp = sal * factor * pct
                pay_str = r[cp].strip() if (cp!=-1 and len(r)>cp) else ""
                stat = "Paid" if len(pay_str)>5 else "Pending"
                rec.append({
                    "Consultant": match,
                    "GP": gp,
                    "Candidate Salary": sal,
                    "Percentage": pct,
                    "Onboard Date": od,
                    "Payment Date": pay_str,
                    "Status": stat
                })
        return pd.DataFrame(rec)
    except:
        return pd.DataFrame()

def get_monthly_commission(client, name, mk):
    try:
        sheet = safe_google_api_call(client.open_by_key, COMMISSION_SUMMARY_ID)
        ws = safe_google_api_call(sheet.worksheet, COMMISSION_TAB_NAME)
        data = safe_google_api_call(ws.get_all_records)
        df = pd.DataFrame(data)
        if df.empty:
            return 0.0
        n_norm = normalize_text(name)
        m = df[
            (df["Consultant"].apply(normalize_text)==n_norm) &
            (df["Month"].astype(str)==str(mk))
        ]
        return float(m.iloc[0]["Final_Commission"]) if not m.empty else 0.0
    except:
        return 0.0

# ==========================================
# 🎨 UI
# ==========================================
def render_bar(cur, goal, cls, lbl, boss=False):
    pct = (cur/goal)*100 if goal>0 else 0
    dp = min(pct,100)
    h = "pit-height-boss" if boss else "pit-height-std"
    cat = "🎉" if pct>=100 else ""
    st.markdown(f"""
    <div style="margin-bottom:5px;">
        <div class="sub-label">{lbl} ({pct:.1f}%)</div>
        <div class="pit-container {h}">
            <div class="{cls}" style="width:{dp}%;">
                <div class="cat-squad" style="top:{'15px' if boss else '5px'}">{cat}</div>
            </div>
        </div>
    </div>
    """, unsafe_allow_html=True)

def render_card(conf, qcv, comm, idx):
    name = conf["name"]
    role = conf["role"]
    is_lead = conf.get("is_team_lead", False)
    is_intern = (role=="Intern")
    base = conf["base_salary"]
    crown = "👑" if is_lead else ""
    border = f"card-border-{(idx%4)+1}"
    st.markdown(f"""
    <div class="player-card {border}">
        <div class="player-header">
            <div class="player-name">{name} {crown}</div>
        </div>
    """, unsafe_allow_html=True)
    if is_intern:
        render_bar(qcv, QUARTERLY_GOAL_INTERN, "cv-fill", "Q. CVs")
    else:
        render_bar(qcv, QUARTERLY_INDIVIDUAL_GOAL, "cv-fill", "Q. CVs")
    if is_intern:
        st.markdown("""<div class="comm-locked">INTERNSHIP TRACK</div>""", unsafe_allow_html=True)
    else:
        if comm>0:
            st.markdown(f"""<div class="comm-unlocked">💰 UNLOCKED: ${comm:,.2f}</div>""", unsafe_allow_html=True)
        else:
            st.markdown("""<div class="comm-locked">🔒 LOCKED</div>""", unsafe_allow_html=True)
    st.markdown("</div>", unsafe_allow_html=True)

# ==========================================
# 🚀 主程序（完全按你要求重写）
# ==========================================
def main():
    qtr_tabs, q_num, s_m, e_m, year = get_quarter_info()
    curr_mm = datetime.now().strftime("%Y%m")

    st.title("👾 FILL THE PIT 👾")
    c1,c2,c3 = st.columns([1,3,1])
    with c2:
        go = st.button("🚩 PRESS START")

    if not go:
        return

    client = connect_to_google()
    if not client:
        return

    team = []
    status = st.empty()
    status.info("🔐 LOADING TEAM...")
    for t in TEAM_CONFIG_TEMPLATE:
        role, lead, title = fetch_role(client, t["id"])
        team.append({**t, "role": role, "is_team_lead": lead, "title": title})
    status.empty()

    # 全局明细
    all_details = []

    # 1）当月 CV
    monthly_cv = {}
    for p in team:
        monthly_cv[p["name"]] = 0

    # 2）本季度 CV（只算Q1三个月）
    qtr_cv = {}
    for p in team:
        qtr_cv[p["name"]] = 0

    # 3）按季度统计CV（用于佣金判断历史季度是否达标）
    cv_by_qtr_all = {}
    for p in team:
        cv_by_qtr_all[p["name"]] = {}

    with st.spinner("📥 读取所有简历数据..."):
        for p in team:
            all_mons = get_all_month_tabs(client, p)
            p_month = 0
            p_qtr = 0
            qcv = {}
            for m in all_mons:
                cnt, det = fetch_cv_one_month(client, p, m)
                all_details.extend(det)
                # 当月
                if m == curr_mm:
                    p_month = cnt
                # 本季度
                if m in qtr_tabs:
                    p_qtr += cnt
                # 按季度汇总
                try:
                    y = int(m[:4])
                    mo = int(m[4:6])
                    q = (mo-1)//3 +1
                    qk = f"{y}Q{q}"
                    qcv[qk] = qcv.get(qk,0) + cnt
                except:
                    pass
            monthly_cv[p["name"]] = p_month
            qtr_cv[p["name"]] = p_qtr
            cv_by_qtr_all[p["name"]] = qcv

    # 财务
    df_sales = fetch_financial_df(client, year, s_m, e_m)

    # 月度团队
    mt = sum(monthly_cv.values())
    st.markdown(f'<div class="header-bordered" style="border-color:#feca57;">🏆 TEAM MONTHLY GOAL ({curr_mm})</div>', unsafe_allow_html=True)
    ph_m = st.empty()
    ph_ms = st.empty()
    steps=15
    for step in range(steps+1):
        v = (mt/steps)*step
        ph_m.markdown(f"""
        <div class="sub-label" style="font-size:1.2em;text-align:center;">{int(v)} / {MONTHLY_GOAL} CVs</div>
        <div class="pit-container pit-height-boss">
            <div class="pit-fill-boss" style="width:{min((v/MONTHLY_GOAL)*100,100)}%;">
                <div class="cat-squad" style="font-size:40px;top:5px;">🔥</div>
            </div>
        </div>
        """, unsafe_allow_html=True)
        if step==steps:
            cols = ph_ms.columns(len(team))
            for i,p in enumerate(team):
                with cols[i]:
                    st.markdown(f"""<div class="stat-card"><div class="stat-name">{p['name']}</div><div class="stat-val">{monthly_cv[p['name']]}</div></div>""", unsafe_allow_html=True)
        time.sleep(0.01)
    if mt >= MONTHLY_GOAL:
        st.balloons()
        time.sleep(1)

    # 季度团队
    qt = sum(qtr_cv.values())
    st.markdown(f'<div class="header-bordered" style="border-color:#54a0ff;margin-top:20px;">🌊 TEAM QUARTERLY GOAL (Q{q_num})</div>', unsafe_allow_html=True)
    ph_q = st.empty()
    for step in range(steps+1):
        v = (qt/steps)*step
        ph_q.markdown(f"""
        <div class="sub-label" style="font-size:1.2em;text-align:center;">{int(v)} / {QUARTERLY_TEAM_GOAL} CVs</div>
        <div class="pit-container pit-height-boss">
            <div class="pit-fill-season" style="width:{min((v/QUARTERLY_TEAM_GOAL)*100,100)}%;">
                <div class="cat-squad" style="font-size:40px;top:5px;">🌊</div>
            </div>
        </div>
        """, unsafe_allow_html=True)
        time.sleep(0.01)

    # 个人卡片：Q.CVs = 季度，佣金 = 历史达标结算，与本月无关
    st.markdown("<br>", unsafe_allow_html=True)
    st.markdown(f'<div class="header-bordered" style="border-color:#48dbfb;">❄️ PLAYER STATS (Q{q_num})</div>', unsafe_allow_html=True)
    r1 = st.columns(2)
    r2 = st.columns(2)
    cols = r1 + r2

    for i, p in enumerate(team):
        name = p["name"]
        qcv = qtr_cv[name]
        cv_q = cv_by_qtr_all[name]
        _, comm, _ = calculate_real_commission_by_deal_quarter(
            df_sales, name, p["base_salary"], p["role"], p["is_team_lead"], cv_q
        )
        with cols[i]:
            render_card(p, qcv, comm, i)

    # 日志
    if all_details:
        st.markdown("---")
        with st.expander(f"📜 MISSION LOGS ({curr_mm})", expanded=False):
            df = pd.DataFrame(all_details)
            dfm = df[df["Month"]==curr_mm]
            tabs = st.tabs([x["name"] for x in team])
            for i, t in enumerate(tabs):
                with t:
                    sub = dfm[dfm["Consultant"]==team[i]["name"]]
                    if sub.empty:
                        st.info("NO DATA")
                    else:
                        agg = sub.groupby(["Company","Position"])["Count"].sum().reset_index()
                        agg = agg.sort_values("Count", ascending=False)
                        agg["Count"] = agg["Count"].astype(str)
                        st.dataframe(agg, use_container_width=True, hide_index=True)
        with st.expander("📊 CV SUMMARY", expanded=False):
            df = pd.DataFrame(all_details)
            agg = df.groupby(["Company","Position"])["Count"].sum().reset_index().sort_values("Count", ascending=False)
            agg.columns = ["CLIENT","ROLE","TOTAL CVs"]
            st.dataframe(agg, use_container_width=True, hide_index=True)

if __name__ == "__main__":
    main()
