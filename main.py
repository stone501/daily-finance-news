#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
每日财税资讯自动推送 - 单文件版（零第三方依赖，只用 Python 标准库）

流程：采集 → 评分挑Top1 → LLM生成正文 → 生成配图 → 推送企业微信群机器人
腾讯云函数 SCF 直接粘贴此文件即可运行，无需安装任何依赖。
"""
import os
import sys
import json
import time
import hashlib
import base64
import re
import urllib.request
import urllib.parse
import urllib.error
from html.parser import HTMLParser
from datetime import datetime
import traceback


# ============================================================
# 配置
# ============================================================
SEARCH_QUERIES = [
    "灵活用工结算 政策 2025",
    "灵活用工平台 最新动态",
    "人力资源外包 新规",
    "HRO 人力资源外包 行业",
    "劳务外包 政策解读",
    "个税汇算 灵活用工",
    "社保新政 灵活就业",
    "用工合规 灵活用工",
    "平台经济 用工 政策",
    "新就业形态 权益保障",
    "零工经济 税务合规",
    "灵活用工 税务风险",
]

AUTHORITATIVE_SOURCES = {
    "chinatax.gov.cn": 1.0, "mohrss.gov.cn": 1.0, "gov.cn": 0.9,
    "npc.gov.cn": 0.9, "12366": 0.8, "yicai.com": 0.7,
    "caixin.com": 0.7, "21jingji.com": 0.7, "cs.com.cn": 0.7,
    "thepaper.cn": 0.6,
}

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}


# ============================================================
# HTTP 请求工具（替代 requests）
# ============================================================
def http_get(url, timeout=15, headers=None):
    """GET 请求，返回 (状态码, 文本内容)"""
    h = dict(HEADERS)
    if headers:
        h.update(headers)
    req = urllib.request.Request(url, headers=h)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            charset = resp.headers.get_content_charset() or "utf-8"
            return resp.status, resp.read().decode(charset, errors="replace")
    except urllib.error.HTTPError as e:
        return e.code, str(e)
    except Exception as e:
        return 0, str(e)


def http_post(url, data=None, json_data=None, timeout=30, headers=None):
    """POST 请求，返回 (状态码, 文本内容)"""
    h = dict(HEADERS)
    if headers:
        h.update(headers)
    body = None
    if json_data is not None:
        body = json.dumps(json_data).encode("utf-8")
        h["Content-Type"] = "application/json"
    elif data is not None:
        body = data if isinstance(data, bytes) else data.encode("utf-8")
    req = urllib.request.Request(url, data=body, headers=h, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            charset = resp.headers.get_content_charset() or "utf-8"
            return resp.status, resp.read().decode(charset, errors="replace")
    except urllib.error.HTTPError as e:
        charset = e.headers.get_content_charset() or "utf-8"
        return e.code, e.read().decode(charset, errors="replace")
    except Exception as e:
        return 0, str(e)


def http_post_multipart(url, fields, files, timeout=60):
    """multipart POST（上传文件用），files = [(fieldname, filename, content_bytes, content_type)]"""
    boundary = "----WebKitFormBoundary" + hashlib.md5(str(time.time()).encode()).hexdigest()[:16]
    body = b""
    for name, value in fields:
        body += f"--{boundary}\r\n".encode()
        body += f'Content-Disposition: form-data; name="{name}"\r\n\r\n'.encode()
        body += f"{value}\r\n".encode()
    for fieldname, filename, content, content_type in files:
        body += f"--{boundary}\r\n".encode()
        body += f'Content-Disposition: form-data; name="{fieldname}"; filename="{filename}"\r\n'.encode()
        body += f"Content-Type: {content_type}\r\n\r\n".encode()
        body += content + b"\r\n"
    body += f"--{boundary}--\r\n".encode()

    h = dict(HEADERS)
    h["Content-Type"] = f"multipart/form-data; boundary={boundary}"
    req = urllib.request.Request(url, data=body, headers=h, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            charset = resp.headers.get_content_charset() or "utf-8"
            return resp.status, resp.read().decode(charset, errors="replace")
    except urllib.error.HTTPError as e:
        charset = e.headers.get_content_charset() or "utf-8"
        return e.code, e.read().decode(charset, errors="replace")
    except Exception as e:
        return 0, str(e)


def http_get_bytes(url, timeout=90):
    """GET 请求返回 bytes（下载图片用）"""
    req = urllib.request.Request(url, headers=HEADERS)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, resp.read()
    except Exception as e:
        return 0, b""


# ============================================================
# HTML 正文提取（替代 BeautifulSoup + trafilatura）
# ============================================================
class TextExtractor(HTMLParser):
    """简易 HTML 正文提取器"""
    def __init__(self):
        super().__init__()
        self.skip_tags = {"script", "style", "nav", "footer", "header", "aside", "form", "noscript"}
        self.in_skip = 0
        self.in_p = False
        self.paragraphs = []
        self.current_text = ""

    def handle_starttag(self, tag, attrs):
        if tag in self.skip_tags:
            self.in_skip += 1
        if tag == "p" and self.in_skip == 0:
            self.in_p = True
            self.current_text = ""

    def handle_endtag(self, tag):
        if tag in self.skip_tags and self.in_skip > 0:
            self.in_skip -= 1
        if tag == "p" and self.in_p:
            self.in_p = False
            text = self.current_text.strip()
            if len(text) > 20:
                self.paragraphs.append(text)

    def handle_data(self, data):
        if self.in_p and self.in_skip == 0:
            self.current_text += data


def extract_text(html):
    """从 HTML 提取正文"""
    parser = TextExtractor()
    try:
        parser.feed(html)
    except Exception:
        pass
    text = "\n".join(parser.paragraphs)
    return text if len(text) > 100 else ""


# ============================================================
# 采集模块
# ============================================================
def search_ddg(query, max_results=5):
    """DuckDuckGo HTML 搜索"""
    url = "https://html.duckduckgo.com/html/"
    data = urllib.parse.urlencode({"q": query, "kl": "cn-zh"}).encode("utf-8")
    results = []
    for attempt in range(3):
        try:
            req = urllib.request.Request(url, data=data, headers=HEADERS, method="POST")
            with urllib.request.urlopen(req, timeout=15) as resp:
                html = resp.read().decode("utf-8", errors="replace")

            # 提取搜索结果（正则匹配）
            pattern = r'class="result__a"[^>]*href="([^"]*)"[^>]*>(.*?)</a>'
            for m in re.finditer(pattern, html, re.DOTALL):
                raw_url = m.group(1)
                title_html = m.group(2)
                # 解析真实 URL
                real_url = raw_url
                if "uddg=" in raw_url:
                    parsed = urllib.parse.urlparse(raw_url)
                    params = urllib.parse.parse_qs(parsed.query)
                    real_url = params.get("uddg", [None])[0]
                if not real_url:
                    continue
                # 清理标题
                title = re.sub(r"<[^>]+>", "", title_html).strip()
                if not title:
                    continue
                results.append({"title": title, "url": real_url, "snippet": ""})

            # 提取摘要
            snippet_pattern = r'class="result__snippet"[^>]*>(.*?)</(?:a|span|div)'
            snippets = re.findall(snippet_pattern, html, re.DOTALL)
            for i, s in enumerate(snippets):
                if i < len(results):
                    results[i]["snippet"] = re.sub(r"<[^>]+>", "", s).strip()

            if results:
                break
            time.sleep(2)
        except Exception as e:
            print(f"  [搜索重试 {attempt+1}] {query}: {e}")
            time.sleep(3)
    return results[:max_results]


def fetch_content(url):
    """抓取网页正文"""
    for attempt in range(2):
        status, text = http_get(url, timeout=15)
        if status == 200 and text:
            content = extract_text(text)
            if content and len(content) > 100:
                return content
        else:
            print(f"  [抓取重试 {attempt+1}] {url}: {status}")
        time.sleep(2)
    return ""


def score_article(article):
    """热度评分"""
    score = 0.0
    url = article.get("url", "").lower()
    for domain, weight in AUTHORITATIVE_SOURCES.items():
        if domain in url:
            score += weight * 30
            break
    else:
        score += 10
    score += min(len(article.get("snippet", "")) / 10, 20)
    score += min(len(article.get("content", "")) / 100, 30)
    if article.get("content"):
        score += 10
    return score


def collect():
    """主采集函数"""
    all_results = []
    seen_urls = set()
    seen_titles = set()

    print("  开始 DuckDuckGo 搜索...")
    for i, query in enumerate(SEARCH_QUERIES):
        print(f"  [{i+1}/{len(SEARCH_QUERIES)}] 搜索: {query}")
        results = search_ddg(query, max_results=5)
        for r in results:
            url_key = r["url"].split("?")[0].split("#")[0]
            title_key = r["title"][:20]
            if url_key in seen_urls or title_key in seen_titles:
                continue
            seen_urls.add(url_key)
            seen_titles.add(title_key)
            all_results.append(r)
        time.sleep(1)

    print(f"  搜索完成，去重后 {len(all_results)} 条")
    if not all_results:
        return []

    print("  开始抓取正文...")
    for i, article in enumerate(all_results[:15]):
        print(f"  [{i+1}/15] 抓取: {article['title'][:40]}")
        article["content"] = fetch_content(article["url"])
        article["score"] = score_article(article)
        time.sleep(0.5)

    for article in all_results[15:]:
        article["content"] = ""
        article["score"] = score_article(article)

    all_results.sort(key=lambda x: x["score"], reverse=True)
    print(f"  评分排序完成，Top1: {all_results[0]['title'][:50]}")
    return all_results


# ============================================================
# LLM 生成模块（直接调 DeepSeek API，不用 openai 库）
# ============================================================
def generate_article(source):
    """用 DeepSeek 生成高质量公众号文章"""
    api_key = os.environ.get("LLM_API_KEY", "")
    base_url = os.environ.get("LLM_BASE_URL", "https://api.deepseek.com/v1")
    model = os.environ.get("LLM_MODEL", "deepseek-v4-flash")

    source_content = (source.get("content", "") or source.get("snippet", ""))[:4000]

    prompt = f"""你是一位拥有15年经验的资深财税咨询专家，同时具备注册会计师和税务师资质，专注于灵活用工结算和人力资源外包领域，长期为企业提供合规咨询和实务方案。

