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
                # st.warning(f"API限流，{wait:.1f}秒后重试 ({retry + 1}/{MAX_RETRIES})")
                time.sleep(wait)
                continue
            else:
                st.error(f"API失败: {str(e)}")
                return None
    # st.error("达到最大重试次数")
    return None


def normalize_text(text):
    if pd.isna(text):
        return ""
    return ''.join(c for c in unicodedata.normalize('NFD', str(text))
                   if unicodedata.category(c) != 'Mn').lower()


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
# 🧮 佣金：直接从指定Sheet读取（不再计算）
# ==========================================
def get_commission_from_sheet(client, consultant_name):
    """直接从 1A3K3RLlVNzCSCI-AkXAh8-K99gDSpCM7L9oNOCY0Obs 读取佣金"""
    try:
        sheet = safe_google_api_call(client.open_by_key, COMMISSION_SUMMARY_ID)
        ws = safe_google_api_call(sheet.worksheet, COMMISSION_TAB_NAME)
        data = safe_google_api_call(ws.get_all_records)
        df = pd.DataFrame(data)

        if df.empty:
            return 0.0

        # 模糊匹配顾问姓名
        n_norm = normalize_text(consultant_name)
        df["name_norm"] = df["Consultant"].apply(normalize_text)
        match_row = df[df["name_norm"].str.contains(n_norm) | (df["name_norm"] == n_norm)]

        if match_row.empty:
            return 0.0

        # 取最新的Final_Commission
        match_row["Month"] = pd.to_datetime(match_row["Month"], errors='coerce')
        latest_row = match_row.sort_values("Month", ascending=False).iloc[0]
        return float(latest_row.get("Final_Commission", 0.0))
    except Exception as e:
        st.warning(f"读取{consultant_name}佣金失败: {str(e)}")
        return 0.0


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
    qtr_tabs = [f"{y}{mm:02d}" for mm in range(s, e + 1)]
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
                cs = [x for x in cl[i + 1:] if x]
                cnt += len(cs)
                for _ in cs:
                    det.append({
                        "Consultant": cfg["name"],
                        "Company": curr_c,
                        "Position": curr_p,
                        "Month": month_tab,
                        "Count": 1  # 修复KeyError：添加Count列
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
        cc, co, cp, cs, cpt = -1, -1, -1, -1, -1
        found = False
        rec = []
        for r in rows:
            if not any(c.strip() for c in r):
                continue
            rl = [str(x).strip().lower() for x in r]
            if not found:
                if any("linkeazi" in c for c in rl) and any("onboarding" in c for c in rl):
                    for i, c in enumerate(rl):
                        if "linkeazi" in c and "consultant" in c: cc = i
                        if "onboarding" in c and "date" in c: co = i
                        if "candidate" in c and "salary" in c: cs = i
                        if "payment" in c and "onboard" not in c: cp = i
                        if "percentage" in c or "pct" in c or c == "%": cpt = i
                    found = True
                    continue
            else:
                ru = " ".join(rl).upper()
                if "POSITION" in ru and "PLACED" not in ru:
                    break
                if len(r) <= max(cc, co, cs):
                    continue
                name = r[cc].strip()
                if not name:
                    continue
                od_str = r[co].strip()
                od = None
                for f in ["%Y-%m-%d", "%d/%m/%Y", "%Y/%m/%d", "%m/%d/%Y", "%d-%b-%y"]:
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
                sal_raw = str(r[cs]).replace(',', '').replace('$', '').replace('MXN', '').strip()
                try:
                    sal = float(sal_raw)
                except:
                    sal = 0
                pct = 1.0
                if cpt != -1 and len(r) > cpt:
                    ps = str(r[cpt]).replace('%', '').strip()
                    try:
                        pf = float(ps)
                        pct = pf / 100 if pf > 1 else pf
                    except:
                        pct = 1.0
                factor = 1.0 if sal < 20000 else 1.5
                gp = sal * factor * pct
                pay_str = r[cp].strip() if (cp != -1 and len(r) > cp) else ""
                stat = "Paid" if len(pay_str) > 5 else "Pending"
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


# ==========================================
# 🎨 UI 渲染函数
# ==========================================
def render_bar(cur, goal, cls, lbl, boss=False):
    pct = (cur / goal) * 100 if goal > 0 else 0
    dp = min(pct, 100)
    h = "pit-height-boss" if boss else "pit-height-std"
    cat = "🎉" if pct >= 100 else ""
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


def render_card(conf, qcv, gp_actual, gp_target, comm, level, idx):
    """渲染个人卡片（恢复GP进度条、LEVEL标签）"""
    name = conf["name"]
    role = conf["role"]
    is_lead = conf.get("is_team_lead", False)
    is_intern = (role == "Intern")
    base = conf["base_salary"]
    crown = "👑" if is_lead else ""
    border = f"card-border-{(idx % 4) + 1}"

    # LEVEL 标签文本
    level_text = f"LEVEL {level}" if level > 0 else "LEVEL 0"

    st.markdown(f"""
    <div class="player-card {border}">
        <div class="player-header">
            <div class="player-name">{name} {crown}</div>
            <div class="status-badge-pass">{level_text}</div>
        </div>
    """, unsafe_allow_html=True)

    # Q.CVs 进度条
    if is_intern:
        render_bar(qcv, QUARTERLY_GOAL_INTERN, "cv-fill", "Q. CVs")
    else:
        render_bar(qcv, QUARTERLY_INDIVIDUAL_GOAL, "cv-fill", "Q. CVs")

    # GP TARGET 进度条（恢复）
    if not is_intern:
        render_bar(gp_actual, gp_target, "gp-fill", "GP TARGET")

    # 佣金显示
    if is_intern:
        st.markdown("""<div class="comm-locked">INTERNSHIP TRACK</div>""", unsafe_allow_html=True)
    else:
        if comm > 0:
            st.markdown(f"""<div class="comm-unlocked">💰 UNLOCKED: ${comm:,.2f}</div>""", unsafe_allow_html=True)
        else:
            st.markdown("""<div class="comm-locked">🔒 LOCKED</div>""", unsafe_allow_html=True)

    st.markdown("</div>", unsafe_allow_html=True)


# ==========================================
# 🚀 主程序（完全重写，修复所有问题）
# ==========================================
def main():
    qtr_tabs, q_num, s_m, e_m, year = get_quarter_info()
    curr_mm = datetime.now().strftime("%Y%m")

    st.title("👾 FILL THE PIT 👾")

    # 修复：PRESS START 按钮居中
    st.markdown('<div class="start-button-container">', unsafe_allow_html=True)
    go = st.button("🚩 PRESS START")
    st.markdown('</div>', unsafe_allow_html=True)

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

    # 全局明细（修复Count列）
    all_details = []

    # 1）当月 CV
    monthly_cv = {}
    for p in team:
        monthly_cv[p["name"]] = 0

    # 2）本季度 CV（只算Q1三个月）
    qtr_cv = {}
    for p in team:
        qtr_cv[p["name"]] = 0

    with st.spinner("📥 读取所有简历数据..."):
        for p in team:
            all_mons = get_all_month_tabs(client, p)
            p_month = 0
            p_qtr = 0
            for m in all_mons:
                cnt, det = fetch_cv_one_month(client, p, m)
                all_details.extend(det)
                # 当月
                if m == curr_mm:
                    p_month = cnt
                # 本季度
                if m in qtr_tabs:
                    p_qtr += cnt
            monthly_cv[p["name"]] = p_month
            qtr_cv[p["name"]] = p_qtr

    # 财务数据（用于计算GP TARGET和LEVEL）
    df_sales = fetch_financial_df(client, year, s_m, e_m)

    # 月度团队目标
    mt = sum(monthly_cv.values())
    st.markdown(f'<div class="header-bordered" style="border-color:#feca57;">🏆 TEAM MONTHLY GOAL ({curr_mm})</div>',
                unsafe_allow_html=True)
    ph_m = st.empty()
    ph_ms = st.empty()
    steps = 15
    for step in range(steps + 1):
        v = (mt / steps) * step
        ph_m.markdown(f"""
        <div class="sub-label" style="font-size:1.2em;text-align:center;">{int(v)} / {MONTHLY_GOAL} CVs</div>
        <div class="pit-container pit-height-boss">
            <div class="pit-fill-boss" style="width:{min((v / MONTHLY_GOAL) * 100, 100)}%;">
                <div class="cat-squad" style="font-size:40px;top:5px;">🔥</div>
            </div>
        </div>
        """, unsafe_allow_html=True)
        if step == steps:
            cols = ph_ms.columns(len(team))
            for i, p in enumerate(team):
                with cols[i]:
                    st.markdown(
                        f"""<div class="stat-card"><div class="stat-name">{p['name']}</div><div class="stat-val">{monthly_cv[p['name']]}</div></div>""",
                        unsafe_allow_html=True)
        time.sleep(0.01)
    if mt >= MONTHLY_GOAL:
        st.balloons()
        time.sleep(1)

    # 季度团队目标
    qt = sum(qtr_cv.values())
    st.markdown(
        f'<div class="header-bordered" style="border-color:#54a0ff;margin-top:20px;">🌊 TEAM QUARTERLY GOAL (Q{q_num})</div>',
        unsafe_allow_html=True)
    ph_q = st.empty()
    for step in range(steps + 1):
        v = (qt / steps) * step
        ph_q.markdown(f"""
        <div class="sub-label" style="font-size:1.2em;text-align:center;">{int(v)} / {QUARTERLY_TEAM_GOAL} CVs</div>
        <div class="pit-container pit-height-boss">
            <div class="pit-fill-season" style="width:{min((v / QUARTERLY_TEAM_GOAL) * 100, 100)}%;">
                <div class="cat-squad" style="font-size:40px;top:5px;">🌊</div>
            </div>
        </div>
        """, unsafe_allow_html=True)
        time.sleep(0.01)

    # 个人卡片：恢复GP TARGET、LEVEL，佣金从指定Sheet读取
    st.markdown("<br>", unsafe_allow_html=True)
    st.markdown(f'<div class="header-bordered" style="border-color:#48dbfb;">❄️ PLAYER STATS (Q{q_num})</div>',
                unsafe_allow_html=True)
    r1 = st.columns(2)
    r2 = st.columns(2)
    cols = r1 + r2

    for i, p in enumerate(team):
        name = p["name"]
        qcv = qtr_cv[name]
        base_salary = p["base_salary"]
        is_lead = p["is_team_lead"]
        is_intern = (p["role"] == "Intern")

        # 计算GP相关
        gp_actual = df_sales[df_sales["Consultant"] == name]["GP"].sum() if not df_sales.empty else 0
        gp_target_multi = 4.5 if is_lead else 9.0
        gp_target = base_salary * gp_target_multi

        # 计算LEVEL
        level, _ = calculate_commission_tier(gp_actual, base_salary, is_lead)

        # 读取佣金（从指定Sheet）
        comm = get_commission_from_sheet(client, name) if not is_intern else 0

        with cols[i]:
            render_card(p, qcv, gp_actual, gp_target, comm, level, i)

    # 日志（修复Count列KeyError）
    if all_details:
        st.markdown("---")
        with st.expander(f"📜 MISSION LOGS ({curr_mm})", expanded=False):
            df = pd.DataFrame(all_details)
            dfm = df[df["Month"] == curr_mm]
            tabs = st.tabs([x["name"] for x in team])
            for i, t in enumerate(tabs):
                with t:
                    sub = dfm[dfm["Consultant"] == team[i]["name"]]
                    if sub.empty:
                        st.info("NO DATA")
                    else:
                        # 修复：groupby后sum Count列
                        agg = sub.groupby(["Company", "Position"])["Count"].sum().reset_index()
                        agg = agg.sort_values("Count", ascending=False)
                        agg["Count"] = agg["Count"].astype(str)
                        st.dataframe(agg, use_container_width=True, hide_index=True)
        with st.expander("📊 CV SUMMARY", expanded=False):
            df = pd.DataFrame(all_details)
            agg = df.groupby(["Company", "Position"])["Count"].sum().reset_index().sort_values("Count", ascending=False)
            agg.columns = ["CLIENT", "ROLE", "TOTAL CVs"]
            st.dataframe(agg, use_container_width=True, hide_index=True)


if __name__ == "__main__":
    main()
