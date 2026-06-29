#!/usr/bin/env python3
"""
每日财税资讯自动推送 - 主流程

流程：采集 → 评分挑Top1 → LLM生成正文 → 生成配图 → 推送公众号草稿箱 → 推送企业微信摘要
失败时通过企业微信发送告警。
"""
import sys
import os
import traceback
import requests
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from collectors import collect
from generator import generate_article, generate_cover, generate_inline_image
from wechat_mp import WeChatMP
from wecom import WeCom
from template import ARTICLE_TEMPLATE


def print_ip():
    """打印出口 IP（用于配置公众号白名单）"""
    try:
        resp = requests.get("https://api.ipify.org", timeout=5)
        print(f"[出口 IP] {resp.text}")
    except Exception:
        print("[出口 IP] 获取失败")


def notify_wecom(message, is_error=False):
    """通过企业微信发送通知（失败不中断主流程）"""
    try:
        wecom = WeCom()
        prefix = "【异常告警】" if is_error else "【推送通知】"
        wecom.send_text(prefix + "\n\n" + message)
    except Exception as e:
        print(f"[企业微信通知失败] {e}")


def main():
    start_time = datetime.now()
    print(f"[{start_time.strftime('%Y-%m-%d %H:%M:%S')}] 开始执行每日财税资讯推送")
    print("=" * 60)

    print_ip()
    print("=" * 60)

    # ===== 第 1 步：采集 =====
    print(">>> [1/5] 采集资讯...")
    articles = collect()
    print(f"    采集到 {len(articles)} 条资讯")

    if not articles:
        msg = "今日未采集到资讯，请检查 DuckDuckGo 搜索是否正常。"
        print(f"[警告] {msg}")
        notify_wecom(msg, is_error=True)
        return

    # ===== 第 2 步：挑选 Top1 =====
    print(">>> [2/5] 挑选 Top1...")
    top1 = articles[0]
    print(f"    选中: {top1['title']}")
    print(f"    来源: {top1['url']}")
    print(f"    评分: {top1['score']:.1f}")

    # ===== 第 3 步：AI 生成 =====
    print(">>> [3/5] AI 生成文章...")
    article = generate_article(top1)
    print(f"    标题: {article.get('title', '未知')}")
    print(f"    摘要: {article.get('digest', '')[:50]}...")

    print("    生成封面图...")
    cover_img = generate_cover(article.get("title", ""))
    print("    生成内文配图...")
    inline_img = generate_inline_image("flexible employment HR outsourcing")

    # ===== 第 4 步：推送公众号草稿箱 =====
    print(">>> [4/5] 推送公众号草稿箱...")
    try:
        mp = WeChatMP()

        # 上传封面
        thumb_media_id = mp.upload_thumb(cover_img)
        print(f"    封面上传成功: {thumb_media_id}")

        # 上传内文图
        inline_url = mp.upload_content_image(inline_img)
        print(f"    内文图上传成功: {inline_url}")

        # 正文开头插入配图
        content_with_image = f'<p><img src="{inline_url}" style="width:100%; border-radius:8px;"/></p>' + article.get("content", "")

        # 套用排版模板
        final_content = ARTICLE_TEMPLATE.format(
            digest=article.get("digest", ""),
            content=content_with_image,
            source_url=article.get("source_url", top1["url"]),
        )

        article["content"] = final_content
        article["thumb_media_id"] = thumb_media_id

        # 创建草稿
        draft_id = mp.add_draft(article)
        print(f"    草稿创建成功: {draft_id}")

    except Exception as e:
        error_detail = traceback.format_exc()[:800]
        error_msg = (
            f"公众号草稿箱推送失败\n\n"
            f"错误: {e}\n\n"
            f"文章标题: {article.get('title', '未知')}\n"
            f"文章摘要: {article.get('digest', '')[:80]}\n\n"
            f"详细信息:\n{error_detail}"
        )
        print(f"[错误] {error_msg}")
        notify_wecom(error_msg, is_error=True)
        return

    # ===== 第 5 步：推送企业微信摘要 =====
    print(">>> [5/5] 推送企业微信摘要...")
    try:
        wecom = WeCom()
        wecom.send_textcard(
            title=f"今日财税资讯: {article['title'][:30]}",
            description=(
                f"{article.get('digest', '')[:100]}\n\n"
                f"已自动写入公众号草稿箱\n"
                f"请登录 mp.weixin.qq.com 审核发布"
            ),
            url=article.get("source_url", top1["url"]),
            btntxt="查看原文",
        )
        print("    企业微信推送成功")
    except Exception as e:
        print(f"[企业微信推送失败] {e}")
        # 不影响整体流程

    # ===== 完成 =====
    elapsed = (datetime.now() - start_time).total_seconds()
    print("=" * 60)
    print(f"[完成] 耗时 {elapsed:.0f} 秒")
    print(f"  草稿 ID: {draft_id}")
    print(f"  文章标题: {article['title']}")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        error_msg = f"流程异常终止: {e}\n\n{traceback.format_exc()[:500]}"
        print(f"[严重错误] {error_msg}")
        try:
            notify_wecom(error_msg, is_error=True)
        except Exception:
            pass
        sys.exit(1)
