#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Google Sheets 佣金数据查询系统
功能：批量查询员工月度佣金数据，处理API限流，支持缓存、日志、重试、配置管理
解决核心问题：APIError: [429] Quota exceeded（请求频率超限）
"""

import os
import sys
import time
import json
import random
import logging
import configparser
import threading
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple, Any
from pathlib import Path

# 第三方库导入
try:
    from googleapiclient.discovery import build
    from googleapiclient.errors import HttpError
    from google.oauth2.service_account import Credentials
    from google.api_core import retry as google_retry
except ImportError as e:
    print(f"缺少依赖库，请执行安装：pip install google-api-python-client google-auth google-api-core")
    sys.exit(1)

# -----------------------------------------------------------------------------
# 1. 全局配置与常量定义 (约100行)
# -----------------------------------------------------------------------------
# 项目根目录
PROJECT_ROOT = Path(__file__).parent.absolute()

# 配置文件路径
CONFIG_FILE = PROJECT_ROOT / "config.ini"
# 服务账号密钥路径（可在config.ini中配置）
DEFAULT_SERVICE_ACCOUNT_FILE = PROJECT_ROOT / "credentials.json"
# 缓存目录
CACHE_DIR = PROJECT_ROOT / "cache"
# 日志目录
LOG_DIR = PROJECT_ROOT / "logs"
# 确保目录存在
for dir_path in [CACHE_DIR, LOG_DIR]:
    dir_path.mkdir(exist_ok=True)

# API限流相关常量
BASE_DELAY = 1.5  # 基础请求延迟（秒）
MAX_RETRIES = 8   # 最大重试次数
MAX_CONCURRENT_THREADS = 3  # 最大并发线程数
QUOTA_REFRESH_INTERVAL = 60  # 配额刷新间隔（分钟）

# 表格数据列映射（可在config.ini中配置）
COLUMN_MAPPING = {
    "name": 0,      # 员工姓名列
    "commission": 1,# 佣金金额列
    "department": 2,# 部门列
    "date": 3,      # 日期列
    "status": 4     # 状态列
}

# -----------------------------------------------------------------------------
# 2. 日志系统配置 (约80行)
# -----------------------------------------------------------------------------
def setup_logger() -> logging.Logger:
    """配置日志系统，同时输出到控制台和文件"""
    logger = logging.getLogger("SheetsCommissionSystem")
    logger.setLevel(logging.DEBUG)
    
    # 避免重复添加处理器
    if logger.handlers:
        return logger
    
    # 日志格式
    formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(threadName)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    
    # 控制台处理器
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(formatter)
    
    # 文件处理器（按日期滚动）
    log_file = LOG_DIR / f"commission_system_{datetime.now().strftime('%Y%m%d')}.log"
    file_handler = logging.FileHandler(log_file, encoding='utf-8')
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(formatter)
    
    # 添加处理器
    logger.addHandler(console_handler)
    logger.addHandler(file_handler)
    
    return logger

# 初始化日志器
logger = setup_logger()

# -----------------------------------------------------------------------------
# 3. 配置文件管理 (约120行)
# -----------------------------------------------------------------------------
class ConfigManager:
    """配置文件管理类，支持从ini文件读取配置"""
    
    def __init__(self, config_path: Path = CONFIG_FILE):
        self.config_path = config_path
        self.config = configparser.ConfigParser()
        self._load_config()
        self._validate_config()
    
    def _load_config(self) -> None:
        """加载配置文件，不存在则创建默认配置"""
        if self.config_path.exists():
            self.config.read(self.config_path, encoding='utf-8')
            logger.info(f"成功加载配置文件: {self.config_path}")
        else:
            logger.warning(f"配置文件不存在，创建默认配置: {self.config_path}")
            self._create_default_config()
    
    def _create_default_config(self) -> None:
        """创建默认配置文件"""
        # API配置
        self.config['API'] = {
            'spreadsheet_id': 'your_spreadsheet_id_here',
            'service_account_file': str(DEFAULT_SERVICE_ACCOUNT_FILE),
            'base_delay': str(BASE_DELAY),
            'max_retries': str(MAX_RETRIES),
            'max_concurrent_threads': str(MAX_CONCURRENT_THREADS),
            'quota_refresh_interval': str(QUOTA_REFRESH_INTERVAL)
        }
        
        # 数据配置
        self.config['DATA'] = {
            'column_name': str(COLUMN_MAPPING['name']),
            'column_commission': str(COLUMN_MAPPING['commission']),
            'column_department': str(COLUMN_MAPPING['department']),
            'column_date': str(COLUMN_MAPPING['date']),
            'column_status': str(COLUMN_MAPPING['status']),
            'default_sheet_prefix': '2025',
            'cache_ttl': '3600'  # 缓存有效期（秒）
        }
        
        # 保存配置文件
        with open(self.config_path, 'w', encoding='utf-8') as f:
            self.config.write(f)
    
    def _validate_config(self) -> None:
        """验证配置的有效性"""
        required_sections = ['API', 'DATA']
        for section in required_sections:
            if section not in self.config:
                logger.error(f"配置文件缺少必要章节: {section}")
                sys.exit(1)
        
        # 验证API配置
        api_keys = ['spreadsheet_id', 'service_account_file']
        for key in api_keys:
            if not self.config['API'].get(key):
                logger.error(f"API配置缺少必要项: {key}")
                sys.exit(1)
        
        # 验证文件路径
        sa_file = Path(self.config['API']['service_account_file'])
        if not sa_file.exists() and sa_file != DEFAULT_SERVICE_ACCOUNT_FILE:
            logger.warning(f"服务账号密钥文件不存在: {sa_file}")
    
    def get_api_config(self) -> Dict[str, Any]:
        """获取API相关配置"""
        return {
            'spreadsheet_id': self.config['API']['spreadsheet_id'],
            'service_account_file': Path(self.config['API']['service_account_file']),
            'base_delay': float(self.config['API'].get('base_delay', BASE_DELAY)),
            'max_retries': int(self.config['API'].get('max_retries', MAX_RETRIES)),
            'max_concurrent_threads': int(self.config['API'].get('max_concurrent_threads', MAX_CONCURRENT_THREADS)),
            'quota_refresh_interval': int(self.config['API'].get('quota_refresh_interval', QUOTA_REFRESH_INTERVAL))
        }
    
    def get_data_config(self) -> Dict[str, Any]:
        """获取数据相关配置"""
        return {
            'column_mapping': {
                'name': int(self.config['DATA']['column_name']),
                'commission': int(self.config['DATA']['column_commission']),
                'department': int(self.config['DATA']['column_department']),
                'date': int(self.config['DATA']['column_date']),
                'status': int(self.config['DATA']['column_status'])
            },
            'default_sheet_prefix': self.config['DATA']['default_sheet_prefix'],
            'cache_ttl': int(self.config['DATA']['cache_ttl'])
        }
    
    def update_config(self, section: str, key: str, value: Any) -> None:
        """更新配置并保存"""
        if section not in self.config:
            self.config[section] = {}
        self.config[section][key] = str(value)
        with open(self.config_path, 'w', encoding='utf-8') as f:
            self.config.write(f)
        logger.info(f"更新配置: {section}.{key} = {value}")

# -----------------------------------------------------------------------------
# 4. 缓存管理系统 (约100行)
# -----------------------------------------------------------------------------
class CacheManager:
    """缓存管理器，用于减少重复的API请求"""
    
    def __init__(self, cache_dir: Path = CACHE_DIR, ttl: int = 3600):
        self.cache_dir = cache_dir
        self.ttl = ttl
        self.lock = threading.Lock()
    
    def _get_cache_filename(self, key: str) -> Path:
        """生成缓存文件名"""
        safe_key = key.replace('/', '_').replace(':', '_').replace(' ', '_')
        return self.cache_dir / f"{safe_key}.json"
    
    def is_cache_valid(self, key: str) -> bool:
        """检查缓存是否有效"""
        cache_file = self._get_cache_filename(key)
        if not cache_file.exists():
            return False
        
        # 检查缓存时间
        file_mtime = datetime.fromtimestamp(cache_file.stat().st_mtime)
        now = datetime.now()
        if (now - file_mtime).total_seconds() > self.ttl:
            return False
        
        return True
    
    def get_cache(self, key: str) -> Optional[Any]:
        """获取缓存数据"""
        with self.lock:
            cache_file = self._get_cache_filename(key)
            if not self.is_cache_valid(key):
                return None
            
            try:
                with open(cache_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                logger.debug(f"成功加载缓存: {key}")
                return data
            except Exception as e:
                logger.error(f"读取缓存失败 {key}: {str(e)}")
                return None
    
    def set_cache(self, key: str, data: Any) -> None:
        """设置缓存数据"""
        with self.lock:
            cache_file = self._get_cache_filename(key)
            try:
                with open(cache_file, 'w', encoding='utf-8') as f:
                    json.dump({
                        'data': data,
                        'timestamp': datetime.now().isoformat()
                    }, f, ensure_ascii=False, indent=2)
                logger.debug(f"成功保存缓存: {key}")
            except Exception as e:
                logger.error(f"保存缓存失败 {key}: {str(e)}")
    
    def clear_cache(self, key: Optional[str] = None) -> None:
        """清除缓存，key为None时清除所有缓存"""
        with self.lock:
            if key:
                cache_file = self._get_cache_filename(key)
                if cache_file.exists():
                    cache_file.unlink()
                    logger.info(f"清除缓存: {key}")
            else:
                for cache_file in self.cache_dir.glob("*.json"):
                    cache_file.unlink()
                logger.info("清除所有缓存")

# -----------------------------------------------------------------------------
# 5. Google Sheets API 客户端 (约200行)
# -----------------------------------------------------------------------------
class SheetsAPIClient:
    """Google Sheets API客户端，处理认证、请求、限流"""
    
    def __init__(self, config: Dict[str, Any]):
        self.spreadsheet_id = config['spreadsheet_id']
        self.service_account_file = config['service_account_file']
        self.base_delay = config['base_delay']
        self.max_retries = config['max_retries']
        self.quota_refresh_interval = config['quota_refresh_interval']
        
        # 配额监控
        self.request_count = 0
        self.last_quota_reset = datetime.now()
        self.lock = threading.Lock()
        
        # 初始化服务
        self.service = self._authenticate()
    
    def _authenticate(self) -> Optional[Any]:
        """认证并创建Sheets服务实例"""
        try:
            if not self.service_account_file.exists():
                logger.error(f"服务账号密钥文件不存在: {self.service_account_file}")
                return None
            
            creds = Credentials.from_service_account_file(
                str(self.service_account_file),
                scopes=[
                    'https://www.googleapis.com/auth/spreadsheets.readonly',
                    'https://www.googleapis.com/auth/drive.readonly'
                ]
            )
            
            service = build('sheets', 'v4', credentials=creds, cache_discovery=False)
            logger.info("成功创建Google Sheets API服务实例")
            return service
        
        except Exception as e:
            logger.error(f"认证失败: {str(e)}")
            return None
    
    def _update_request_count(self) -> None:
        """更新请求计数，定期重置"""
        with self.lock:
            now = datetime.now()
            if (now - self.last_quota_reset).total_seconds() > self.quota_refresh_interval * 60:
                self.request_count = 0
                self.last_quota_reset = now
                logger.info(f"重置请求计数，配额周期已刷新")
            
            self.request_count += 1
            logger.debug(f"当前请求计数: {self.request_count}")
    
    def _exponential_backoff(self, retry_count: int) -> float:
        """指数退避算法，计算重试延迟"""
        # 基础延迟: 2^retry_count + 随机抖动
        backoff_time = (2 ** min(retry_count, 8)) + random.uniform(0, 1)
        # 添加基础延迟
        backoff_time += self.base_delay
        # 限制最大延迟为60秒
        return min(backoff_time, 60)
    
    @google_retry.Retry(
        predicate=google_retry.if_exception_type(HttpError),
        deadline=300,
        on_error=lambda retry_state: logger.warning(f"API请求重试 {retry_state}")
    )
    def _make_request(self, request_func, *args, **kwargs) -> Optional[Dict[str, Any]]:
        """执行API请求，处理限流和重试"""
        retry_count = 0
        
        while retry_count < self.max_retries:
            try:
                # 更新请求计数
                self._update_request_count()
                
                # 请求前延迟，避免触发限流
                delay = self.base_delay + random.uniform(0, 0.5)
                time.sleep(delay)
                
                # 执行请求
                response = request_func(*args, **kwargs).execute()
                logger.debug(f"API请求成功，延迟: {delay:.2f}秒")
                return response
            
            except HttpError as error:
                error_code = error.resp.status
                error_details = error.error_details[0] if error.error_details else {}
                error_message = error_details.get('message', str(error))
                
                # 处理429限流错误
                if error_code == 429:
                    retry_count += 1
                    backoff_time = self._exponential_backoff(retry_count)
                    
                    logger.warning(
                        f"API限流错误 (429) - 重试 {retry_count}/{self.max_retries}, "
                        f"延迟 {backoff_time:.2f}秒, 原因: {error_message}"
                    )
                    
                    # 等待后重试
                    time.sleep(backoff_time)
                    continue
                
                # 处理404错误（资源不存在）
                elif error_code == 404:
                    logger.error(f"资源不存在: {error_message}")
                    return None
                
                # 处理其他HTTP错误
                else:
                    logger.error(f"API请求失败 [{error_code}]: {error_message}")
                    return None
            
            except Exception as e:
                logger.error(f"请求执行异常: {str(e)}")
                retry_count += 1
                if retry_count < self.max_retries:
                    time.sleep(self._exponential_backoff(retry_count))
                    continue
                return None
        
        logger.error(f"达到最大重试次数 ({self.max_retries})，请求失败")
        return None
    
    def get_sheet_data(self, sheet_name: str, range_str: str = "A:ZZ") -> Optional[List[List[str]]]:
        """
        获取指定工作表的数据
        :param sheet_name: 工作表名称
        :param range_str: 数据范围，默认A:ZZ（全部数据）
        :return: 二维列表格式的数据
        """
        if not self.service:
            logger.error("API服务未初始化，无法获取数据")
            return None
        
        full_range = f"{sheet_name}!{range_str}"
        logger.info(f"开始获取数据: {full_range}")
        
        try:
            request = self.service.spreadsheets().values().get(
                spreadsheetId=self.spreadsheet_id,
                range=full_range,
                valueRenderOption='FORMATTED_VALUE'
            )
            
            response = self._make_request(request)
            
            if response and 'values' in response:
                data = response['values']
                logger.info(f"成功获取「{sheet_name}」数据，共{len(data)}行")
                return data
            else:
                logger.warning(f"「{sheet_name}」无数据或响应为空")
                return None
        
        except Exception as e:
            logger.error(f"获取工作表数据失败 {sheet_name}: {str(e)}")
            return None
    
    def list_sheets(self) -> Optional[List[str]]:
        """列出所有工作表名称"""
        if not self.service:
            logger.error("API服务未初始化，无法列出工作表")
            return None
        
        try:
            request = self.service.spreadsheets().get(spreadsheetId=self.spreadsheet_id)
            response = self._make_request(request)
            
            if not response:
                return None
            
            sheets = []
            for sheet in response.get('sheets', []):
                sheet_name = sheet.get('properties', {}).get('title', '')
                if sheet_name:
                    sheets.append(sheet_name)
            
            logger.info(f"找到{len(sheets)}个工作表: {sheets}")
            return sheets
        
        except Exception as e:
            logger.error(f"列出工作表失败: {str(e)}")
            return None

# -----------------------------------------------------------------------------
# 6. 佣金数据处理器 (约150行)
# -----------------------------------------------------------------------------
class CommissionDataProcessor:
    """佣金数据处理类，负责解析和查询员工佣金数据"""
    
    def __init__(self, sheets_client: SheetsAPIClient, cache_manager: CacheManager, data_config: Dict[str, Any]):
        self.sheets_client = sheets_client
        self.cache_manager = cache_manager
        self.column_mapping = data_config['column_mapping']
        self.default_sheet_prefix = data_config['default_sheet_prefix']
        self.cache_ttl = data_config['cache_ttl']
    
    def _get_sheet_cache_key(self, sheet_name: str) -> str:
        """生成工作表缓存键"""
        return f"sheet_data_{sheet_name}"
    
    def get_sheet_data_with_cache(self, sheet_name: str) -> Optional[List[List[str]]]:
        """获取工作表数据（优先使用缓存）"""
        # 生成缓存键
        cache_key = self._get_sheet_cache_key(sheet_name)
        
        # 尝试从缓存获取
        cached_data = self.cache_manager.get_cache(cache_key)
        if cached_data:
            return cached_data.get('data')
        
        # 缓存未命中，从API获取
        sheet_data = self.sheets_client.get_sheet_data(sheet_name)
        
        # 保存到缓存
        if sheet_data:
            self.cache_manager.set_cache(cache_key, sheet_data)
        
        return sheet_data
    
    def parse_employee_data(self, row: List[str], row_num: int) -> Dict[str, Any]:
        """解析单行员工数据"""
        parsed_data = {
            'row_number': row_num,
            'name': '',
            'commission': '',
            'department': '',
            'date': '',
            'status': '',
            'is_valid': False
        }
        
        try:
            # 按列映射解析数据
            for key, col_idx in self.column_mapping.items():
                if len(row) > col_idx:
                    parsed_data[key] = row[col_idx].strip()
            
            # 验证必要字段
            if parsed_data['name'] and parsed_data['commission']:
                parsed_data['is_valid'] = True
            
            return parsed_data
        
        except Exception as e:
            logger.error(f"解析行数据失败 (行{row_num}): {str(e)}")
            return parsed_data
    
    def get_employee_commission(self, sheet_name: str, employee_name: str) -> Dict[str, Any]:
        """
        获取指定员工的佣金数据
        :param sheet_name: 工作表名称
        :param employee_name: 员工姓名
        :return: 员工佣金数据字典
        """
        logger.info(f"查询员工「{employee_name}」在「{sheet_name}」的佣金数据")
        
        # 结果模板
        result = {
            'employee_name': employee_name,
            'sheet_name': sheet_name,
            'found': False,
            'data': {},
            'error': ''
        }
        
        try:
            # 获取工作表数据
            sheet_data = self.get_sheet_data_with_cache(sheet_name)
            if not sheet_data:
                result['error'] = f"工作表「{sheet_name}」数据为空或不存在"
                logger.warning(result['error'])
                return result
            
            # 遍历查找员工数据（跳过表头行）
            for row_num, row in enumerate(sheet_data, start=1):
                # 跳过空行
                if not row or len(row) == 0:
                    continue
                
                # 解析行数据
                parsed_row = self.parse_employee_data(row, row_num)
                
                # 匹配员工姓名
                if parsed_row['is_valid'] and parsed_row['name'] == employee_name:
                    result['found'] = True
                    result['data'] = parsed_row
                    logger.info(f"找到员工「{employee_name}」数据 (行{row_num})")
                    break
            
            if not result['found']:
                result['error'] = f"未找到员工「{employee_name}」的佣金数据"
                logger.warning(result['error'])
            
            return result
        
        except Exception as e:
            error_msg = f"查询员工佣金数据失败: {str(e)}"
            logger.error(error_msg)
            result['error'] = error_msg
            return result
    
    def batch_get_commission_data(self, sheet_name: str, employee_names: List[str]) -> Dict[str, Dict[str, Any]]:
        """
        批量获取多个员工的佣金数据
        :param sheet_name: 工作表名称
        :param employee_names: 员工姓名列表
        :return: 员工姓名到佣金数据的映射
        """
        logger.info(f"批量查询{len(employee_names)}名员工在「{sheet_name}」的佣金数据")
        
        results = {}
        sheet_data = self.get_sheet_data_with_cache(sheet_name)
        
        if not sheet_data:
            error_msg = f"工作表「{sheet_name}」数据为空或不存在"
            for emp_name in employee_names:
                results[emp_name] = {
                    'employee_name': emp_name,
                    'sheet_name': sheet_name,
                    'found': False,
                    'data': {},
                    'error': error_msg
                }
            return results
        
        # 构建员工姓名索引，提高查询效率
        employee_index = {name: None for name in employee_names}
        
        # 遍历所有行，一次性匹配所有员工
        for row_num, row in enumerate(sheet_data, start=1):
            if not row or len(row) == 0:
                continue
            
            parsed_row = self.parse_employee_data(row, row_num)
            if not parsed_row['is_valid']:
                continue
            
            emp_name = parsed_row['name']
            if emp_name in employee_index and employee_index[emp_name] is None:
                employee_index[emp_name] = parsed_row
        
        # 构建结果
        for emp_name in employee_names:
            parsed_data = employee_index[emp_name]
            if parsed_data:
                results[emp_name] = {
                    'employee_name': emp_name,
                    'sheet_name': sheet_name,
                    'found': True,
                    'data': parsed_data,
                    'error': ''
                }
            else:
                results[emp_name] = {
                    'employee_name': emp_name,
                    'sheet_name': sheet_name,
                    'found': False,
                    'data': {},
                    'error': f"未找到员工「{emp_name}」的佣金数据"
                }
        
        logger.info(f"批量查询完成，找到{sum(1 for r in results.values() if r['found'])}名员工的数据")
        return results

# -----------------------------------------------------------------------------
# 7. 多线程任务管理器 (约100行)
# -----------------------------------------------------------------------------
class ThreadedTaskManager:
    """多线程任务管理器，控制并发请求数量"""
    
    def __init__(self, max_concurrent: int = 3):
        self.max_concurrent = max_concurrent
        self.semaphore = threading.Semaphore(max_concurrent)
        self.results = {}
        self.lock = threading.Lock()
    
    def _task_wrapper(self, func, task_id: str, *args, **kwargs) -> None:
        """任务包装器，处理信号量和结果收集"""
        with self.semaphore:
            try:
                result = func(*args, **kwargs)
                with self.lock:
                    self.results[task_id] = {
                        'success': True,
                        'data': result,
                        'error': ''
                    }
            except Exception as e:
                error_msg = f"任务执行失败: {str(e)}"
                logger.error(f"任务 {task_id}: {error_msg}")
                with self.lock:
                    self.results[task_id] = {
                        'success': False,
                        'data': None,
                        'error': error_msg
                    }
    
    def submit_task(self, func, task_id: str, *args, **kwargs) -> threading.Thread:
        """提交任务到线程池"""
        thread = threading.Thread(
            target=self._task_wrapper,
            args=(func, task_id) + args,
            kwargs=kwargs,
            name=f"Task-{task_id}"
        )
        thread.start()
        logger.debug(f"提交任务 {task_id}，当前并发数: {self.max_concurrent - self.semaphore._value}")
        return thread
    
    def wait_for_all_tasks(self) -> None:
        """等待所有任务完成"""
        main_thread = threading.current_thread()
        for thread in threading.enumerate():
            if thread is not main_thread and thread.name.startswith("Task-"):
                thread.join()
        logger.info("所有任务执行完成")
    
    def get_task_results(self) -> Dict[str, Dict[str, Any]]:
        """获取所有任务结果"""
        return self.results.copy()

# -----------------------------------------------------------------------------
# 8. 主应用程序类 (约120行)
# -----------------------------------------------------------------------------
class CommissionQueryApp:
    """佣金查询应用主类"""
    
    def __init__(self):
        # 初始化配置
        self.config_manager = ConfigManager()
        self.api_config = self.config_manager.get_api_config()
        self.data_config = self.config_manager.get_data_config()
        
        # 初始化缓存
        self.cache_manager = CacheManager(ttl=self.data_config['cache_ttl'])
        
        # 初始化Sheets客户端
        self.sheets_client = SheetsAPIClient(self.api_config)
        
        # 初始化数据处理器
        self.data_processor = CommissionDataProcessor(
            self.sheets_client,
            self.cache_manager,
            self.data_config
        )
        
        # 初始化任务管理器
        self.task_manager = ThreadedTaskManager(
            max_concurrent=self.api_config['max_concurrent_threads']
        )
    
    def validate_sheet_exists(self, sheet_name: str) -> bool:
        """验证工作表是否存在"""
        sheets = self.sheets_client.list_sheets()
        if not sheets:
            return False
        return sheet_name in sheets
    
    def run_single_query(self, sheet_name: str, employee_name: str) -> None:
        """运行单个员工的佣金查询"""
        logger.info("="*60)
        logger.info(f"开始单员工查询: {employee_name} @ {sheet_name}")
        logger.info("="*60)
        
        # 验证工作表
        if not self.validate_sheet_exists(sheet_name):
            logger.error(f"工作表「{sheet_name}」不存在")
            return
        
        # 执行查询
        result = self.data_processor.get_employee_commission(sheet_name, employee_name)
        
        # 输出结果
        self._print_query_result(result)
    
    def run_batch_query(self, sheet_name: str, employee_names: List[str]) -> None:
        """运行批量员工佣金查询"""
        logger.info("="*60)
        logger.info(f"开始批量查询: {len(employee_names)}名员工 @ {sheet_name}")
        logger.info("="*60)
        
        # 验证工作表
        if not self.validate_sheet_exists(sheet_name):
            logger.error(f"工作表「{sheet_name}」不存在")
            return
        
        # 执行批量查询
        results = self.data_processor.batch_get_commission_data(sheet_name, employee_names)
        
        # 输出结果
        self._print_batch_results(results)
    
    def run_threaded_batch_query(self, sheet_name: str, employee_names: List[str]) -> None:
        """使用多线程运行批量查询"""
        logger.info("="*60)
        logger.info(f"开始多线程批量查询: {len(employee_names)}名员工 @ {sheet_name}")
        logger.info("="*60)
        
        # 验证工作表
        if not self.validate_sheet_exists(sheet_name):
            logger.error(f"工作表「{sheet_name}」不存在")
            return
        
        # 提交任务
        for emp_name in employee_names:
            self.task_manager.submit_task(
                self.data_processor.get_employee_commission,
                f"{sheet_name}_{emp_name}",
                sheet_name,
                emp_name
            )
        
        # 等待任务完成
        self.task_manager.wait_for_all_tasks()
        
        # 获取并输出结果
        results = self.task_manager.get_task_results()
        self._print_threaded_results(results)
    
    def _print_query_result(self, result: Dict[str, Any]) -> None:
        """打印单个查询结果"""
        print("\n" + "-"*50)
        print(f"查询结果: {result['employee_name']} @ {result['sheet_name']}")
        print("-"*50)
        
        if result['found']:
            data = result['data']
            print(f"行号: {data['row_number']}")
            print(f"员工姓名: {data['name']}")
            print(f"佣金金额: {data['commission']}")
            print(f"部门: {data.get('department', 'N/A')}")
            print(f"日期: {data.get('date', 'N/A')}")
            print(f"状态: {data.get('status', 'N/A')}")
        else:
            print(f"错误: {result['error']}")
        print("-"*50 + "\n")
    
    def _print_batch_results(self, results: Dict[str, Dict[str, Any]]) -> None:
        """打印批量查询结果"""
        print("\n" + "="*60)
        print("批量查询结果汇总")
        print("="*60)
        
        found_count = 0
        for emp_name, result in results.items():
            print(f"\n🔍 {emp_name}:")
            if result['found']:
                found_count += 1
                data = result['data']
                print(f"  ✅ 找到数据 (行{data['row_number']})")
                print(f"     佣金: {data['commission']}")
                print(f"     部门: {data.get('department', 'N/A')}")
            else:
                print(f"  ❌ {result['error']}")
        
        print(f"\n📊 汇总: 共查询{len(results)}名员工，找到{found_count}名员工的数据")
        print("="*60 + "\n")
    
    def _print_threaded_results(self, results: Dict[str, Dict[str, Any]]) -> None:
        """打印多线程查询结果"""
        print("\n" + "="*60)
        print("多线程查询结果汇总")
        print("="*60)
        
        success_count = 0
        found_count = 0
        
        for task_id, result in results.items():
            emp_name = task_id.split("_")[-1]
            print(f"\n🔍 {emp_name}:")
            
            if not result['success']:
                print(f"  ❌ 任务执行失败: {result['error']}")
                continue
            
            success_count += 1
            query_result = result['data']
            
            if query_result['found']:
                found_count += 1
                data = query_result['data']
                print(f"  ✅ 找到数据 (行{data['row_number']})")
                print(f"     佣金: {data['commission']}")
            else:
                print(f"  ❌ {query_result['error']}")
        
        print(f"\n📊 汇总: 共提交{len(results)}个任务，成功{success_count}个，找到{found_count}名员工的数据")
        print("="*60 + "\n")
    
    def export_results_to_json(self, results: Dict[str, Any], output_file: Path) -> None:
        """导出查询结果到JSON文件"""
        try:
            with open(output_file, 'w', encoding='utf-8') as f:
                json.dump({
                    'export_time': datetime.now().isoformat(),
                    'results': results
                }, f, ensure_ascii=False, indent=2)
            logger.info(f"结果已导出到: {output_file}")
        except Exception as e:
            logger.error(f"导出结果失败: {str(e)}")

# -----------------------------------------------------------------------------
# 9. 命令行交互与主入口 (约80行)
# -----------------------------------------------------------------------------
def print_welcome_banner() -> None:
    """打印欢迎横幅"""
    banner = f"""
{'='*70}
欢迎使用 Google Sheets 佣金数据查询系统
当前时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
项目目录: {PROJECT_ROOT}
功能说明:
  1. 解决API 429限流问题（请求频率超限）
  2. 支持单员工/批量员工佣金查询
  3. 支持多线程并发查询（可控）
  4. 内置缓存机制，减少重复API请求
  5. 完整的日志记录和错误处理
{'='*70}
"""
    print(banner)

def main():
    """主函数"""
    try:
        # 打印欢迎信息
        print_welcome_banner()
        
        # 初始化应用
        app = CommissionQueryApp()
        
        # 示例配置 - 请根据实际需求修改
        TARGET_SHEET = "202512"  # 目标工作表
        TARGET_EMPLOYEES = [     # 目标员工列表
            "Ana Cruz",
            "Karina Albarran",
            "Maria Garcia",
            "Juan Rodriguez",
            "Luis Martinez"
        ]
        
        # 执行查询（可选三种模式）
        # 模式1: 单员工查询
        # app.run_single_query(TARGET_SHEET, TARGET_EMPLOYEES[0])
        
        # 模式2: 批量查询（单线程）
        # results = app.data_processor.batch_get_commission_data(TARGET_SHEET, TARGET_EMPLOYEES)
        # app._print_batch_results(results)
        # app.export_results_to_json(results, PROJECT_ROOT / "batch_results.json")
        
        # 模式3: 多线程批量查询（推荐，效率更高且可控）
        app.run_threaded_batch_query(TARGET_SHEET, TARGET_EMPLOYEES)
        
        # 导出多线程结果
        threaded_results = app.task_manager.get_task_results()
        app.export_results_to_json(threaded_results, PROJECT_ROOT / "threaded_results.json")
        
        logger.info("程序执行完成！")
        
    except KeyboardInterrupt:
        logger.info("用户中断程序执行")
        sys.exit(0)
    except Exception as e:
        logger.error(f"程序执行出错: {str(e)}", exc_info=True)
        sys.exit(1)

# -----------------------------------------------------------------------------
# 10. 模块入口
# -----------------------------------------------------------------------------
if __name__ == "__main__":
    # 设置Python递归深度（防止多线程场景下栈溢出）
    sys.setrecursionlimit(10000)
    
    # 运行主程序
    main()