请基于以下素材，撰写一篇高质量的微信公众号文章。

【写作要求】
1. 标题：专业、有信息量，体现政策要点或实务价值，15-28字。不要用"震惊""必看"等标题党词汇。
2. 摘要：60字以内，点明文章核心结论或读者能获得的实务价值。
3. 正文：1500-2200字，用 HTML 标签格式化，要求：
   - <h3> 用于小标题（每部分一个）
   - <p> 用于段落，每段聚焦一个要点
   - <blockquote> 用于引用政策原文、法条编号、数据
   - <strong> 用于加粗关键术语、数字、风险点
   - 适当使用 <ul><li> 列举要点
4. 文章结构（严格按此顺序）：
   - 【背景导读】用1-2段交代政策出台背景或行业现状，引出本文主题
   - 【政策要点解读】逐条解读核心内容，引用具体条文或数据，避免笼统
   - 【企业影响分析】分析对不同类型企业（制造业/服务业/平台企业）的具体影响
   - 【合规操作指引】给出3-5条可落地的操作建议，每条要具体到操作层面
   - 【风险提示】点明2-3个常见误区或风险点，用 <strong> 加粗
   - 【结语】简短收尾，引导关注和咨询
5. 专业要求：
   - 必须引用具体政策名称、文号、生效时间（从素材中提取，无则合理标注）
   - 涉及税务处理要明确税种、税率、计算逻辑
   - 涉及用工要区分劳动关系/劳务关系/非全日制/平台用工等
   - 使用专业术语但配通俗解释，面向 HR 负责人和财务主管
