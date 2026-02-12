# 仅当非 Intern 时才进入逻辑
if not is_intern:
    if not c_sales.empty:
        # 1. 预处理：只看已付款的单子，并转换日期
        paid_sales = c_sales[c_sales['Status'] == 'Paid'].copy()
        if not paid_sales.empty:
            paid_sales['Payment Date Obj'] = pd.to_datetime(paid_sales['Payment Date Obj'])
            
            # 初始化结果列
            paid_sales['Applied Level'] = 0
            paid_sales['Final Comm'] = 0.0
            paid_sales['Commission Day Obj'] = pd.NaT

            # 2. 按季度分开处理，确保每个季度的累积 GP 独立计算
            for q_name in [PREV_Q_STR, CURRENT_Q_STR]:
                # 筛选属于该季度的已付单子
                q_mask = paid_sales['Quarter'] == q_name
                if not q_mask.any():
                    continue
                
                # 取出该季度的单子并按付款时间排序（决定谁先计入 Level）
                q_data = paid_sales[q_mask].copy().sort_values(by='Payment Date Obj')
                
                running_paid_gp = 0
                target_is_met = is_target_met_curr if q_name == CURRENT_Q_STR else is_target_met_hist
                
                # 3. 逐单计算佣金 (不回溯，不补差价)
                for idx, row in q_data.iterrows():
                    # 累加当前季度的 GP
                    running_paid_gp += row['GP']
                    
                    # 根据当前累加的 GP 确定这一笔单子所属的 Level
                    # 假设 calculate_commission_tier 返回该 GP 阶段对应的 level 和 multiplier
                    level, multiplier = calculate_commission_tier(running_paid_gp, base, is_team_lead)
                    
                    # 只有达标了才计算实际可发放金额
                    if target_is_met and level > 0:
                        # 计算单笔佣金
                        deal_comm = calculate_single_deal_commission(row['Candidate Salary'], multiplier) * row['Percentage']
                        
                        # 确定发薪日期 (根据付款月份计算)
                        pay_month_key = row['Payment Date Obj'].to_period('M')
                        payout_date = get_payout_date_from_month_key(str(pay_month_key))
                        
                        # 写入数据
                        q_data.at[idx, 'Applied Level'] = level
                        q_data.at[idx, 'Commission Day Obj'] = payout_date
                        q_data.at[idx, 'Final Comm'] = deal_comm
                    else:
                        # 未达标或未到 Level 1
                        q_data.at[idx, 'Final Comm'] = 0
                        q_data.at[idx, 'Applied Level'] = level

                # 把计算好的季度数据更新回总表
                paid_sales.update(q_data)

            # 4. 汇总可发放佣金 (只累加日期已到或近期将到的)
            for idx, row in paid_sales.iterrows():
                comm_date = row['Commission Day Obj']
                # 判定发放时间节点（当前日期 + 20天预支判断）
                if pd.notnull(comm_date) and comm_date <= datetime.now() + timedelta(days=20):
                    if row['Quarter'] == CURRENT_Q_STR:
                        total_comm_curr += row['Final Comm']
                    else:
                        total_comm_hist += row['Final Comm']

            # 更新原始 DataFrame
            c_sales.update(paid_sales)
            c_sales['Commission Day'] = c_sales['Commission Day Obj'].apply(
                lambda x: x.strftime("%Y-%m-%d") if pd.notnull(x) else "")

        updated_sales_records.append(c_sales)
