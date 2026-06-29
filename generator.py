#!/usr/bin/env python3
"""
内容生成模块
- LLM 生成公众号正文（DeepSeek API，兼容 OpenAI 格式）
- Pollinations.ai 生成封面图 + 内文配图（完全免费，无需 key）
- Pillow 后备：图片生成失败时生成简洁标题图
"""
import os
import json
import requests
from openai import OpenAI
from io import BytesIO
from PIL import Image, ImageDraw, ImageFont
import textwrap

# 初始化 LLM 客户端（DeepSeek 兼容 OpenAI 格式）
_client = None


def _get_client():
    global _client
    if _client is None:
        _client = OpenAI(
            api_key=os.environ.get("LLM_API_KEY", ""),
            base_url=os.environ.get("LLM_BASE_URL", "https://api.deepseek.com/v1"),
        )
    return _client


def generate_article(source):
    """用 LLM 生成公众号文章，返回 dict(title, digest, content, source_url)"""
    source_content = source.get("content", "") or source.get("snippet", "")
    source_content = source_content[:3000]

    prompt = f"""你是一位资深财税领域内容创作者，专注于灵活用工结算和人力资源外包方向。
请基于以下素材写一篇微信公众号文章。

要求：
1. 标题：吸引人但不标题党，15-25字，体现财税/用工主题
2. 摘要：50字以内，概括核心价值
3. 正文：1000-1500字，用 HTML 标签格式
   - <h3> 小标题
   - <p> 段落
   - <blockquote> 引用政策原文或重点
   - <strong> 关键词加粗
4. 结构：政策解读 → 企业影响 → 合规建议 → 实务指引
5. 语气：专业但有可读性，面向 HR 和财务从业者
6. 结尾：引导关注和咨询灵活用工结算服务

素材标题：{source['title']}
素材内容：{source_content}
素材来源：{source['url']}

请严格输出以下 JSON 格式（不要加 markdown 代码块标记）：
{{"title":"文章标题","digest":"摘要内容","content":"<h3>小标题</h3><p>正文段落</p>...","source_url":"{source['url']}"}}"""

    client = _get_client()
    model = os.environ.get("LLM_MODEL", "deepseek-chat")

    response = client.chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": prompt}],
        temperature=0.7,
        max_tokens=4000,
    )

    result = response.choices[0].message.content.strip()

    # 清理可能存在的 markdown 代码块标记
    if result.startswith("```"):
        lines = result.split("\n")
        result = "\n".join(lines[1:-1] if lines[-1].startswith("```") else lines[1:])

    try:
        article = json.loads(result)
        article.setdefault("source_url", source["url"])
        return article
    except json.JSONDecodeError:
        print("  [LLM 返回非 JSON，使用原始文本]")
        return {
            "title": source["title"],
            "digest": source.get("snippet", "")[:64],
            "content": f"<p>{result}</p>",
            "source_url": source["url"],
        }


def generate_image(prompt, width=900, height=383):
    """用 Pollinations.ai 生成图片，返回 BytesIO"""
    encoded = requests.utils.quote(prompt)
    url = f"https://image.pollinations.ai/prompt/{encoded}?width={width}&height={height}&nologo=true"

    for attempt in range(2):
        try:
            resp = requests.get(url, timeout=90)
            resp.raise_for_status()
            if len(resp.content) > 5000:
                return BytesIO(resp.content)
        except Exception as e:
            print(f"  [图片生成重试 {attempt+1}] {e}")
    print("  [图片生成失败，使用后备方案]")
    return _fallback_image(prompt, width, height)


def _fallback_image(text, width=900, height=383):
    """Pillow 后备：生成简洁的纯色标题图"""
    img = Image.new("RGB", (width, height), color=(31, 78, 121))
    draw = ImageDraw.Draw(img)

    font_large = None
    font_small = None
    for font_name in ["DejaVuSans-Bold.ttf", "Arial-Bold.ttf", "LiberationSans-Bold.ttf"]:
        try:
            font_large = ImageFont.truetype(font_name, 32)
            font_small = ImageFont.truetype(font_name, 16)
            break
        except Exception:
            continue
    if not font_large:
        font_large = ImageFont.load_default()
        font_small = ImageFont.load_default()

    lines = textwrap.wrap("Daily Finance News", width=25)
    y = height // 2 - len(lines) * 18
    for line in lines:
        bbox = draw.textbbox((0, 0), line, font=font_large)
        x = (width - bbox[2]) // 2
        draw.text((x, y), line, fill="white", font=font_large)
        y += 36

    buf = BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    return buf


def generate_cover(title):
    """生成封面图（900x383，公众号推荐尺寸）"""
    prompt = (
        "Professional business illustration about Chinese finance, taxation, "
        "flexible employment and HR outsourcing, clean modern flat design, "
        "blue and white corporate tones, no text, 16:9 aspect ratio"
    )
    return generate_image(prompt, 900, 383)


def generate_inline_image(topic="flexible employment"):
    """生成内文配图（1080x720）"""
    prompt = (
        f"Professional illustration about {topic}, business meeting and documents, "
        "clean modern style, blue tones, no text"
    )
    return generate_image(prompt, 1080, 720)


if __name__ == "__main__":
    # 测试（需要设置 LLM_API_KEY 环境变量）
    test_source = {
        "title": "测试标题",
        "content": "测试内容",
        "url": "https://example.com",
        "snippet": "测试摘要",
    }
    if os.environ.get("LLM_API_KEY"):
        article = generate_article(test_source)
        print(json.dumps(article, ensure_ascii=False, indent=2))
    else:
        print("请设置 LLM_API_KEY 环境变量后测试")
