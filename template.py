#!/usr/bin/env python3
"""
公众号文章 HTML 排版模板
专业财税风格：蓝色主色调，清晰段落，引用块，引导关注
"""

ARTICLE_TEMPLATE = """<section style="padding: 8px 4px; font-family: -apple-system, BlinkMacSystemFont, 'Helvetica Neue', 'PingFang SC', 'Microsoft YaHei', sans-serif; font-size: 16px; line-height: 1.85; color: #333333;">

<p style="color: #888; font-size: 14px; line-height: 1.6; margin-bottom: 24px; padding-left: 12px; border-left: 3px solid #1F4E79;">{digest}</p>

{content}

<section style="margin-top: 32px; padding: 16px 20px; background: #F0F7FF; border-radius: 8px; border-left: 4px solid #1F4E79;">
<p style="margin: 0; font-size: 14px; line-height: 1.7; color: #444;">
<strong style="color: #1F4E79;">关于我们</strong><br/>
专注于为一般纳税人企业提供合规的灵活用工结算解决方案。如需灵活用工结算或人力资源外包咨询，欢迎联系交流。
</p>
</section>

<p style="font-size: 12px; color: #AAA; margin-top: 20px; line-height: 1.5;">
原文来源：<a href="{source_url}" style="color: #576B95; text-decoration: none;">{source_url}</a><br/>
本文由系统自动采集生成，内容仅供参考，不构成专业建议。
</p>

</section>"""
