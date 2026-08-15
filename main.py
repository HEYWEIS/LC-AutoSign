# -*- coding: UTF-8 -*-

import requests
import json
import time
import random
import os
from requests.exceptions import RequestException

TOKEN_LIST = os.getenv('TOKEN_LIST', '')
SEND_KEY_LIST = os.getenv('SEND_KEY_LIST', '')

# 接口配置
url = 'https://m.jlc.com/api/activity/sign/signIn?source=3'
gold_bean_url = "https://m.jlc.com/api/appPlatform/center/assets/selectPersonalAssetsInfo"
seventh_day_url = "https://m.jlc.com/api/activity/sign/receiveVoucher"


# ======== 工具函数 ========

def mask_account(account):
    """用于打印时隐藏部分账号信息"""
    if len(account) >= 4:
        return account[:2] + '****' + account[-2:]
    return '****'


def mask_json_customer_code(data):
    """递归地脱敏 JSON 中的 customerCode 字段"""
    if isinstance(data, dict):
        new_data = {}
        for k, v in data.items():
            if k == "customerCode" and isinstance(v, str):
                new_data[k] = v[:1] + "xxxxx" + v[-2:]
            else:
                new_data[k] = mask_json_customer_code(v)
        return new_data
    elif isinstance(data, list):
        return [mask_json_customer_code(i) for i in data]
    else:
        return data


# ======== 推送通知 ========

def send_msg_by_server(send_key, title, content):
    push_url = f'https://sctapi.ftqq.com/{send_key}.send'
    data = {
        'text': title,
        'desp': content
    }
    try:
        response = requests.post(push_url, data=data, timeout=15)
        response.raise_for_status()
        return response.json()
    except RequestException as e:
        print(f"❌ 推送请求异常: {str(e)}")
        return None
    except Exception as e:
        print(f"❌ 推送未知异常: {str(e)}")
        return None


# ======== 单个账号签到逻辑 ========

def sign_in(access_token, retries=3, backoff=10):
    headers = {
        'X-JLC-AccessToken': access_token,
        'User-Agent': 'Mozilla/5.0 (iPhone; CPU iPhone OS 17_2_1 like Mac OS X) '
                      'AppleWebKit/605.1.15 (KHTML, like Gecko) Mobile/15E148 Html5Plus/1.0 (Immersed/20) JlcMobileApp',
    }

    for attempt in range(1, retries + 1):
        try:
            # 1. 获取金豆信息（先获取，用于获取 customer_code）
            bean_response = requests.get(gold_bean_url, headers=headers, timeout=15)
            bean_response.raise_for_status()
            bean_result = bean_response.json()

            # 获取 customerCode
            customer_code = bean_result['data']['customerCode']
            integral_voucher = bean_result['data']['integralVoucher']

            # 2. 执行签到请求
            sign_response = requests.get(url, headers=headers, timeout=15)
            sign_response.raise_for_status()
            sign_result = sign_response.json()

            # 检查签到是否成功
            if not sign_result.get('success'):
                message = sign_result.get('message', '未知错误')
                if '已经签到' in message:
                    print(f"ℹ️ [账号{mask_account(customer_code)}] 今日已签到")
                    return f"ℹ️ 账号({mask_account(customer_code)})：今日已签到，当前金豆总数：{integral_voucher}"
                else:
                    print(f"❌ [账号{mask_account(customer_code)}] 签到失败 - {message}")
                    return f"❌ 账号({mask_account(customer_code)})：签到失败 - {message}"

            # 解析签到数据
            data = sign_result.get('data', {})

            # 安全地获取 gainNum 和 status
            gain_num = data.get('gainNum') if data else None
            status = data.get('status') if data else None

            # 处理签到结果
            if status and status > 0:
                if gain_num is not None and gain_num != 0:
                    print(f"✅ [账号{mask_account(customer_code)}] 今日签到成功")
                    return f"✅ 账号({mask_account(customer_code)})：获取{gain_num}个金豆，当前总数：{integral_voucher + gain_num}"
                else:
                    # 第七天特殊处理
                    seventh_response = requests.get(seventh_day_url, headers=headers, timeout=15)
                    seventh_response.raise_for_status()
                    seventh_result = seventh_response.json()

                    if seventh_result.get("success"):
                        print(f"🎉 [账号{mask_account(customer_code)}] 第七天签到成功")
                        return f"🎉 账号({mask_account(customer_code)})：第七天签到成功，当前金豆总数：{integral_voucher + 8}"
                    else:
                        print(f"ℹ️ [账号{mask_account(customer_code)}] 第七天签到失败，无金豆获取")
                        return f"ℹ️ 账号({mask_account(customer_code)})：第七天签到失败，当前金豆总数：{integral_voucher}"
            else:
                print(f"ℹ️ [账号{mask_account(customer_code)}] 今日已签到或签到失败")
                return f"ℹ️ 账号({mask_account(customer_code)})：签到状态异常，当前金豆总数：{integral_voucher}"

        except RequestException as e:
            print(f"⚠️ [账号{mask_account(access_token)}] 第{attempt}次请求失败: {str(e)}")
            if attempt < retries:
                wait = backoff * attempt
                print(f"⏳ {wait} 秒后重试...")
                time.sleep(wait)
            else:
                print(f"❌ [账号{mask_account(access_token)}] 已重试 {retries} 次，放弃")
                return f"❌ 账号({mask_account(access_token)})：请求失败，已重试 {retries} 次 - {str(e)}"
        except KeyError as e:
            print(f"❌ [账号{mask_account(access_token)}] 数据解析失败: 缺少键 {str(e)}")
            return f"❌ 账号({mask_account(access_token)})：数据解析失败 - 缺少键 {str(e)}"
        except Exception as e:
            print(f"❌ [账号{mask_account(access_token)}] 未知错误: {str(e)}")
            return f"❌ 账号({mask_account(access_token)})：未知错误 - {str(e)}"


