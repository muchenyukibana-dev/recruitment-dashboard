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
# 🔧 配置区域 (保持不变)
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


# --- 🧮 辅助工具函数 (保持原有逻辑) ---
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


def connect_to_google():
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    if "gcp_service_account" in st.secrets:
        creds = ServiceAccountCredentials.from_json_keyfile_dict(dict(st.secrets["gcp_service_account"]), scope)
        return gspread.authorize(creds)
    return None


def get_quarter_str(date_obj):
    if pd.isna(date_obj): return "Unknown"
    return f"{date_obj.year} Q{(date_obj.month - 1) // 3 + 1}"


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


# --- 🛰️ 数据抓取逻辑 (核心优化：集成缓存) ---

def fetch_role_from_personal_sheet(client, sheet_id):
    try:
        sheet = safe_api_call(client.open_by_key, sheet_id)
        ws = safe_api_call(sheet.worksheet, 'Credentials')
        return (safe_api_call(ws.acell, 'B1').value or "Consultant").strip()
    except:
        return "Consultant"


def internal_fetch_sheet_data(client, conf, tab):
    try:
        sheet = safe_api_call(client.open_by_key, conf['id'])
        ws = safe_api_call(sheet.worksheet, tab)
        rows = safe_api_call(ws.get_all_values)
        details, cs, ci, co = [], 0, 0, 0
        target_key = conf.get('keyword', 'Name')
        COMPANY_KEYS, POSITION_KEYS, STAGE_KEYS = ["Company", "Client", "Cliente", "公司", "公司名称" ,"客户"], ["Position", "Role",
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
                res.append({"Consultant": conf['name'], "Month": tab, "Company": b['c'], "Position": b['p'],
                            "Status": "Offered" if is_off else ("Interviewed" if is_int else "Sent"), "Count": 1})
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


def fetch_sales_history(client):
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
                if not onboard_date or onboard_date.year < 2024: continue

                matched = "Unknown"
                for conf in TEAM_CONFIG:
                    if normalize_text(conf['name']) in normalize_text(c_name_raw): matched = conf['name']; break
                if matched == "Unknown": continue

                sal = float(str(row[col_sal]).replace(',', '').replace('$', '').strip() or 0)
                pct = 1.0
                if col_pct != -1 and len(row) > col_pct:
                    try:
                        p_val = float(str(row[col_pct]).replace('%', '').strip())
                        pct = p_val / 100 if p_val > 1 else p_val
                    except:
                        pct = 1.0

                pay_date_obj, status = None, "Pending"
                if col_pay != -1 and len(row) > col_pay and len(row[col_pay].strip()) > 5:
                    status = "Paid"
                    for fmt in ["%Y-%m-%d", "%d/%m/%Y", "%m/%d/%Y"]:
                        try:
                            pay_date_obj = datetime.strptime(row[col_pay].strip(), fmt); break
                        except:
                            pass

                records.append({
                    "Consultant": matched, "GP": sal * (1.5 if sal >= 20000 else 1.0) * pct,
                    "Salary": sal, "Pct": pct, "Status": status, "PayDateObj": pay_date_obj,
                    "Quarter": get_quarter_str(onboard_date)
                })
    except:
        pass
    return pd.DataFrame(records)


@st.cache_data(ttl=600)
def get_all_dashboard_data():
    client = connect_to_google()
    if not client: return None

    sales_df = fetch_sales_history(client)
    team_processed = []
    q_cv_counts, prev_q_counts = {}, {}
    all_logs = []
    current_month_str = datetime.now().strftime("%Y%m")
    m_cv_data = []

    for conf in TEAM_CONFIG:
        role_val = fetch_role_from_personal_sheet(client, conf['id'])
        is_lead = "Team Lead" in role_val.lower()
        c_conf = {**conf, "role": role_val, "is_team_lead": is_lead, "title_display": role_val}
        team_processed.append(c_conf)

        # CV Counts
        q_sent = 0
        curr_m_logs = []
        for m_str in curr_q_months:
            s, i, o, d = internal_fetch_sheet_data(client, c_conf, m_str)
            q_sent += s
            if m_str == current_month_str: curr_m_logs = d
        q_cv_counts[conf['name']] = q_sent
        m_cv_data.append({"name": conf['name'], "count": sum([l['Count'] for l in curr_m_logs])})
        all_logs.extend(curr_m_logs)

        pq_sent = 0
        for pm_str in prev_q_months:
            s, _, _, _ = internal_fetch_sheet_data(client, c_conf, pm_str)
            pq_sent += s
        prev_q_counts[conf['name']] = pq_sent

    return {
        "team": team_processed, "sales": sales_df, "q_cv": q_cv_counts,
        "pq_cv": prev_q_counts, "m_cv": m_cv_data, "logs": all_logs
    }


# ==========================================
# 🎨 UI 渲染函数 (保持 CSS 和风格)
# ==========================================

st.set_page_config(page_title="Fill The Pit", page_icon="🎮", layout="wide")
st.markdown("""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Press+Start+2P&display=swap');
    @import url('https://fonts.googleapis.com/css2?family=Fredoka+One&display=swap');
    .stApp { background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); font-family: 'Press Start 2P', monospace; }
    h1 { text-shadow: 4px 4px 0px #000; color: #FFD700 !important; text-align: center; font-size: 3.5em !important; -webkit-text-stroke: 2px #000; }
    .stButton { display: flex; justify-content: center; width: 100%; margin-bottom: 20px;}
    .stButton>button { 
        background-color: #FF4757; color: white; border: 4px solid #000; border-radius: 15px; 
        font-family: 'Press Start 2P', monospace; font-size: 24px !important; padding: 20px 40px !important;
        box-shadow: 0px 8px 0px #a71c2a; width: 80%; transition: all 0.1s;
    }
    .pit-container { background-color: #eee; border: 3px solid #000; border-radius: 12px; width: 100%; position: relative; margin-bottom: 12px; overflow: hidden; }
    .pit-height-std { height: 25px; }
    .pit-height-boss { height: 60px; border-width: 4px; }
    @keyframes barberpole { from { background-position: 0 0; } to { background-position: 50px 50px; } }
    .pit-fill-boss { background: linear-gradient(270deg, #ff6b6b, #feca57, #48dbfb, #ff9ff3, #54a0ff); background-size: 400% 400%; animation: rainbow-move 6s ease infinite; height: 100%; display: flex; align-items: center; justify-content: flex-end; }
    @keyframes rainbow-move { 0% { background-position: 0% 50%; } 50% { background-position: 100% 50%; } 100% { background-position: 0% 50%; } }
    .pit-fill-season { background-image: linear-gradient(45deg, #3742fa 25%, #5352ed 25%, #5352ed 50%, #3742fa 50%, #3742fa 75%, #5352ed 75%, #5352ed 100%); background-size: 50px 50px; animation: barberpole 3s linear infinite; height: 100%; display: flex; align-items: center; justify-content: flex-end; }
    .money-fill { background-image: linear-gradient(45deg, #2ed573 25%, #7bed9f 25%, #7bed9f 50%, #2ed573 50%, #2ed573 75%, #7bed9f 75%, #7bed9f 100%); background-size: 50px 50px; animation: barberpole 4s linear infinite; height: 100%; display: flex; align-items: center; justify-content: flex-end; }
    .cv-fill { background-image: linear-gradient(45deg, #ff9ff3 25%, #f368e0 25%, #f368e0 50%, #ff9ff3 50%, #ff9ff3 75%, #f368e0 75%, #f368e0 100%); background-size: 50px 50px; animation: barberpole 3s linear infinite; height: 100%; display: flex; align-items: center; justify-content: flex-end; }
    .player-card { background-color: #FFF; border: 4px solid #000; border-radius: 15px; padding: 20px; margin-bottom: 30px; color: #333; box-shadow: 8px 8px 0px rgba(0,0,0,0.2); }
    .card-border-1 { border-bottom: 6px solid #ff6b6b; } .card-border-2 { border-bottom: 6px solid #feca57; } .card-border-3 { border-bottom: 6px solid #48dbfb; } .card-border-4 { border-bottom: 6px solid #ff9ff3; }
    .status-badge-pass { background-color: #2ed573; color: white; padding: 8px 12px; border-radius: 20px; border: 2px solid #000; font-size: 0.6em; }
    .status-badge-loading { background-color: #feca57; color: #000; padding: 8px 12px; border-radius: 20px; border: 2px solid #000; font-size: 0.6em; }
    .comm-unlocked { background-color: #fff4e6; border: 2px solid #ff9f43; border-radius: 10px; color: #e67e22; text-align: center; padding: 10px; margin-top: 15px; font-weight: bold; font-size: 0.9em; }
    .comm-locked { background-color: #f1f2f6; border: 2px solid #ced6e0; border-radius: 10px; color: #a4b0be; text-align: center; padding: 10px; margin-top: 15px; font-size: 0.8em; }
    .header-bordered { background-color: #FFF; border: 4px solid #000; border-radius: 15px; box-shadow: 6px 6px 0px #000; padding: 20px; text-align: center; margin-bottom: 25px; }
    .sub-label { font-family: 'Fredoka One', sans-serif; font-size: 0.8em; color: #FFF; margin-bottom: 5px; text-transform: uppercase; text-shadow: 1px 1px 0px #000; }
    .stat-card { background-color: #fff; border: 3px solid #000; border-radius: 10px; padding: 10px; text-align: center; }
    .stat-val { color: #000; font-size: 1.2em; font-weight: bold; }
    .stat-name { color: #555; font-size: 0.7em; }
    </style>
    """, unsafe_allow_html=True)


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


def render_player_card(conf, q_cvs, pq_cvs, sales_df, idx):
    name, role, is_lead, base = conf['name'], conf['role'], conf['is_team_lead'], conf['base_salary']
    c_sales_curr = sales_df[(sales_df['Consultant'] == name) & (sales_df['Quarter'] == CURRENT_Q_STR)]
    c_sales_prev = sales_df[(sales_df['Consultant'] == name) & (sales_df['Quarter'] == PREV_Q_STR)]

    booked_gp_curr = c_sales_curr['GP'].sum()
    target_gp = base * (4.5 if is_lead else 9.0)
    is_q_curr = (booked_gp_curr >= target_gp or q_cvs >= CV_TARGET_QUARTERLY) if role != "Intern" else (
                q_cvs >= CV_TARGET_QUARTERLY)
    is_q_prev = (c_sales_prev['GP'].sum() >= target_gp or pq_cvs >= CV_TARGET_QUARTERLY) if role != "Intern" else (
                pq_cvs >= CV_TARGET_QUARTERLY)

    # Commission Logic
    total_comm = 0
    now_date = datetime.now()
    target_pay_year, target_pay_month = (now_date.year, now_date.month) if now_date.day <= 15 else (
        now_date.year + 1 if now_date.month == 12 else now_date.year, 1 if now_date.month == 12 else now_date.month + 1)

    if role != "Intern":
        # 我们把原来的 is_qual 挪个位置，增加一个 q_label 标签
        for q_label, q_df, is_qual in [("current", c_sales_curr, is_q_curr), ("prev", c_sales_prev, is_q_prev)]:
            if not q_df.empty:  # <--- 注意：这里去掉了 is_qual，让没达标的单子也能进入计算
                running_gp = 0
                for _, row in q_df.sort_index().iterrows():
                    running_gp += row['GP']
                    if row['Status'] == 'Paid':
                        p_date = get_commission_pay_date(row['PayDateObj'])

                        # 判断是否属于本月发放周期
                        if p_date and p_date.year == target_pay_year and p_date.month == target_pay_month:

                            # --- 核心判断逻辑修改 ---
                            # 如果是上个季度的单子，必须上个季度达标(is_qual)才发
                            # 如果是本季度的单子，即便目前没达标(is_qual为False)，只要回款了就发
                            if q_label == "current" or (q_label == "prev" and is_qual):
                                _, mult = calculate_commission_tier(running_gp, base, is_lead)

                                # 达标保底逻辑：如果没到GP门槛但 CV 够了，按最低档发
                                if mult == 0:
                                    _, mult = calculate_commission_tier(base * 10, base, is_lead)

                                deal_comm = calculate_single_deal_commission(row['Salary'], mult) * row['Pct']
                                total_comm += deal_comm

    if is_lead:
        ov_mask = (sales_df['Status'] == 'Paid') & (sales_df['Consultant'] != name) & (
        sales_df['Consultant'] != "Estela Peng")

        for _, row in sales_df[ov_mask].iterrows():
            p_date = get_commission_pay_date(row['PayDateObj'])

            # 核心判断：只要回款日期属于本月发放周期，就计入主管津贴
            if p_date and p_date.year == target_pay_year and p_date.month == target_pay_month:
               total_comm += 1000 * row['Pct']

    # UI
    border = f"card-border-{(idx % 4) + 1}"
    status_tag = '<span class="status-badge-pass">LEVEL UP! 🌟</span>' if is_q_curr else '<span class="status-badge-loading">LOADING... 🚀</span>'
    st.markdown(
        f'<div class="player-card {border}"><div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:15px;"><div><b style="font-size:1.1em;">{name} {"👑" if is_lead else ""}</b><br><small style="color:#999;">{role}</small></div>{status_tag}</div>',
        unsafe_allow_html=True)

    if role == "Intern":
        p = (q_cvs / CV_TARGET_QUARTERLY * 100)
        st.markdown(
            f'<div class="sub-label">Q. CVS ({p:.1f}%)</div><div class="pit-container pit-height-std"><div class="cv-fill" style="width:{min(p, 100)}%;"></div></div>',
            unsafe_allow_html=True)
    else:
        gp_p, cv_p = (booked_gp_curr / target_gp * 100), (q_cvs / CV_TARGET_QUARTERLY * 100)
        st.markdown(
            f'<div class="sub-label">GP TARGET ({gp_p:.1f}%)</div><div class="pit-container pit-height-std"><div class="money-fill" style="width:{min(gp_p, 100)}%;"></div></div>',
            unsafe_allow_html=True)
        st.markdown('<div style="font-size:0.5em; color:#666; margin:5px 0;">OR RECRUITMENT GOAL:</div>',
                    unsafe_allow_html=True)
        st.markdown(
            f'<div class="sub-label">Q. CVS ({cv_p:.1f}%)</div><div class="pit-container pit-height-std"><div class="cv-fill" style="width:{min(cv_p, 100)}%;"></div></div>',
            unsafe_allow_html=True)

    if role != "Intern":
        if total_comm > 0:
            st.markdown(f'<div class="comm-unlocked">💰 THIS MONTH: ${total_comm:,.0f}</div>', unsafe_allow_html=True)
        else:
            st.markdown(
                f'<div class="comm-locked">🔒 {"LOCKED (WAITING PAY)" if is_q_curr else "LOCKED (TARGET NOT MET)"}</div>',
                unsafe_allow_html=True)
    st.markdown("</div>", unsafe_allow_html=True)


# ==========================================
# 🎮 主程序
# ==========================================

def main():
    st.title("👾 FILL THE PIT 👾")

    if 'data' not in st.session_state:
        col1, col2, col3 = st.columns([1, 3, 1])
        with col2:
            if st.button("🚩 PRESS START"):
                with st.spinner("🛰️ SCANNING SECTOR..."):
                    st.session_state.data = get_all_dashboard_data()
                    st.rerun()
    else:
        data = st.session_state.data
        # Boss Bar 1: MONTHLY
        st.markdown(
            f'<div class="header-bordered" style="border-color:#feca57;">🏆 TEAM MONTHLY GOAL ({curr_q_months[-1]})</div>',
            unsafe_allow_html=True)
        m_total = sum([d['count'] for d in data['m_cv']])
        render_boss_bar(m_total, QUARTERLY_TEAM_GOAL, "pit-fill-boss", "🔥")

        cols = st.columns(len(data['m_cv']))
        for idx, d in enumerate(data['m_cv']):
            with cols[idx]: st.markdown(
                f'<div class="stat-card"><div class="stat-name">{d["name"]}</div><div class="stat-val">{int(d["count"])}</div></div>',
                unsafe_allow_html=True)

        # Boss Bar 2: QUARTERLY
        st.markdown(
            f'<div class="header-bordered" style="border-color:#54a0ff; margin-top:20px;">🌊 TEAM QUARTERLY GOAL ({CURRENT_Q_STR})</div>',
            unsafe_allow_html=True)
        render_boss_bar(sum(data['q_cv'].values()), QUARTERLY_TEAM_GOAL, "pit-fill-season", "🌊")

        # Player Hub
        st.markdown("<br><div class=\"header-bordered\" style=\"border-color:#48dbfb;\">❄️ PLAYER STATS</div>",
                    unsafe_allow_html=True)
        p_row1, p_row2 = st.columns(2), st.columns(2)
        all_p_cols = p_row1 + p_row2
        for i, conf in enumerate(data['team']):
            with all_p_cols[i]: render_player_card(conf, data['q_cv'][conf['name']], data['pq_cv'][conf['name']],
                                                   data['sales'], i)

        # Mission Logs
        if data['logs']:
            st.markdown("---")
            with st.expander(f"📜 MISSION LOGS ({curr_q_months[-1]})"):
                log_df = pd.DataFrame(data['logs'])
                tabs = st.tabs([c['name'] for c in data['team']])
                for i, tab in enumerate(tabs):
                    with tab:
                        p_logs = log_df[log_df['Consultant'] == data['team'][i]['name']]
                        if not p_logs.empty:
                            st.dataframe(
                                p_logs.groupby(['Company', 'Position'])['Count'].sum().reset_index().sort_values(
                                    'Count', ascending=False), use_container_width=True, hide_index=True)
                        else:
                            st.info("NO DATA")


if __name__ == "__main__":
    main()