6. 禁止：
   - 不要写"本文将为您解读"这类套话
   - 不要重复素材原文，要有分析和增量信息
   - 不要使用空泛的"非常重要""值得关注"等无信息量表述

【素材信息】
素材标题：{source['title']}
素材正文：{source_content}
素材来源：{source['url']}

请严格输出以下 JSON 格式（不要加 markdown 代码块标记，不要在 JSON 外加任何文字）：
{{"title":"文章标题","digest":"摘要","content":"<h3>背景导读</h3><p>...</p><h3>政策要点解读</h3><p>...</p>...","source_url":"{source['url']}"}}"""

    body = {
        "model": model,
        "messages": [
            {"role": "system", "content": "你是资深财税专家，输出必须专业、准确、有实务价值。严格遵守用户要求的JSON格式输出，不要在JSON外加任何文字。"},
            {"role": "user", "content": prompt}
        ],
        "temperature": 0.3,
        "max_tokens": 6000,
    }

    url = f"{base_url}/chat/completions"
    status, resp_text = http_post(url, json_data=body, timeout=120, headers={"Authorization": f"Bearer {api_key}"})

    if status != 200:
        raise Exception(f"DeepSeek API 返回 {status}: {resp_text[:300]}")

    data = json.loads(resp_text)
    result = data["choices"][0]["message"]["content"].strip()

    # 清理 markdown 代码块标记
    if result.startswith("```"):
        lines = result.split("\n")
        result = "\n".join(lines[1:-1] if lines[-1].startswith("```") else lines[1:])

    try:
        article = json.loads(result)
        article.setdefault("source_url", source["url"])
        return article
    except json.JSONDecodeError:
        return {
            "title": source["title"],
            "digest": source.get("snippet", "")[:64],
            "content": f"<p>{result}</p>",
            "source_url": source["url"],
        }


def generate_image(prompt, width=900, height=383):
    """用 Pollinations.ai 生成图片，返回 bytes。用 flux 模型提升质量。"""
    encoded = urllib.parse.quote(prompt)
    # flux 模型质量更高；加 seed 保证一致性
    url = f"https://image.pollinations.ai/prompt/{encoded}?width={width}&height={height}&nologo=true&model=flux&seed=42"
    for attempt in range(3):
        status, img_bytes = http_get_bytes(url, timeout=120)
        if status == 200 and len(img_bytes) > 10000:
            return img_bytes
        print(f"  [图片生成重试 {attempt+1}] status={status} size={len(img_bytes)}")
        time.sleep(3)
    print("  [图片生成失败，跳过]")
    return b""


def generate_cover(title):
    """生成高质量封面图（900x500，公众号黄金比例）"""
    # 从标题提取主题词，让封面更贴合内容
    keywords = title[:30] if title else "灵活用工 财税政策"
    return generate_image(
        f"Editorial cover illustration for a Chinese business finance article about: {keywords}. "
        "Style: premium financial magazine cover, sophisticated isometric 3D illustration, "
        "deep navy blue and gold color scheme, abstract geometric shapes representing "
        "documents, handshake, growth chart, employment network. "
        "Clean composition, lots of negative space, professional corporate aesthetic, "
        "no text, no watermark, high quality, 16:9",
        900, 500
    )


def generate_inline_image(topic="flexible employment"):
    """生成高质量内文配图（1080x720）"""
    return generate_image(
        f"Professional editorial illustration about {topic} in China. "
        "Style: modern flat design with subtle gradients, infographic style, "
        "showing business professionals, documents, compliance checklist, "
        "digital platform interface elements. "
        "Color palette: deep blue, teal, white, with orange accents. "
        "Clean layout, suitable for business article, no text, high quality, 3:2",
        1080, 720
    )


# ============================================================
# 企业微信群机器人推送
# ============================================================
def get_webhook():
    return os.environ.get("WECOM_WEBHOOK", "")


def send_markdown(content):
    """发送 markdown 消息"""
    webhook = get_webhook()
    if not webhook:
        raise Exception("WECOM_WEBHOOK 环境变量未配置")

    MAX_BYTES = 4000
    content_bytes = content.encode("utf-8")
    if len(content_bytes) <= MAX_BYTES:
        return _webhook_send({"msgtype": "markdown", "markdown": {"content": content}})

    # 超长分段
    parts = _split_text(content, MAX_BYTES)
    for i, part in enumerate(parts):
        header = f"**（第 {i+1}/{len(parts)} 部分）**\n\n" if len(parts) > 1 else ""
        _webhook_send({"msgtype": "markdown", "markdown": {"content": header + part}})
        if i < len(parts) - 1:
            time.sleep(0.5)
    return True


def _split_text(content, max_bytes):
    paragraphs = content.split("\n\n")
    parts = []
    current = ""
    for para in paragraphs:
        candidate = (current + "\n\n" + para) if current else para
        if len(candidate.encode("utf-8")) > max_bytes:
            if current:
                parts.append(current)
            current = para
        else:
            current = candidate
    if current:
        parts.append(current)
    return parts


def send_image(img_bytes):
    """发送图片"""
    if not img_bytes:
        return False
    webhook = get_webhook()
    b64 = base64.b64encode(img_bytes).decode("utf-8")
    md5 = hashlib.md5(img_bytes).hexdigest()
    return _webhook_send({"msgtype": "image", "image": {"base64": b64, "md5": md5}})


def send_text(content):
    """发送纯文本"""
    return _webhook_send({"msgtype": "text", "text": {"content": content}})


def _webhook_send(body):
    webhook = get_webhook()
    status, resp = http_post(webhook, json_data=body, timeout=30)
    if status != 200:
        raise Exception(f"群机器人请求失败 {status}: {resp[:200]}")
    data = json.loads(resp)
    if data.get("errcode") != 0:
        raise Exception(f"群机器人发送失败: {data}")
    return True


def send_article(title, digest, markdown_content, cover_bytes, inline_imgs=None, source_url=""):
    """发送完整文章"""
    # 1. 封面图
    if cover_bytes:
        print("    发送封面图...")
        send_image(cover_bytes)
        time.sleep(0.3)

    # 2. 正文 markdown
    print("    发送正文...")
    parts = [f"# {title}\n", f"> {digest}\n", markdown_content]
    if source_url:
        parts.append(f"\n**原文链接：** [点击查看]({source_url})")
    parts.append("\n---\n*由自动推送系统生成 · 每日 07:00*")
    full_md = "\n\n".join(parts)
    send_markdown(full_md)

    # 3. 内文配图
    if inline_imgs:
        for i, img in enumerate(inline_imgs):
            if img:
                time.sleep(0.3)
                print(f"    发送内文配图 {i+1}...")
                send_image(img)
    return True


# ============================================================
# HTML 转 Markdown
# ============================================================
def html_to_markdown(html):
    text = re.sub(r'<h3[^>]*>(.*?)</h3>', r'### \1', html, flags=re.DOTALL)
    text = re.sub(r'<h2[^>]*>(.*?)</h2>', r'## \1', text, flags=re.DOTALL)
    text = re.sub(r'<blockquote[^>]*>(.*?)</blockquote>', lambda m: '\n'.join('> ' + l for l in m.group(1).strip().split('\n')), text, flags=re.DOTALL)
    text = re.sub(r'<(?:strong|b)[^>]*>(.*?)</(?:strong|b)>', r'**\1**', text, flags=re.DOTALL)
    text = re.sub(r'<p[^>]*>(.*?)</p>', r'\1\n\n', text, flags=re.DOTALL)
    text = re.sub(r'<li[^>]*>(.*?)</li>', r'- \1\n', text, flags=re.DOTALL)
    text = re.sub(r'</?(?:ul|ol)[^>]*>', '', text)
    text = re.sub(r'<a[^>]*href="([^"]*)"[^>]*>(.*?)</a>', r'[\2](\1)', text, flags=re.DOTALL)
    text = re.sub(r'<br\s*/?>', '\n', text)
    text = re.sub(r'<[^>]+>', '', text)
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text.strip()


# ============================================================
# 主流程
# ============================================================
def notify_wecom(message, is_error=False):
    try:
        prefix = "⚠️ 异常告警" if is_error else "📢 推送通知"
        send_text(f"{prefix}\n\n{message}")
    except Exception as e:
        print(f"[群机器人通知失败] {e}")


def main():
    start_time = datetime.now()
    print(f"[{start_time.strftime('%Y-%m-%d %H:%M:%S')}] 开始执行每日财税资讯推送")
    print("=" * 60)

    # 出口 IP
    try:
        status, ip = http_get("https://api.ipify.org", timeout=5)
        print(f"[出口 IP] {ip}")
    except Exception:
        print("[出口 IP] 获取失败")
    print("=" * 60)

    # ===== 第 1 步：采集 =====
    print(">>> [1/4] 采集资讯...")
    articles = collect()
    print(f"    采集到 {len(articles)} 条资讯")

    if not articles:
        msg = "今日未采集到资讯，请检查 DuckDuckGo 搜索是否正常。"
        print(f"[警告] {msg}")
        notify_wecom(msg, is_error=True)
        return

    # ===== 第 2 步：AI 生成 =====
    print(">>> [2/4] 挑选 Top1 + AI 生成文章...")
    top1 = articles[0]
    print(f"    选中: {top1['title']}")
    print(f"    来源: {top1['url']}")
    print(f"    评分: {top1['score']:.1f}")

    article = generate_article(top1)
    print(f"    标题: {article.get('title', '未知')}")
    print(f"    摘要: {article.get('digest', '')[:50]}...")

    print("    生成封面图...")
    cover_bytes = generate_cover(article.get("title", ""))
    print("    生成内文配图...")
    inline1 = generate_inline_image("flexible employment HR outsourcing business")
    inline2 = generate_inline_image("tax compliance employment policy")

    markdown_content = html_to_markdown(article.get("content", ""))

    # ===== 第 3 步：推送 =====
    print(">>> [3/4] 推送企业微信群机器人...")
    try:
        send_article(
            title=article.get("title", "今日财税资讯"),
            digest=article.get("digest", ""),
            markdown_content=markdown_content,
            cover_bytes=cover_bytes,
            inline_imgs=[inline1, inline2],
            source_url=article.get("source_url", top1["url"]),
        )
        print("    群机器人推送成功！")
    except Exception as e:
        error_detail = traceback.format_exc()[:800]
        error_msg = f"群机器人推送失败\n\n错误: {e}\n\n文章标题: {article.get('title', '未知')}\n\n{error_detail}"
        print(f"[错误] {error_msg}")
        try:
            notify_wecom(error_msg, is_error=True)
        except Exception:
            pass
        return

    # ===== 第 4 步：完成 =====
    print(">>> [4/4] 完成")
    elapsed = (datetime.now() - start_time).total_seconds()
    print("=" * 60)
    print(f"[完成] 耗时 {elapsed:.0f} 秒")
    print(f"  文章标题: {article.get('title', '未知')}")


# ============================================================
# 入口（GitHub Actions 直接运行，SCF 调 main_handler）
# ============================================================
def main_handler(event=None, context=None):
    print("=" * 60)
    print(f"[触发] event={event}")
    print("=" * 60)
    try:
        main()
        return {"statusCode": 200, "message": "推送完成"}
    except SystemExit:
        return {"statusCode": 500, "message": "流程异常退出"}
    except Exception as e:
        error_msg = f"执行异常: {e}\n{traceback.format_exc()[:500]}"
        print(f"[严重错误] {error_msg}")
        return {"statusCode": 500, "message": error_msg}


if __name__ == "__main__":
    main()
