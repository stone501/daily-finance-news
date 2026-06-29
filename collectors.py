#!/usr/bin/env python3
"""
数据采集模块
- DuckDuckGo 搜索（免费，无需 API key）
- 正文抓取（trafilatura 提取正文）
- 去重 + 热度评分
"""
import requests
from bs4 import BeautifulSoup
import trafilatura
from urllib.parse import parse_qs, urlparse
import time

# 搜索关键词组（覆盖灵活用工 + 人力外包 + 财税政策）
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

# 权威来源域名权重（用于热度评分）
AUTHORITATIVE_SOURCES = {
    "chinatax.gov.cn": 1.0,
    "mohrss.gov.cn": 1.0,
    "gov.cn": 0.9,
    "npc.gov.cn": 0.9,
    "12366": 0.8,
    "yicai.com": 0.7,
    "caixin.com": 0.7,
    "21jingji.com": 0.7,
    "cs.com.cn": 0.7,
    "thepaper.cn": 0.6,
    "clsn": 0.6,
    "shebao": 0.6,
}

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}


def search_ddg(query, max_results=5):
    """DuckDuckGo HTML 版搜索"""
    url = "https://html.duckduckgo.com/html/"
    data = {"q": query, "kl": "cn-zh"}
    results = []
    for attempt in range(3):
        try:
            resp = requests.post(url, data=data, headers=HEADERS, timeout=15)
            resp.raise_for_status()
            soup = BeautifulSoup(resp.text, "html.parser")
            for item in soup.select(".result"):
                title_elem = item.select_one(".result__a")
                snippet_elem = item.select_one(".result__snippet")
                if not title_elem:
                    continue
                raw_url = title_elem.get("href", "")
                real_url = raw_url
                if "uddg=" in raw_url:
                    parsed = urlparse(raw_url)
                    params = parse_qs(parsed.query)
                    real_url = params.get("uddg", [None])[0]
                if not real_url:
                    continue
                title = title_elem.get_text(strip=True)
                snippet = snippet_elem.get_text(strip=True) if snippet_elem else ""
                results.append({"title": title, "url": real_url, "snippet": snippet})
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
        try:
            resp = requests.get(url, timeout=15, headers=HEADERS, allow_redirects=True)
            resp.raise_for_status()
            content = trafilatura.extract(resp.text)
            if content and len(content) > 100:
                return content
        except Exception as e:
            print(f"  [抓取重试 {attempt+1}] {url}: {e}")
            time.sleep(2)
    return ""


def score_article(article):
    """热度评分：来源权威度 + 信息丰富度 + 内容长度"""
    score = 0.0
    url = article.get("url", "").lower()
    for domain, weight in AUTHORITATIVE_SOURCES.items():
        if domain in url:
            score += weight * 30
            break
    else:
        score += 10
    snippet_len = len(article.get("snippet", ""))
    score += min(snippet_len / 10, 20)
    content_len = len(article.get("content", ""))
    score += min(content_len / 100, 30)
    if article.get("content"):
        score += 10
    return score


def collect():
    """主采集函数：搜索 → 抓取 → 去重 → 评分 → 排序"""
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

    # 对未抓取正文的也评分
    for article in all_results[15:]:
        article["content"] = ""
        article["score"] = score_article(article)

    all_results.sort(key=lambda x: x["score"], reverse=True)
    print(f"  评分排序完成，Top1: {all_results[0]['title'][:50]}")
    return all_results


if __name__ == "__main__":
    # 测试
    results = collect()
    for r in results[:5]:
        print(f"  [{r['score']:.1f}] {r['title']}")
        print(f"       {r['url']}")
