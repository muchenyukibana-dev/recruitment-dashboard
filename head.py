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
    </style>
    """, unsafe_allow_html=True)


# --- 🧮 辅助函数 ---
def calculate_commission_tier(total_gp, base_salary):
    """
    根据 Paid GP 和 Base Salary 计算 Level 和 Multiplier
    """
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


def get_commission_pay_date(payment_date):
    """
    根据 Payment Date 计算佣金发放日（下个月 15 号）。
    增加安全检查。
    """
    if pd.isna(payment_date) or not payment_date:
        return None
    try:
        # 下个月年份
        year = payment_date.year + (payment_date.month // 12)
        # 下个月月份 (12月变成1月, 其他+1)
        month = (payment_date.month % 12) + 1
        return datetime(year, month, 15)
    except:
        return None


def normalize_text(text):
    return ''.join(c for c in unicodedata.normalize('NFD', str(text)) if unicodedata.category(c) != 'Mn').lower()


def safe_api_call(func, *args, **kwargs):
    """
    执行 Google API 调用，如果遇到 429 错误 (Quota exceeded)，则等待并重试。
    """
    max_retries = 5
    base_delay = 2  # 基础等待时间（秒）

    for i in range(max_retries):
        try:
            return func(*args, **kwargs)
        except APIError as e:
            # 检查是否为 429 错误
            if "429" in str(e):
                wait_time = base_delay * (2 ** i) + random.uniform(0, 1)  # 指数退避: 2s, 4s, 8s...
                time.sleep(wait_time)
                # 仅在最后一次尝试失败时抛出错误，否则继续循环重试
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


def fetch_historical_recruitment_stats(client, exclude_months):
    all_stats = []
    try:
        # 1. 获取所有月份 Sheet 名称 (只读取一次)
        sheet = safe_api_call(client.open_by_key, TEAM_CONFIG[0]['id'])
        worksheets = safe_api_call(sheet.worksheets)

        hist_months = []
        for ws in worksheets:
            title = ws.title.strip()
            if title.isdigit() and len(title) == 6:
                if title not in exclude_months:
                    hist_months.append(title)

        # 2. 遍历历史月份
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
    except Exception as e:
        return 0, 0, 0, []


# --- 💰 获取业绩数据 ---
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

                # 解析 Onboard Date
                onboard_str = row[col_onboard].strip()
                onboard_date = None
                for fmt in date_formats:
                    try:
                        onboard_date = datetime.strptime(onboard_str, fmt)
                        break
                    except:
                        pass
                if not onboard_date: continue

                # 匹配顾问
                matched = "Unknown"
                c_norm = normalize_text(consultant_name)
                for conf in TEAM_CONFIG:
                    conf_norm = normalize_text(conf['name'])
                    if conf_norm in c_norm or c_norm in conf_norm: matched = conf['name']; break
                    if conf_norm.split()[0] in c_norm: matched = conf['name']; break
                if matched == "Unknown": continue

                # 工资与 GP 计算
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

                # 解析 Payment Date
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
                    "Status": status
                })
        return pd.DataFrame(sales_records)
    except Exception as e:
        st.error(f"Error fetching sales data: {e}")
        return pd.DataFrame()


# --- 🚀 主程序 ---
def main():
    st.title("💼 Management Dashboard")

    col1, col2 = st.columns([1, 5])
    with col1:
        if st.button("🔄 LOAD Q4 DATA"):
            st.session_state['loaded'] = True

    if not st.session_state.get('loaded'):
        st.info("Click 'LOAD Q4 DATA' to view reports.")
        return

    client = connect_to_google()
    if not client: st.error("API Error"); return

    # === Q4 时间设置 ===
    year = 2025
    quarter_num = 4
    start_m = 10
    end_m = 12
    quarter_months_str = [f"{year}{m:02d}" for m in range(start_m, end_m + 1)]

    # 用于判断"本月"的基准
    now = datetime.now()

    with st.spinner("Analyzing Data (API requests throttled to prevent quota errors)..."):
        rec_stats_df, rec_details_df = fetch_recruitment_stats(client, quarter_months_str)
        time.sleep(1)

        rec_hist_df = fetch_historical_recruitment_stats(client, exclude_months=quarter_months_str)
        time.sleep(1)

        all_sales_df = fetch_all_sales_data(client)

        if not all_sales_df.empty:
            q4_mask = (all_sales_df['Onboard Date'].dt.year == year) & \
                      (all_sales_df['Onboard Date'].dt.month >= start_m) & \
                      (all_sales_df['Onboard Date'].dt.month <= end_m)
            sales_df_q4 = all_sales_df[q4_mask].copy()
            sales_df_hist = all_sales_df[~q4_mask].copy()
        else:
            sales_df_q4 = pd.DataFrame()
            sales_df_hist = pd.DataFrame()

    tab_dash, tab_details = st.tabs(["📊 DASHBOARD", "📝 DETAILS"])

    with tab_dash:
        # 1. Recruitment Stats
        st.markdown(f"### 🎯 Recruitment Stats (Q{quarter_num})")
        if not rec_stats_df.empty:
            rec_summary = rec_stats_df.groupby('Consultant')[['Sent', 'Int', 'Off']].sum().reset_index()
            rec_summary = rec_summary.sort_values(by='Sent', ascending=False)
            st.dataframe(
                rec_summary, use_container_width=True, hide_index=True,
                column_config={
                    "Sent": st.column_config.NumberColumn("Sent/Q", format="%d"),
                    "Int": st.column_config.NumberColumn("Int/Q", format="%d"),
                    "Off": st.column_config.NumberColumn("Off/Q", format="%d")
                }
            )
        else:
            st.warning(f"No recruitment data for Q{quarter_num}.")

        with st.expander("📜 Historical Recruitment Data (All Time)"):
            if not rec_hist_df.empty:
                hist_summary = rec_hist_df.groupby('Consultant')[['Sent', 'Int', 'Off']].sum().reset_index()
                hist_summary = hist_summary.sort_values(by='Sent', ascending=False)
                st.markdown("#### Aggregated History (Excl. Current Q)")
                st.dataframe(hist_summary, use_container_width=True, hide_index=True)
            else:
                st.info("No historical recruitment data found.")

        st.divider()

        # 2. Financial Performance (Q4)
        st.markdown(f"### 💰 Financial Performance (Q{quarter_num})")
        financial_summary = []
        
        if not sales_df_q4.empty:
            sales_df_q4['Commission Day Obj'] = sales_df_q4['Payment Date Obj'].apply(get_commission_pay_date)
            sales_df_q4['Commission Day'] = sales_df_q4['Commission Day Obj'].apply(
                lambda x: x.strftime("%Y-%m-%d") if (pd.notnull(x) and x is not None) else "")

        for conf in TEAM_CONFIG:
            c_name = conf['name']
            base = conf['base_salary']
            target = base * 9

            c_sales = sales_df_q4[sales_df_q4['Consultant'] == c_name] if not sales_df_q4.empty else pd.DataFrame()
            
            # 1. Booked GP: 入职即算 (Booked)
            booked_gp = c_sales['GP'].sum() if not c_sales.empty else 0

            # 2. Paid GP: 只有 Status = 'Paid' 的单子才算
            # ⚠️ 关键修正: Level 和 Target 达成率 均基于 Q4 期间 回款的 GP
            paid_sales = c_sales[c_sales['Status'] == 'Paid'] if not c_sales.empty else pd.DataFrame()
            paid_gp = paid_sales['GP'].sum() if not paid_sales.empty else 0

            # 3. 判定 Level (基于 Paid GP)
            level, multiplier = calculate_commission_tier(paid_gp, base)
            
            # 4. 计算 Est. Commission
            total_comm = 0
            if not c_sales.empty:
                for _, row in c_sales.iterrows():
                    # 只有 Paid 的单子才可能有佣金
                    if row['Status'] == 'Paid' and pd.notnull(row['Commission Day Obj']):
                        full_deal_comm = calculate_single_deal_commission(row['Candidate Salary'], multiplier)
                        potential_comm = full_deal_comm * row['Percentage']
                        
                        comm_date = row['Commission Day Obj']
                        # 佣金发放日 <= 今天 + 缓冲期，计入显示
                        if comm_date <= datetime.now() + timedelta(days=5):
                            total_comm += potential_comm

            # 5. 计算达成率 (基于 Paid GP)
            completion_rate = (paid_gp / target) if target > 0 else 0

            financial_summary.append({
                "Consultant": c_name, "Base Salary": base, "Target": target,
                "Booked GP": booked_gp,  # 仅作参考展示
                "Paid GP": paid_gp,      # 实际用于 Level 的
                "Achieved": completion_rate * 100,
                "Level": level, "Est. Commission": total_comm
            })

        df_fin = pd.DataFrame(financial_summary).sort_values(by='Paid GP', ascending=False)
        st.dataframe(
            df_fin, use_container_width=True, hide_index=True,
            column_config={
                "Base Salary": st.column_config.NumberColumn(format="$%d"),
                "Target": st.column_config.NumberColumn("Target Q", format="$%d"),
                "Booked GP": st.column_config.NumberColumn("Booked GP (Ref)", format="$%d", help="Total GP of onboarded deals"),
                "Paid GP": st.column_config.NumberColumn("Paid GP (Level)", format="$%d", help="GP collected, used for Level & Target"),
                "Achieved": st.column_config.NumberColumn("Achieved", format="%.1f%%"),
                "Est. Commission": st.column_config.NumberColumn("Payable Comm.", format="$%d"),
            }
        )

        # 3. Historical Financial Summary (Excl Q4)
        with st.expander("📜 Historical GP Summary (All Time)"):
            if not sales_df_hist.empty:
                st.markdown("#### Aggregated GP (Excl. Current Q4)")
                hist_fin_agg = sales_df_hist.groupby('Consultant')['GP'].sum().reset_index().sort_values(by='GP',
                                                                                                         ascending=False)
                st.dataframe(
                    hist_fin_agg,
                    use_container_width=True,
                    hide_index=True,
                    column_config={
                        "Consultant": st.column_config.TextColumn("Consultant"),
                        "GP": st.column_config.NumberColumn("Total GP", format="$%d")
                    }
                )
            else:
                st.info("No historical sales data found (excluding current Q4).")

    with tab_details:
        # A. Q4 Details
        st.markdown("### 🔍 Drill Down Details (Q4 Only)")
        for conf in TEAM_CONFIG:
            c_name = conf['name']
            fin_row = df_fin[df_fin['Consultant'] == c_name].iloc[0]
            header = f"👤 {c_name} | Paid GP: ${fin_row['Paid GP']:,.0f} (Lvl {fin_row['Level']})"

            with st.expander(header):
                st.markdown("#### 💸 Commission Breakdown")
                c_sales = sales_df_q4[sales_df_q4['Consultant'] == c_name] if not sales_df_q4.empty else pd.DataFrame()
                if not c_sales.empty:
                    # 使用基于 Paid GP 计算出的 Level Multiplier
                    multiplier = calculate_commission_tier(fin_row['Paid GP'], fin_row['Base Salary'])[1]

                    def get_comm_display(row):
                        if row['Status'] != 'Paid': return 0
                        base_comm = calculate_single_deal_commission(row['Candidate Salary'], multiplier)
                        return base_comm * row['Percentage']

                    c_sales['Comm Amt'] = c_sales.apply(get_comm_display, axis=1)
                    c_sales['Pct Display'] = c_sales['Percentage'].apply(lambda x: f"{x * 100:.0f}%")
                    
                    if 'Commission Day' not in c_sales.columns:
                        c_sales['Commission Day'] = ""

                    # 高亮 Status 是 Pending 的行可能有助于检查
                    st.dataframe(c_sales[['Onboard Date Str', 'Payment Date', 'Commission Day', 'Candidate Salary', 'Pct Display', 'GP', 'Status',
                                          'Comm Amt']],
                                 use_container_width=True, hide_index=True,
                                 column_config={
                                     "Commission Day": st.column_config.TextColumn("Commission Day"),
                                     "Comm Amt": st.column_config.NumberColumn("Comm ($)", format="$%.2f")
                                 })
                else:
                    st.info("No deals in Q4.")

                st.divider()
                st.markdown("#### 📝 Recruitment Logs (Q4)")
                if not rec_details_df.empty:
                    c_logs = rec_details_df[rec_details_df['Consultant'] == c_name]
                    if not c_logs.empty:
                        agg = c_logs.groupby(['Month', 'Company', 'Position', 'Status'])['Count'].sum().reset_index()
                        agg = agg.sort_values(by='Month', ascending=False)
                        st.dataframe(agg, use_container_width=True, hide_index=True)
                    else:
                        st.info("No logs.")
                else:
                    st.info("No data.")


if __name__ == "__main__":
    main()