# ======== 主函数 ========

def main():
    # 从 GitHub Secrets 获取配置
    AccessTokenList = [token.strip() for token in TOKEN_LIST.split(',') if token.strip()]
    SendKeyList = [key.strip() for key in SEND_KEY_LIST.split(',') if key.strip()]

    # 检查配置是否为空
    if not AccessTokenList:
        print("❌ 请设置 TOKEN_LIST")
        return

    if not SendKeyList:
        print("❌ 请设置 SEND_KEY_LIST")
        return

    # SendKey 去重（保序），所有 key 都将收到相同的完整汇总
    unique_send_keys = list(dict.fromkeys(SendKeyList))

    print(f"🔧 共发现 {len(AccessTokenList)} 个账号需要签到")
    print(f"📊 共 {len(unique_send_keys)} 个推送目标（去重后）")

    # ======== 第一步：执行所有账号签到，汇总结果 ========
    print("\n🚀 开始签到任务")
    results = []

    for i, token in enumerate(AccessTokenList):
        print(f"📝 处理第 {i+1}/{len(AccessTokenList)} 个账号...")

        # 执行签到
        result = sign_in(token)
        if result:
            results.append(result)

        # 如果不是最后一个账号，则等待随机时间
        if i < len(AccessTokenList) - 1:
            wait_time = random.randint(5, 15)
            print(f"⏳ 等待 {wait_time} 秒后处理下一个账号...")
            time.sleep(wait_time)

    # ======== 第二步：将完整汇总推送给每个 SendKey ========
    print("\n📬 开始推送通知...")
    if not results:
        print("ℹ️ 所有账号均未获取到金豆，无通知发送")
        return

    content = "\n\n".join(results)
    notification_sent = False

    for send_key in unique_send_keys:
        print(f"📤 推送给 SendKey: {send_key[:5]}...")

        response = send_msg_by_server(send_key, "嘉立创签到汇总", content)

        if response and response.get('code') == 0:
            print(f"✅ 通知发送成功！消息ID: {response.get('data', {}).get('pushid', '')}")
            notification_sent = True
        else:
            error_msg = response.get('message') if response else '网络异常或推送服务无响应'
            print(f"❌ 通知发送失败！错误: {error_msg}")

    if not notification_sent:
        print("ℹ️ 所有 SendKey 均推送失败")


# ======== 程序入口 ========

if __name__ == '__main__':
    print("🏁 嘉立创自动签到任务开始")
    main()
    print("🏁 任务执行完毕")
