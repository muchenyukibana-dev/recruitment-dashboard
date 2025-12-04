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
    {"name": "Raul Solis", "id": "...", "keyword": "Name", "base_salary": 11000},
    {"name": "Estela Peng", "id": "...", "keyword": "姓名", "base_salary": 20800},
    {"name": "Ana Cruz", "id": "...", "keyword": "Name", "base_salary": 13000},
    {"name": "Karina Albarran", "id": "...", "keyword": "Name", "base_salary": 15000},
]

st.set_page_config(page_title="Debug Dashboard", page_icon="🐞", layout="wide")

# --- 样式 (保持简单) ---
st.markdown("""<style>.stApp { background-color: #FFFFFF; color: #000; }</style>""", unsafe_allow_html=True)

# --- 辅助函数 ---
def normalize_text(text):
    return ''.join(c for c in unicodedata.normalize('NFD', str(text)) if unicodedata.category(c) != 'Mn').lower()

def connect_to_google():
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    if "gcp_service_account" in st.secrets:
        creds = ServiceAccountCredentials.from_json_keyfile_dict(dict(st.secrets["gcp_service_account"]), scope)
    else:
        creds = ServiceAccountCredentials.from_json_keyfile_name(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'credentials.json'), scope)
    return gspread.authorize(creds)

# --- 🎯 核心诊断函数 ---
def fetch_sales_data_debug(client, year=2025):
    st.info(f"🔬 显微镜模式启动: 正在检查数据读取细节...")
    
    try:
        sheet = client.open_by_key(SALES_SHEET_ID)
        try: ws = sheet.worksheet(SALES_TAB_NAME)
        except: ws = sheet.get_worksheet(0)
        rows = ws.get_all_values()
        
        found_header = False
        start_row_index = 0
        
        # 1. 定位表头 (使用之前的成功逻辑)
        col_cons = -1; col_onb = -1; col_sal = -1
        
        for i, row in enumerate(rows):
            row_lower = [str(x).strip().lower() for x in row]
            
            # 同时包含 Linkeazi Consultant 和 Onboarding
            has_cons = any("linkeazi" in cell and "consultant" in cell for cell in row_lower)
            has_onb = any("onboarding" in cell for cell in row_lower)
            
            if has_cons and has_onb:
                for idx, cell in enumerate(row_lower):
                    if "linkeazi" in cell and "consultant" in cell: col_cons = idx
                    if "onboarding" in cell and "date" in cell: col_onb = idx
                    if "candidate" in cell and "salary" in cell: col_sal = idx
                
                found_header = True
                start_row_index = i + 1 # 数据从下一行开始
                st.success(f"""
                ✅ **表头定位成功 (第 {i+1} 行)**
                - 顾问列 (Column {col_cons+1}): `{row[col_cons]}`
                - 入职列 (Column {col_onb+1}): `{row[col_onb]}`
                - 薪资列 (Column {col_sal+1}): `{row[col_sal]}`
                """)
                break
        
        if not found_header:
            st.error("❌ 依然无法定位表头。请确认表头包含 'Linkeazi Consultant' 和 'Onboarding Date'。")
            return

        # 2. 逐行诊断前 5 条数据
        st.markdown("### 🕵️‍♂️ 数据行详细体检 (前 5 行)")
        
        debug_count = 0
        for i in range(start_row_index, len(rows)):
            if debug_count >= 5: break # 只看前5行
            
            row = rows[i]
            # 跳过空行
            if not any(cell.strip() for cell in row): continue
            
            # 遇到结束标记停止
            if "POSITION" in str(row[0]).upper() and "PLACED" not in str(row[0]).upper():
                st.info("遇到结束标记，停止检测。")
                break

            debug_count += 1
            
            # 获取原始数据
            raw_cons = row[col_cons] if len(row) > col_cons else "越界"
            raw_date = row[col_onb] if len(row) > col_onb else "越界"
            raw_sal = row[col_sal] if len(row) > col_sal else "越界"
            
            with st.expander(f"第 {i+1} 行: {raw_cons} (点击展开查看详情)", expanded=True):
                st.text(f"原始数据 -> 顾问: '{raw_cons}' | 日期: '{raw_date}' | 薪资: '{raw_sal}'")
                
                # --- 诊断 1: 日期解析 ---
                parsed_date = None
                date_formats = ["%Y-%m-%d", "%d/%m/%Y", "%Y/%m/%d", "%m/%d/%Y", "%d-%b-%y", "%Y.%m.%d"]
                for fmt in date_formats:
                    try:
                        parsed_date = datetime.strptime(raw_date.strip(), fmt)
                        break
                    except: pass
                
                if parsed_date:
                    st.write(f"✅ 日期解析成功: {parsed_date.strftime('%Y-%m-%d')}")
                    # 检查是否 Q3
                    if parsed_date.year == 2025 and 7 <= parsed_date.month <= 9:
                        st.write("✅ 时间符合: 属于 2025年 Q3")
                    else:
                        st.write(f"❌ 时间不符: 它是 {parsed_date.year}年 {parsed_date.month}月，不是 Q3")
                else:
                    st.error(f"❌ 日期解析失败: 无法识别格式 '{raw_date}'")

                # --- 诊断 2: 名字匹配 ---
                matched = "Unknown"
                c_norm = normalize_text(raw_cons)
                
                for conf in TEAM_CONFIG:
                    conf_norm = normalize_text(conf['name'])
                    if conf_norm in c_norm or c_norm in conf_norm:
                        matched = conf['name']
                        break
                    # 尝试 First Name 匹配 (比如 'Raul' 匹配 'Raul Solis')
                    if conf_norm.split()[0] in c_norm:
                        matched = conf['name']
                        break
                
                if matched != "Unknown":
                    st.write(f"✅ 名字匹配成功: 对应配置中的 '{matched}'")
                else:
                    st.error(f"❌ 名字匹配失败: 系统里没有叫 '{raw_cons}' 的人 (请检查 TEAM_CONFIG)")

    except Exception as e:
        st.error(f"运行出错: {e}")

# --- 主程序 ---
def main():
    st.title("🐞 Debugger Mode")
    if st.button("🚀 开始诊断 (LOAD Q3)"):
        client = connect_to_google()
        if client:
            fetch_sales_data_debug(client)

if __name__ == "__main__":
    main()
