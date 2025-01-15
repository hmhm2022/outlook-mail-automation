#!/usr/bin/env python3
"""
Microsoft OAuth2认证脚本
用于获取Microsoft的access_token和refresh_token
"""

from DrissionPage import Chromium
import requests
from typing import Dict
import logging
import configparser
from urllib.parse import quote, parse_qs
import time
from datetime import datetime
import winreg

def get_proxy():
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Internet Settings") as key:
            proxy_enable, _ = winreg.QueryValueEx(key, "ProxyEnable")
            proxy_server, _ = winreg.QueryValueEx(key, "ProxyServer")
            
            if proxy_enable and proxy_server:
                proxy_parts = proxy_server.split(":")
                if len(proxy_parts) == 2:
                    return {"http": f"http://{proxy_server}", "https": f"http://{proxy_server}"}
    except WindowsError:
        pass
    return {"http": None, "https": None}

def load_config():
    config = configparser.ConfigParser()
    config.read('config.txt', encoding='utf-8')
    return config

def save_config(config):
    with open('config.txt', 'w', encoding='utf-8') as f:
        config.write(f)

# 配置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# 加载配置
config = load_config()
microsoft_config = config['microsoft']

CLIENT_ID = microsoft_config['client_id']
CLIENT_SECRET = microsoft_config['client_secret']
REDIRECT_URI = microsoft_config['redirect_uri']

# API端点
AUTH_URL = 'https://login.microsoftonline.com/common/oauth2/v2.0/authorize'
TOKEN_URL = 'https://login.microsoftonline.com/common/oauth2/v2.0/token'

# 权限范围
SCOPES = [
    'offline_access',
    'https://graph.microsoft.com/Mail.ReadWrite',
    'https://graph.microsoft.com/Mail.Send',
    'https://graph.microsoft.com/User.Read'
]

def request_authorization(tab) -> str:
    """请求Microsoft OAuth2授权"""
    scope = ' '.join(SCOPES)
    auth_params = {
        'client_id': CLIENT_ID,
        'response_type': 'code',
        'redirect_uri': REDIRECT_URI,
        'scope': scope,
        'response_mode': 'query',
        'prompt': 'select_account',
    }
    
    params = '&'.join([f'{k}={quote(v)}' for k, v in auth_params.items()])
    auth_url = f'{AUTH_URL}?{params}'
    
    tab.get(auth_url)
    logger.info("等待用户登录和授权...")
    
    tab.wait.url_change(text='localhost:8000', timeout=300)  # 5分钟超时
    
    callback_url = tab.url
    logger.info(f"回调URL: {callback_url}")
    
    query_components = parse_qs(callback_url.split('?')[1]) if '?' in callback_url else {}
    
    if 'code' not in query_components:
        raise ValueError("未能获取授权码")
    
    auth_code = query_components['code'][0]
    logger.info("成功获取授权码")
    return auth_code

def get_tokens(auth_code: str) -> Dict[str, str]:
    """使用授权码获取访问令牌和刷新令牌"""
    token_params = {
        'client_id': CLIENT_ID,
        'client_secret': CLIENT_SECRET,
        'code': auth_code,
        'redirect_uri': REDIRECT_URI,
        'grant_type': 'authorization_code',
        'scope': ' '.join(SCOPES)
    }
    
    headers = {
        'Content-Type': 'application/x-www-form-urlencoded'
    }
    
    try:
        response = requests.post(TOKEN_URL, data=token_params, headers=headers, proxies=get_proxy())
        response.raise_for_status()
        return response.json()
    except requests.RequestException as e:
        logger.error(f"获取令牌失败: {e}")
        if hasattr(e, 'response'):
            logger.error(f"响应内容: {e.response.text}")
        raise

def main():
    try:
        browser = Chromium()
        tab = browser.new_tab() 

        logger.info("正在打开浏览器进行授权...")
        
        try:
            auth_code = request_authorization(tab)
            tab.close()
            logger.info("成功获取授权码！")
            
            tokens = get_tokens(auth_code)
            
            if 'refresh_token' in tokens:
                logger.info("成功获取refresh_token！")
                config['tokens']['refresh_token'] = tokens['refresh_token']
                if 'access_token' in tokens:
                    config['tokens']['access_token'] = tokens['access_token']
                    expires_at = time.time() + tokens['expires_in']
                    expires_at_str = datetime.fromtimestamp(expires_at).strftime('%Y-%m-%d %H:%M:%S')
                    config['tokens']['expires_at'] = expires_at_str
                save_config(config)
        finally:
            browser.quit()
        
    except Exception as e:
        logger.error(f"程序执行出错: {e}")
        raise

if __name__ == '__main__':
    main()