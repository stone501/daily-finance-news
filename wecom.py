#!/usr/bin/env python3
"""
企业微信推送模块
- 发送文本卡片消息（资讯摘要 + 链接）
- 发送文本消息（失败告警）
"""
import os
import time
import requests


class WeCom:
    def __init__(self):
        self.corp_id = os.environ["WECOM_CORPID"]
        self.agent_id = os.environ["WECOM_AGENTID"]
        self.secret = os.environ["WECOM_SECRET"]
        self._token = None
        self._token_expire = 0

    def get_token(self):
        """获取企业微信 access_token"""
        if self._token and time.time() < self._token_expire:
            return self._token

        url = "https://qyapi.weixin.qq.com/cgi-bin/gettoken"
        params = {"corpid": self.corp_id, "corpsecret": self.secret}
        resp = requests.get(url, params=params, timeout=10)
        data = resp.json()

        if data.get("errcode") != 0:
            raise Exception(f"企业微信获取 token 失败: {data}")

        self._token = data["access_token"]
        self._token_expire = time.time() + data.get("expires_in", 7200) - 300
        return self._token

    def send_textcard(self, title, description, url, btntxt="查看原文"):
        """发送文本卡片消息"""
        token = self.get_token()
        api_url = f"https://qyapi.weixin.qq.com/cgi-bin/message/send?access_token={token}"

        body = {
            "touser": "@all",
            "msgtype": "textcard",
            "agentid": int(self.agent_id),
            "textcard": {
                "title": title,
                "description": description,
                "url": url,
                "btntxt": btntxt,
            },
        }
        resp = requests.post(api_url, json=body, timeout=10)
        data = resp.json()

        if data.get("errcode") != 0:
            raise Exception(f"企业微信发送卡片失败: {data}")
        return True

    def send_text(self, content):
        """发送纯文本消息（用于告警）"""
        token = self.get_token()
        api_url = f"https://qyapi.weixin.qq.com/cgi-bin/message/send?access_token={token}"

        body = {
            "touser": "@all",
            "msgtype": "text",
            "agentid": int(self.agent_id),
            "text": {"content": content},
        }
        resp = requests.post(api_url, json=body, timeout=10)
        data = resp.json()

        if data.get("errcode") != 0:
            raise Exception(f"企业微信发送文本失败: {data}")
        return True


if __name__ == "__main__":
    wecom = WeCom()
    try:
        wecom.send_text("测试消息：企业微信推送通道正常")
        print("发送成功")
    except Exception as e:
        print(f"发送失败: {e}")
