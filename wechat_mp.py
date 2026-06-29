#!/usr/bin/env python3
"""
微信公众号 API 模块
- 获取 access_token（带缓存）
- 上传永久素材（封面图）
- 上传图文内图片（返回 URL）
- 创建草稿
"""
import os
import time
import requests


class WeChatMP:
    def __init__(self):
        self.appid = os.environ["MP_APPID"]
        self.secret = os.environ["MP_SECRET"]
        self._token = None
        self._token_expire = 0

    def get_token(self):
        """获取 access_token，带 5 分钟提前刷新缓存"""
        if self._token and time.time() < self._token_expire:
            return self._token

        url = "https://api.weixin.qq.com/cgi-bin/token"
        params = {
            "grant_type": "client_credential",
            "appid": self.appid,
            "secret": self.secret,
        }
        resp = requests.get(url, params=params, timeout=10)
        data = resp.json()

        if "access_token" not in data:
            raise Exception(f"获取 access_token 失败: {data}")

        self._token = data["access_token"]
        self._token_expire = time.time() + data.get("expires_in", 7200) - 300
        print(f"  access_token 获取成功，有效期 {data.get('expires_in', 7200)} 秒")
        return self._token

    def upload_thumb(self, image_io):
        """上传封面图为永久素材，返回 media_id"""
        token = self.get_token()
        url = f"https://api.weixin.qq.com/cgi-bin/material/add_material?access_token={token}&type=image"
        image_io.seek(0)
        files = {"media": ("cover.png", image_io, "image/png")}
        resp = requests.post(url, files=files, timeout=60)
        data = resp.json()

        if "media_id" not in data:
            raise Exception(f"上传封面素材失败: {data}")
        return data["media_id"]

    def upload_content_image(self, image_io):
        """上传内文图片，返回 URL（用于图文内容中 img src 引用）"""
        token = self.get_token()
        url = f"https://api.weixin.qq.com/cgi-bin/media/uploadimg?access_token={token}"
        image_io.seek(0)
        files = {"media": ("inline.png", image_io, "image/png")}
        resp = requests.post(url, files=files, timeout=60)
        data = resp.json()

        if "url" not in data:
            raise Exception(f"上传内文图失败: {data}")
        return data["url"]

    def add_draft(self, article):
        """创建草稿，返回草稿 media_id"""
        token = self.get_token()
        url = f"https://api.weixin.qq.com/cgi-bin/draft/add?access_token={token}"

        body = {
            "articles": [
                {
                    "title": article["title"],
                    "author": article.get("author", "财税资讯"),
                    "digest": article.get("digest", "")[:120],
                    "content": article["content"],
                    "content_source_url": article.get("source_url", ""),
                    "thumb_media_id": article["thumb_media_id"],
                    "need_open_comment": 0,
                    "only_fans_can_comment": 0,
                }
            ]
        }
        resp = requests.post(url, json=body, timeout=30)
        data = resp.json()

        if "media_id" not in data:
            raise Exception(f"创建草稿失败: {data}")
        return data["media_id"]


if __name__ == "__main__":
    # 快速验证 access_token
    mp = WeChatMP()
    try:
        token = mp.get_token()
        print(f"access_token: {token[:20]}...")
    except Exception as e:
        print(f"失败: {e}")
