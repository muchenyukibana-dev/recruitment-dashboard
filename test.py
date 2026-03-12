import time
import random
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from google.oauth2.service_account import Credentials

# -------------------------- 基础配置（请根据你的实际情况修改） --------------------------
# 替换为你的Google服务账号密钥文件路径（JSON文件）
SERVICE_ACCOUNT_FILE = 'your_service_account_key.json'
# 替换为你的Google Sheets文档ID（在表格URL中可以找到）
SPREADSHEET_ID = 'your_spreadsheet_id'
# 每次请求的基础延迟时间（秒），可根据限流情况调整，建议1.5-3秒
BASE_DELAY = 1.5
# 最大重试次数（遇到429限流时自动重试）
MAX_RETRIES = 5

# -------------------------- 认证函数 --------------------------
def get_sheets_service():
    """获取Google Sheets API服务实例（带认证）"""
    try:
        creds = Credentials.from_service_account_file(
            SERVICE_ACCOUNT_FILE,
            scopes=['https://www.googleapis.com/auth/spreadsheets.readonly']
        )
        service = build('sheets', 'v4', credentials=creds)
        return service
    except Exception as e:
        print(f"❌ 认证失败：{str(e)}")
        return None

# -------------------------- 带限流和重试的请求包装函数 --------------------------
def safe_sheets_request(request_func, *args, **kwargs):
    """
    安全执行Sheets API请求，自动处理429限流错误并重试
    :param request_func: 待执行的API请求函数（如service.spreadsheets().values().get）
    :return: API响应结果（dict），失败则返回None
    """
    retries = 0
    while retries < MAX_RETRIES:
        try:
            # 请求前先延迟，避免触发限流
            time.sleep(BASE_DELAY + random.uniform(0, 0.5))
            
            # 执行实际请求
            response = request_func(*args, **kwargs).execute()
            return response
        
        except HttpError as error:
            error_code = error.resp.status
            error_msg = error.error_details[0]['message'] if error.error_details else str(error)
            
            # 处理429限流错误（核心修复点）
            if error_code == 429:
                retries += 1
                # 指数退避算法：重试间隔随次数递增，避免集中重试
                backoff_time = (2 ** retries) + random.uniform(0, 1)
                print(f"⚠️  请求频率超限（429），{backoff_time:.1f}秒后重试（第{retries}/{MAX_RETRIES}次）")
                time.sleep(backoff_time)
            
            # 处理404错误（工作表/范围真的不存在）
            elif error_code == 404:
                print(f"❌ 资源不存在：{error_msg}")
                return None
            
            # 其他HTTP错误
            else:
                print(f"❌ API请求错误 [{error_code}]：{error_msg}")
                return None
        
        # 处理其他异常（如网络问题）
        except Exception as e:
            print(f"❌ 未知错误：{str(e)}")
            return None
    
    # 达到最大重试次数仍失败
    print(f"❌ 达到最大重试次数（{MAX_RETRIES}次），请求失败")
    return None

# -------------------------- 业务逻辑：获取工作表数据 --------------------------
def get_worksheet_data(sheet_name):
    """
    获取指定名称工作表的全部数据
    :param sheet_name: 工作表名称（如"202512"）
    :return: 工作表数据列表（每行是一个子列表），失败返回空列表
    """
    print(f"\n🔍 正在读取工作表「{sheet_name}」...")
    
    # 获取API服务实例
    service = get_sheets_service()
    if not service:
        return []
    
    # 批量读取整个工作表（A列到Z列），减少请求次数
    range_name = f"{sheet_name}!A:Z"
    request = service.spreadsheets().values().get(
        spreadsheetId=SPREADSHEET_ID,
        range=range_name
    )
    
    # 执行安全请求
    response = safe_sheets_request(request)
    
    # 解析响应数据
    if response and 'values' in response:
        data = response['values']
        print(f"✅ 成功读取「{sheet_name}」，共{len(data)}行数据")
        return data
    else:
        print(f"❌ 读取「{sheet_name}」失败（工作表不存在或无数据）")
        return []

# -------------------------- 业务逻辑：获取指定员工佣金数据 --------------------------
def get_employee_commission(sheet_name, employee_name):
    """
    获取指定员工的月度佣金数据
    :param sheet_name: 工作表名称（如"202512"）
    :param employee_name: 员工姓名（如"Ana Cruz"）
    :return: 佣金数据字典，失败返回空字典
    """
    print(f"\n📈 正在查询「{employee_name}」的{sheet_name}月度佣金...")
    
    # 先获取整个工作表数据（批量读取，减少请求）
    sheet_data = get_worksheet_data(sheet_name)
    if not sheet_data:
        return {}
    
    # 解析员工数据（假设：第1列=姓名，第2列=佣金金额，可根据你的表格调整）
    commission_info = {}
    # 跳过表头行（如果表格有表头）
    header = sheet_data[0]
    for row_num, row in enumerate(sheet_data[1:], start=2):  # 行号从2开始（跳过表头）
        if len(row) >= 2 and row[0].strip() == employee_name:
            commission_info = {
                '员工姓名': row[0].strip(),
                '月度佣金': row[1].strip(),
                '所属月份': sheet_name,
                '数据行号': row_num
            }
            break
    
    # 输出结果
    if commission_info:
        print(f"✅ 找到「{employee_name}」的佣金数据：{commission_info}")
    else:
        print(f"❌ 未找到「{employee_name}」的佣金数据")
    
    return commission_info

# -------------------------- 主程序入口 --------------------------
if __name__ == '__main__':
    # 配置你要查询的参数
    target_month_sheet = "202512"  # 要查询的工作表名称
    target_employees = [           # 要查询的员工列表
        "Ana Cruz",
        "Karina Albarran"
    ]
    
    # 批量查询所有员工的佣金数据
    all_results = {}
    for emp_name in target_employees:
        emp_data = get_employee_commission(target_month_sheet, emp_name)
        all_results[emp_name] = emp_data
        # 额外延迟，进一步降低请求频率
        time.sleep(0.5)
    
    # 输出最终汇总结果
    print("\n" + "="*50)
    print("📊 佣金数据查询汇总")
    print("="*50)
    for emp, data in all_results.items():
        if data:
            print(f"\n{emp}:")
            for key, value in data.items():
                print(f"  - {key}: {value}")
        else:
            print(f"\n{emp}: 无有效数据")
