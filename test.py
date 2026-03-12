import time
import random
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from google.oauth2.service_account import Credentials

# -------------------------- 基础配置 --------------------------
# 替换为你的服务账号密钥路径
SERVICE_ACCOUNT_FILE = 'your_service_account_key.json'
# Google Sheets 文档ID
SPREADSHEET_ID = 'your_spreadsheet_id'
# 每次请求的基础延迟（秒），可根据限流情况调整
BASE_DELAY = 1.5
# 最大重试次数
MAX_RETRIES = 5

# -------------------------- 认证函数 --------------------------
def get_sheets_service():
    """获取Google Sheets服务实例"""
    creds = Credentials.from_service_account_file(
        SERVICE_ACCOUNT_FILE,
        scopes=['https://www.googleapis.com/auth/spreadsheets.readonly']
    )
    return build('sheets', 'v4', credentials=creds)

# -------------------------- 带重试的请求函数 --------------------------
def safe_sheets_request(request_func, *args, **kwargs):
    """
    带限流处理和重试的 Sheets 请求包装函数
    :param request_func: 实际的请求函数（如 service.spreadsheets().values().get）
    :return: 请求结果，失败则返回None
    """
    retries = 0
    while retries < MAX_RETRIES:
        try:
            # 执行请求前先延迟，避免触发限流
            time.sleep(BASE_DELAY + random.uniform(0, 0.5))
            # 执行请求
            response = request_func(*args, **kwargs).execute()
            return response
        except HttpError as error:
            # 处理429限流错误
            if error.resp.status == 429:
                retries += 1
                # 指数退避：重试间隔 = 2^重试次数 + 随机值，避免集中重试
                backoff_time = (2 ** retries) + random.uniform(0, 1)
                print(f"⚠️  请求限流，{backoff_time:.1f}秒后重试（第{retries}/{MAX_RETRIES}次）")
                time.sleep(backoff_time)
            # 处理404（工作表真的不存在）
            elif error.resp.status == 404:
                print(f"❌  资源不存在：{error.error_details[0]['message']}")
                return None
            # 其他错误
            else:
                print(f"❌  请求错误 [{error.resp.status}]：{error.error_details[0]['message']}")
                return None
        except Exception as e:
            print(f"❌  未知错误：{str(e)}")
            return None
    print(f"❌  达到最大重试次数（{MAX_RETRIES}次），请求失败")
    return None

# -------------------------- 业务逻辑函数 --------------------------
def get_worksheet_data(sheet_name):
    """
    获取指定工作表的全部数据
    :param sheet_name: 工作表名称（如"202512"）
    :return: 工作表数据（列表），失败则返回空列表
    """
    print(f"🔍 正在获取工作表「{sheet_name}」数据...")
    service = get_sheets_service()
    
    # 批量读取整个工作表（减少请求次数）
    range_name = f"{sheet_name}!A:Z"
    request = service.spreadsheets().values().get(
        spreadsheetId=SPREADSHEET_ID,
        range=range_name
    )
    
    response = safe_sheets_request(request)
    if response and 'values' in response:
        print(f"✅ 成功获取「{sheet_name}」数据，共{len(response['values'])}行")
        return response['values']
    else:
        print(f"❌ 获取「{sheet_name}」数据失败（工作表不存在或无数据）")
        return []

def get_commission_data(sheet_name, employee_name):
    """
    获取指定员工的月度佣金数据
    :param sheet_name: 工作表名称
    :param employee_name: 员工姓名（如"Ana Cruz"）
    :return: 员工佣金数据（字典），失败则返回空字典
    """
    print(f"\n🔍 正在获取「{employee_name}」的{sheet_name}月度佣金数据...")
    # 先获取整个工作表数据（批量读取，减少请求）
    sheet_data = get_worksheet_data(sheet_name)
    if not sheet_data:
        return {}
    
    # 解析员工数据（假设第一列是姓名，第二列是佣金）
    commission_data = {}
    # 跳过表头（如果有）
    header = sheet_data[0]
    for row in sheet_data[1:]:
        if len(row) >= 2 and row[0] == employee_name:
            commission_data = {
                'name': row[0],
                'commission': row[1],
                'month': sheet_name
            }
            break
    
    if commission_data:
        print(f"✅ 成功获取「{employee_name}」佣金数据：{commission_data}")
    else:
        print(f"❌ 未找到「{employee_name}」的佣金数据")
    return commission_data

# -------------------------- 主函数 --------------------------
if __name__ == '__main__':
    # 要查询的工作表和员工列表
    target_sheet = "202512"
    employees = ["Ana Cruz", "Karina Albarran"]
    
    # 批量获取所有员工的佣金数据
    all_commission_data = {}
    for emp in employees:
        emp_data = get_commission_data(target_sheet, emp)
        all_commission_data[emp] = emp_data
        # 额外延迟，进一步降低请求频率
        time.sleep(0.5)
    
    # 输出最终结果
    print("\n📊 最终查询结果：")
    for emp, data in all_commission_data.items():
        print(f"- {emp}: {data if data else '无数据'}")
