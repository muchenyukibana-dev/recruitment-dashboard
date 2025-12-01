import streamlit as st
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import pandas as pd
import os
import time
from datetime import datetime, timedelta

# ==========================================
# 🔧 TEAM CONFIGURATION
# ==========================================
TEAM_CONFIG = [
    {
        "name": "Raul Solis",
        "id": "1vQuN-iNBRUug5J6gBMX-52jp6oogbA77SaeAf9j_zYs",
        "keyword": "Name"
    },
    {
        "name": "Estela Peng",
        "id": "1sUkffAXzWnpzhhmklqBuwtoQylpR1U18zqBQ-lsp7Z4",
        "keyword": "姓名" 
    },
    {
        "name": "Ana Cruz",
        "id": "1VMVw5YCV12eI8I-VQSXEKg86J2IVZJEgjPJT7ggAFD0",
        "keyword": "Name"
    },
    {
        "name": "Karina Albarran",
        "id": "1zc4ghvfjIxH0eJ2aXfopOWHqiyTDlD8yFNjBzpH07D8",
        "keyword": "Name"
    },
]

# ==========================================

st.set_page_config(page_title="Management Dashboard", page_icon="📊", layout="wide")

# --- 🎨 CSS STYLING (Professional Dashboard) ---
st.markdown("""
    <style>
    /* Global Settings */
    .stApp {
        background-color: #0E1117; /* Dark Professional Background */
        color: #FFFFFF;
    }
    
    /* Titles */
    h1 {
        text-align: center;
        col
