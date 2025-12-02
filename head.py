# --- FETCH SALES DATA (Section Scanning Logic) ---
def fetch_sales_data(client, quarter_start_month, quarter_end_month, year):
    """
    在同一个Tab中扫描查找 'PLACED POSITIONS' 区域并读取数据
    """
    try:
        sheet = client.open_by_key(SALES_SHEET_ID)
        
        # 尝试打开配置的标签页，如果打不开默认试第1页
        try:
            ws = sheet.worksheet(SALES_TAB_NAME)
        except:
            ws = sheet.get_worksheet(0)
            
        rows = ws.get_all_values()
        
        # --- 状态机标志 ---
        found_section_title = False # 是否找到了 "PLACED POSITIONS" 大标题
        found_header = False        # 是否找到了表头 (Consultant, Salary...)
        
        # 列索引
        col_cons = -1; col_date = -1; col_sal = -1
        
        sales_records = []
        
        for row in rows:
            # 转为纯文本并大写，方便匹配
            row_text = [str(x).strip() for x in row]
            first_cell = row_text[0].upper()
            
            # 1. 寻找区域入口
            # 只要第一列包含 PLACED 和 POSITION 就认为是入口
            if "PLACED" in first_cell and "POSITION" in first_cell:
                found_section_title = True
                found_header = False # 重置表头状态，准备找新表头
                continue # 跳过标题行
            
            # 如果还没找到标题，就继续往下扫
            if not found_section_title:
                continue
                
            # 2. 在区域内寻找表头
            if found_section_title and not found_header:
                # 检查这一行是不是表头（特征：包含 Consultant 和 Salary）
                row_lower = [x.lower() for x in row_text]
                
                # 模糊匹配表头列
                temp_cons = -1; temp_date = -1; temp_sal = -1
                for idx, cell in enumerate(row_lower):
                    if "linkeazi" in cell or "consultant" in cell or "顾问" in cell: temp_cons = idx
                    if "date" in cell or "payment" in cell or "付款" in cell: temp_date = idx
                    if "salary" in cell or "薪资" in cell or "base" in cell: temp_sal = idx
                
                # 如果关键列都找到了，说明这一行是表头
                if temp_cons != -1 and temp_sal != -1:
                    col_cons = temp_cons
                    col_date = temp_date
                    col_sal = temp_sal
                    found_header = True
                continue # 跳过表头行本身

            # 3. 读取数据 (只有在找到标题且找到表头后)
            if found_header:
                # 如果遇到空行或新的大标题（比如遇到 CANCELLED POSITIONS），停止读取
                if "POSITION" in first_cell and "PLACED" not in first_cell:
                    break 
                
                # 确保行长度够
                if len(row) <= max(col_cons, col_date, col_sal): continue
                
                # --- 下面是原来的解析逻辑 ---
                date_str = row[col_date].strip()
                try:
                    pay_date = None
                    # 解析日期
                    for fmt in ["%Y-%m-%d", "%d/%m/%Y", "%Y/%m/%d", "%m/%d/%Y", "%Y.%m.%d", "%d-%b-%y"]:
                        try:
                            pay_date = datetime.strptime(date_str, fmt)
                            break
                        except: pass
                    
                    if not pay_date: continue
                    
                    # 过滤季度
                    if pay_date.year == year and quarter_start_month <= pay_date.month <= quarter_end_month:
                        
                        # 解析薪资
                        salary_raw = str(row[col_sal]).replace(',', '').replace('$', '').replace('MXN', '').strip()
                        salary = float(salary_raw) if salary_raw else 0
                        
                        # GP 计算 ( <20k *1.0, >=20k *1.5)
                        if salary < 20000:
                            calculated_gp = salary * 1.0
                        else:
                            calculated_gp = salary * 1.5
                        
                        consultant_name = row[col_cons].strip()
                        
                        # 匹配名字
                        matched_name = "Unknown"
                        for conf in TEAM_CONFIG:
                            if conf['name'].lower() in consultant_name.lower():
                                matched_name = conf['name']
                                break
                        
                        if matched_name != "Unknown":
                            sales_records.append({
                                "Consultant": matched_name,
                                "GP": calculated_gp,
                                "Candidate Salary": salary,
                                "Date": pay_date.strftime("%Y-%m-%d")
                            })
                except Exception:
                    continue

        return pd.DataFrame(sales_records)

    except Exception as e:
        st.error(f"Sales Data Error: {e}")
        return pd.DataFrame()
