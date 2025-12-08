import streamlit as st
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import pandas as pd
import os
import time
from datetime import datetime
import unicodedata

# ==========================================
# 🔧 配置区域
# ==========================================
SALES_SHEET_ID = '1rCmyqOUOBn-644KpCtF5FZwBMEnRGHTKSSUBxzvOSkI'
SALES_TAB_NAME = 'Positions'

# 定义要加载的历史年份月份 (根据实际Sheet中的Tab名称添加)
# 格式: YYYYMM
HISTORY_MONTHS_TO_LOAD = [
    # 2025 Q1
    "202501", "202502", "202503",
    # 2025 Q2
    "202504", "202505", "202506",
    # 2025 Q3
    "202507", "202508", "202509",
    # 2025 Q4
    "202510", "202511", "202512"
]

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

    .stProgress > div > div > div > div { background-color: #28a745; }
    </style>
    """, unsafe_allow_html=True)


# --- 🧮 辅助函数 ---
def calculate_commission_tier(total_gp, base_salary):
    """
    计算当前季度的阶梯倍数。
    Target = 9 * Base Salary
    """
    target = 9 * base_salary
    if total_gp < target:
        return 0, 0  # 未达标，Multiplier 强制为 0
    elif total_gp < 13.5 * base_salary:
        return 1, 1
    elif total_gp < 22.5 * base_salary:
        return 2, 2
    else:
        return 3, 3


def calculate_single_deal_commission(candidate_salary, multiplier):
    """
    计算单笔基础佣金
    如果 Multiplier 为 0 (未达标)，则直接返回 0。
    """
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


def normalize_text(text):
    """去除重音符号 (Raúl -> raul)"""
    return ''.join(c for c in unicodedata.normalize('NFD', str(text)) if unicodedata.category(c) != 'Mn').lower()


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
    # 进度条
    prog_bar = st.progress(0)
    total_m = len(months)
    
    for idx, month in enumerate(months):
        for consultant in TEAM_CONFIG:
            s, i, o, d = internal_fetch_sheet_data(client, consultant, month)
            # 只要有数据就记录
            if s > 0 or i > 0 or o > 0:
                all_stats.append({"Consultant": consultant['name'], "Month": month, "Sent": s, "Int": i, "Off": o})
            if d: all_details.extend(d)
        prog_bar.progress((idx + 1) / total_m)
        
    prog_bar.empty()
    return pd.DataFrame(all_stats), pd.DataFrame(all_details)


def internal_fetch_sheet_data(client, conf, tab):
    try:
        sheet = client.open_by_key(conf['id'])
        try:
            ws = sheet.worksheet(tab)
        except gspread.exceptions.WorksheetNotFound:
            return 0, 0, 0, [] # Skip missing months
            
        rows = ws.get_all_values()
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
    except:
        return 0, 0, 0, []


# --- 💰 获取业绩数据 (所有历史) ---
def fetch_sales_data_all(client):
    """
    获取Sales Sheet中的所有数据，不筛选年份，用于 History Display
    """
    try:
        sheet = client.open_by_key(SALES_SHEET_ID)
        try:
            ws = sheet.worksheet(SALES_TAB_NAME)
        except:
            ws = sheet.get_worksheet(0)

        rows = ws.get_all_values()

        col_cons = -1
        col_onboard = -1
        col_pay = -1
        col_sal = -1
        col_pct = -1
        
        sales_records = []
        found_header = False

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
                if "POSITION" in row_upper and "PLACED" not in row_upper:
                    break

                if len(row) <= max(col_cons, col_onboard, col_sal): continue

                consultant_name = row[col_cons].strip()
                if not consultant_name: continue

                onboard_str = row[col_onboard].strip()
                onboard_date = None
                formats = ["%Y-%m-%d", "%d/%m/%Y", "%Y/%m/%d", "%m/%d/%Y", "%d-%b-%y", "%Y.%m.%d"]
                for fmt in formats:
                    try:
                        onboard_date = datetime.strptime(onboard_str, fmt)
                        break
                    except:
                        pass

                if not onboard_date: continue
                # 这里不筛选年份，读取全部历史

                matched = "Unknown"
                c_norm = normalize_text(consultant_name)
                for conf in TEAM_CONFIG:
                    conf_norm = normalize_text(conf['name'])
                    if conf_norm in c_norm or c_norm in conf_norm:
                        matched = conf['name']
                        break
                    if conf_norm.split()[0] in c_norm:
                        matched = conf['name']
                        break
                if matched == "Unknown": continue

                salary_raw = str(row[col_sal]).replace(',', '').replace('$', '').replace('MXN', '').replace('CNY', '').strip()
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
                            if p_float > 1.0: pct_val = p_float / 100.0
                            else: pct_val = p_float
                        except: pct_val = 1.0

                base_gp_factor = 1.0 if salary < 20000 else 1.5
                calc_gp = salary * base_gp_factor * pct_val

                pay_date_str = ""
                status = "Pending"
                if col_pay != -1 and len(row) > col_pay:
                    pay_date_str = row[col_pay].strip()
                    if len(pay_date_str) > 5: status = "Paid"

                sales_records.append({
                    "Consultant": matched,
                    "GP": calc_gp,
                    "Candidate Salary": salary,
                    "Percentage": pct_val,
                    "Onboard Date": onboard_date,
                    "Payment Date": pay_date_str,
                    "Status": status
                })

        return pd.DataFrame(sales_records)

    except Exception as e:
        st.error(f"Error: {e}")
        return pd.DataFrame()


# --- 🚀 主程序 ---
def main():
    st.title("💼 Management Dashboard")

    # 配置：当前考核季度
    current_year = 2025
    # 这里定义 Q3 考核期
    target_q_start, target_q_end = 7, 9 
    target_q_name = "Q3"

    col1, col2 = st.columns([1, 5])
    with col1:
        if st.button(f"🔄 LOAD DATA (All History)"):
            st.session_state['loaded'] = True

    if not st.session_state.get('loaded'):
        st.info(f"Click the button to load database.")
        return

    client = connect_to_google()
    if not client: st.error("API Error"); return

    with st.spinner("Analyzing Database..."):
        # 1. 获取所有历史 Sales 数据 (包含过去、现在Q3、未来)
        sales_df_all = fetch_sales_data_all(client)
        
        # 2. 获取所有 Recuitment 数据 (根据 HISTORY_MONTHS_TO_LOAD 配置)
        rec_stats_all_df, rec_details_df = fetch_recruitment_stats(client, HISTORY_MONTHS_TO_LOAD)

    # === 数据切片：当前考核季度 (Q3) ===
    # 用于上半部分显示考核详情
    sales_df_current_q = pd.DataFrame()
    if not sales_df_all.empty:
        # 筛选条件：年份2025且月份在7-9之间
        sales_df_current_q = sales_df_all[
            sales_df_all['Onboard Date'].apply(
                lambda x: x.year == current_year and target_q_start <= x.month <= target_q_end
            )
        ]
    
    # Rec stats for current Q
    rec_stats_current_q = pd.DataFrame()
    if not rec_stats_all_df.empty:
        current_q_months = [f"{current_year}{m:02d}" for m in range(target_q_start, target_q_end + 1)]
        rec_stats_current_q = rec_stats_all_df[rec_stats_all_df['Month'].isin(current_q_months)]

    # 格式化日期列用于展示
    if not sales_df_current_q.empty:
        sales_df_current_q['Onboard Date Str'] = sales_df_current_q['Onboard Date'].apply(lambda x: x.strftime("%Y-%m-%d"))
    
    # 历史数据(All) 也格式化一下
    if not sales_df_all.empty:
        sales_df_all['Onboard Date Str'] = sales_df_all['Onboard Date'].apply(lambda x: x.strftime("%Y-%m-%d"))


    # === 页面展示 ===
    tab_dash, tab_details = st.tabs(["📊 DASHBOARD", "📝 DETAILS"])

    with tab_dash:
        # ==========================
        # SECTION 1: CURRENT QUARTER PERFORMANCE
        # ==========================
        st.markdown(f"### 🎯 Current Quarter Performance ({target_q_name} {current_year})")
        
        # 1.1 Recruitment (Current Q Only)
        col_q_rec, col_q_fin = st.columns([1, 1.5])
        
        with col_q_rec:
            st.caption("Recruitment Stats (This Quarter)")
            if not rec_stats_current_q.empty:
                rec_summary_q = rec_stats_current_q.groupby('Consultant')[['Sent', 'Int', 'Off']].sum().reset_index()
                rec_summary_q = rec_summary_q.sort_values(by='Sent', ascending=False)
                st.dataframe(
                    rec_summary_q, use_container_width=True, hide_index=True,
                    column_config={
                        "Sent": st.column_config.NumberColumn("Sent", format="%d"),
                        "Int": st.column_config.NumberColumn("Int", format="%d"),
                        "Off": st.column_config.NumberColumn("Off", format="%d")
                    }
                )
            else:
                st.warning("No recruitment data for this quarter.")

        # 1.2 Financial (Current Q Only) - With Commission Logic
        with col_q_fin:
            st.caption("Financial & Commission (Strict Target: 9x Base)")
            fin_summary_q = []
            for conf in TEAM_CONFIG:
                c_name = conf['name']
                base = conf['base_salary']
                target = base * 9 

                c_sales = sales_df_current_q[sales_df_current_q['Consultant'] == c_name] if not sales_df_current_q.empty else pd.DataFrame()
                total_gp = c_sales['GP'].sum() if not c_sales.empty else 0

                # 严格的佣金计算
                level, multiplier = calculate_commission_tier(total_gp, base)
                total_comm = 0
                if not c_sales.empty:
                    for _, row in c_sales.iterrows():
                        if row['Status'] == 'Paid':
                            full_deal_comm = calculate_single_deal_commission(row['Candidate Salary'], multiplier)
                            total_comm += full_deal_comm * row['Percentage']

                completion_rate = (total_gp / target) if target > 0 else 0
                
                fin_summary_q.append({
                    "Consultant": c_name, 
                    "Total GP": total_gp, 
                    "Achieved": completion_rate,
                    "Est. Commission": total_comm,
                    "Lvl": level
                })

            df_fin_q = pd.DataFrame(fin_summary_q).sort_values(by='Total GP', ascending=False)
            st.dataframe(
                df_fin_q, use_container_width=True, hide_index=True,
                column_config={
                    "Total GP": st.column_config.NumberColumn("Q3 GP", format="$%d"),
                    "Achieved": st.column_config.ProgressColumn("Achieved", format="%.1f%%", min_value=0, max_value=1),
                    "Est. Commission": st.column_config.NumberColumn("Comm.", format="$%d"),
                    "Lvl": st.column_config.NumberColumn("Tier", format="%d")
                }
            )

        st.divider()

        # ==========================
        # SECTION 2: HISTORY (ALL TIME)
        # ==========================
        st.markdown(f"### 📜 HISTORY (All Time / Total)")
        
        col_h1, col_h2 = st.columns(2)
        
        # 2.1 Recruitment History (Aggregate of all loaded months)
        with col_h1:
            st.caption("Total Recruitment Activity (All Loaded Months)")
            if not rec_stats_all_df.empty:
                rec_hist = rec_stats_all_df.groupby('Consultant')[['Sent', 'Int', 'Off']].sum().reset_index()
                rec_hist = rec_hist.sort_values(by='Off', ascending=False) # 按 Offer 排序
                st.dataframe(
                    rec_hist, use_container_width=True, hide_index=True,
                    column_config={
                        "Sent": st.column_config.NumberColumn("Total Sent", format="%d"),
                        "Int": st.column_config.NumberColumn("Total Int", format="%d"),
                        "Off": st.column_config.NumberColumn("Total Off", format="%d")
                    }
                )
            else:
                st.info("No historical recruitment data.")

        # 2.2 Financial History (Aggregate of all loaded sales)
        with col_h2:
            st.caption("Total Financial Performance (All Time GP)")
            if not sales_df_all.empty:
                # 简单聚合 GP
                sales_hist = sales_df_all.groupby('Consultant')['GP'].sum().reset_index()
                sales_hist = sales_hist.sort_values(by='GP', ascending=False)
                
                # 统计 Deal 数量
                deal_counts = sales_df_all.groupby('Consultant').size().reset_index(name='Deals')
                sales_hist = pd.merge(sales_hist, deal_counts, on='Consultant')

                st.dataframe(
                    sales_hist, use_container_width=True, hide_index=True,
                    column_config={
                        "Consultant": "Consultant",
                        "Deals": st.column_config.NumberColumn("Placements (#)"),
                        "GP": st.column_config.NumberColumn("Total GP Generated", format="$%d"),
                    }
                )
            else:
                st.info("No historical sales data.")

    # === 详情页展示 ===
    with tab_details:
        st.markdown("### 🔍 Current Quarter Drill Down")
        
        # 只展示 Current Quarter 的详细佣金计算详情
        # 历史数据过于庞大且佣金规则可能变动，详情页专注于当前算钱
        
        for conf in TEAM_CONFIG:
            c_name = conf['name']
            # 从上面算好的 df_fin_q 里取数据
            fin_row = df_fin_q[df_fin_q['Consultant'] == c_name].iloc[0]
            
            header = f"👤 {c_name} | Q3 GP: ${fin_row['Total GP']:,.0f} | Est. Comm: ${fin_row['Est. Commission']:,.0f}"

            with st.expander(header):
                st.markdown("#### 💸 Q3 Commission Breakdown")
                
                c_sales_q = sales_df_current_q[sales_df_current_q['Consultant'] == c_name] if not sales_df_current_q.empty else pd.DataFrame()
                
                if not c_sales_q.empty:
                    # 重新计算 multiplier 用于展示
                    multiplier = calculate_commission_tier(fin_row['Total GP'], conf['base_salary'])[1]
                    
                    def get_comm_display(row):
                        if row['Status'] != 'Paid': return 0
                        base_comm = calculate_single_deal_commission(row['Candidate Salary'], multiplier)
                        return base_comm * row['Percentage']

                    c_sales_q['Commission'] = c_sales_q.apply(get_comm_display, axis=1)
                    c_sales_q['Pct Display'] = c_sales_q['Percentage'].apply(lambda x: f"{x*100:.0f}%")

                    st.dataframe(
                        c_sales_q[['Onboard Date Str', 'Payment Date', 'Candidate Salary', 'Pct Display', 'GP', 'Commission']],
                        use_container_width=True, hide_index=True
                    )
                    
                    if multiplier > 0:
                         st.success(f"✅ Target Met! Multiplier: x{multiplier}")
                    else:
                        st.warning("⚠️ Target Not Met (Commission = 0)")
                else:
                    st.info("No deals in Q3.")


if __name__ == "__main__":
    main()
