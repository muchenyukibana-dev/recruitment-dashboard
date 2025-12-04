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

TEAM_CONFIG = [
    {"name": "Raul Solis", "keyword": "Name", "base_salary": 11000},
    {"name": "Estela Peng", "keyword": "姓名", "base_salary": 20800},
    {"name": "Ana Cruz", "keyword": "Name", "base_salary": 13000},
    {"name": "Karina Albarran", "keyword": "Name", "base_salary": 15000},
]

# 补全 ID (为了代码简洁，这里硬编码填入)
for t in TEAM_CONFIG:
    if "Raul" in t['name']: t['id'] = "1vQuN-iNBRUug5J6gBMX-52jp6oogbA77SaeAf9j_zYs"
    elif "Estela" in t['name']: t['id'] = "1sUkffAXzWnpzhhmklqBuwtoQylpR1U18zqBQ-lsp7Z4"
    elif "Ana" in t['name']: t['id'] = "1VMVw5YCV12eI8I-VQSXEKg86J2IVZJEgjPJT7ggAFD0"
    elif "Karina" in t['name']: t['id'] = "1zc4ghvfjIxH0eJ2aXfopOWHqiyTDlD8yFNjBzpH07D8"

st.set_page_config(page_title="Management Dashboard", page_icon="💼", layout="wide")

# --- 🎨 样式 ---
st.markdown("""
    <style>
    .stApp { background-color: #FFFFFF; color: #000000; }
    h1, h2, h3, h4 { color: #333333 !important; font-family: 'Arial', sans-serif; }
    .stButton>button { background-color: #0056b3; color: white; border-radius: 4px; padding: 10px 24px; font-weight: bold; }
    .stButton>button:hover { background-color: #004494; color: white; }
    .dataframe { font-size: 14px !important; border: 1px solid #ddd !important; }
    div[data-testid="metric-container"] { background-color: #f8f9fa; border: 1px solid #e9ecef; padding: 15px; border-radius: 8px; color: #333; }
    .stProgress > div > div > div > div { background-color: #28a745; }
    </style>
    """, unsafe_allow_html=True)

# --- 🧮 佣金计算引擎 (季度修正版) ---
def calculate_commission_tier(current_cum_gp, monthly_base_salary):
    """
    根据【当前的累计GP】判断等级。
    基准：季度底薪 = 月薪 * 3
    """
    quarterly_base = monthly_base_salary * 3
    
    # 逻辑：必须先达到 3倍底薪 才有资格
    if current_cum_gp < 3 * quarterly_base:
        return 0, 0
    elif current_cum_gp < 4.5 * quarterly_base:
        return 1, 1
    elif current_cum_gp < 7.5 * quarterly_base:
        return 2, 2
    else:
        return 3, 3

def calculate_single_deal_commission(candidate_salary, multiplier):
    if multiplier == 0: return 0
    base_comm = 0
    if candidate_salary < 20000: base_comm = 1000
    elif candidate_salary < 30000: base_comm = candidate_salary * 0.05
    elif candidate_salary < 50000: base_comm = candidate_salary * 1.5 * 0.05
    else: base_comm = candidate_salary * 2.0 * 0.05
    return base_comm * multiplier

def normalize_text(text):
    return ''.join(c for c in unicodedata.normalize('NFD', str(text)) if unicodedata.category(c) != 'Mn').lower()

# --- 🔗 连接 ---
def connect_to_google():
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    if "gcp_service_account" in st.secrets:
        try:
            creds_dict = dict(st.secrets["gcp_service_account"])
            creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
            return gspread.authorize(creds)
        except Exception: return None
    else:
        current_dir = os.path.dirname(os.path.abspath(__file__))
        json_path = os.path.join(current_dir, 'credentials.json')
        if os.path.exists(json_path):
            try:
                creds = ServiceAccountCredentials.from_json_keyfile_name(json_path, scope)
                return gspread.authorize(creds)
            except Exception: return None
        else: return None

# --- 📥 招聘数据 ---
def fetch_recruitment_stats(client, months):
    all_stats = []
    all_details = []
    for month in months:
        for consultant in TEAM_CONFIG:
            s, i, o, d = internal_fetch_sheet_data(
