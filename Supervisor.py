import streamlit as st
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import pandas as pd
import os
from datetime import datetime
import unicodedata

# ==========================================
# 🔧 配置区域
# ==========================================
SALES_SHEET_ID = '1rCmyqOUOBn-644KpCtF5FZwBMEnRGHTKSSUBxzvOSkI'
SALES_TAB_NAME = 'Positions'

TEAM_CONFIG = [
    {"name": "Raul Solis", "id": "1vQuN-iNBRUug5J6gBMX-52jp6oogbA77SaeAf9j_zYs", "keyword": "Name", "base_salary": 11000},
    {"name": "Estela Peng", "id": "1sUkffAXzWnpzhhmklqBuwtoQylpR1U18zqBQ-lsp7Z4", "keyword": "姓名", "base_salary": 20800},
    {"name": "Ana Cruz", "id": "1VMVw5YCV12eI8I-VQSXEKg86J2IVZJEgjPJT7ggAFD0", "keyword": "Name", "base_salary": 13000},
    {"name": "Karina Albarran", "id": "1zc4ghvfjIxH0eJ2aXfopOWHqiyTDlD8yFNjBzpH07D8", "keyword": "Name", "base_salary": 15000},
]

st.set_page_config(page_title="Management Dashboard", page_icon="💼", layout="wide")

# --- 🎨 样式 ---
st.markdown("""
    <style>
    .stApp { background-color: #FFFFFF; color: #000000; }
    </style>
    """, unsafe_allow_html=True)

# --- Helper functions ---

def calculate_commission_tier(total_gp, base_salary):
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
    return ''.join(c for c in unicodedata.normalize('NFD', str(text)) if unicodedata.category(c) != 'Mn').lower()

# --- Google connect ---

def connect_to_google():
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    if "gcp_service_account" in st.secrets:
        try:
            creds_dict = dict(st.secrets["gcp_service_account"])
            creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
            return gspread.authorize(creds)
        except Exception:
            return None
    return None

# --- Recruitment data ---
# (Omitted: identical to user code, no changes required here)

# --- Fetch ALL sales data ---
# (Same as your code, no changes needed)

# --- 🚀 Main ---

def main():
    st.title("💼 Management Dashboard")

    if st.button("🔄 LOAD Q4 DATA"):
        st.session_state['loaded'] = True

    if not st.session_state.get('loaded'):
        st.info("Click 'LOAD Q4 DATA' to view reports.")
        return

    client = connect_to_google()
    if not client:
        st.error("API Error")
        return

    # Quarter settings
    year = 2025
    start_m = 10
    end_m = 12
    quarter_months_str = [f"{year}{m:02d}" for m in range(start_m, end_m + 1)]

    # Fetch data
    # (Same blocks as original code)

    tab_dash, tab_details = st.tabs(["📊 DASHBOARD", "📝 DETAILS"])

    with tab_dash:
        # (Recruitment unchanged)

        # === Q4 Financial ===
        financial_summary = []
        for conf in TEAM_CONFIG:
            c_name = conf['name']
            base = conf['base_salary']
            target = base * 9
            c_sales = sales_df_q4[sales_df_q4['Consultant'] == c_name]
            total_gp = c_sales['GP'].sum() if not c_sales.empty else 0

            level, multiplier = calculate_commission_tier(total_gp, base)
            total_comm = 0
            for _, row in c_sales.iterrows():
                if row['Status'] == 'Paid':
                    total_comm += calculate_single_deal_commission(row['Candidate Salary'], multiplier) * row['Percentage']

            completion_rate = total_gp / target if target > 0 else 0

            financial_summary.append({
                "Consultant": c_name,
                "Base Salary": base,
                "Target": target,
                "Total GP": total_gp,
                "Completion": completion_rate,
                "Level": level,
                "Est. Commission": total_comm
            })

        df_fin = pd.DataFrame(financial_summary).sort_values(by='Total GP', ascending=False)
        st.dataframe(
            df_fin,
            use_container_width=True,
            hide_index=True,
            column_config={
                "Base Salary": st.column_config.NumberColumn(format="$%d"),
                "Target": st.column_config.NumberColumn(format="$%d"),
                "Total GP": st.column_config.NumberColumn(format="$%d"),
                "Completion": st.column_config.ProgressColumn("Achieved", format="%.1f%%", min_value=0, max_value=1),
                "Est. Commission": st.column_config.NumberColumn(format="$%d"),
            }
        )

        # === Updated Historical Financial (B1) ===
        with st.expander("📜 Historical Financial Performance (All Time)"):
            if not sales_df_hist.empty:

                hist_fin = []
                for conf in TEAM_CONFIG:
                    c_name = conf['name']
                    base = conf['base_salary']
                    target = base * 9

                    c_sales_hist = sales_df_hist[sales_df_hist['Consultant'] == c_name]
                    total_gp_hist = c_sales_hist['GP'].sum()

                    level, multiplier = calculate_commission_tier(total_gp_hist, base)

                    total_comm_hist = 0
                    for _, row in c_sales_hist.iterrows():
                        if row['Status'] == 'Paid':
                            total_comm_hist += calculate_single_deal_commission(row['Candidate Salary'], multiplier) * row['Percentage']

                    completion_rate_hist = total_gp_hist / target if target > 0 else 0

                    hist_fin.append({
                        "Consultant": c_name,
                        "Base Salary": base,
                        "Target": target,
                        "Total GP": total_gp_hist,
                        "Completion": completion_rate_hist,
                        "Level": level,
                        "Est. Commission": total_comm_hist
                    })

                df_hist_fin = pd.DataFrame(hist_fin).sort_values(by='Total GP', ascending=False)

                st.dataframe(
                    df_hist_fin,
                    use_container_width=True,
                    hide_index=True,
                    column_config={
                        "Base Salary": st.column_config.NumberColumn(format="$%d"),
                        "Target": st.column_config.NumberColumn(format="$%d"),
                        "Total GP": st.column_config.NumberColumn(format="$%d"),
                        "Completion": st.column_config.ProgressColumn("Achieved", format="%.1f%%", min_value=0, max_value=1),
                        "Est. Commission": st.column_config.NumberColumn(format="$%d"),
                    }
                )

            else:
                st.info("No historical sales data found.")

    # Details tab (unchanged except no impact)

if __name__ == "__main__":
    main()
