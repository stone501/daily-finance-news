# 每日财税资讯自动推送

每天 07:00 自动采集灵活用工结算 / 人力资源外包领域热点资讯，AI 生成公众号文章，推送到公众号草稿箱和企业微信。云端运行，设备关机也照跑。

## 配置步骤（一次性，约 20 分钟）

### 1. 配置 GitHub Secrets

进入仓库 → **Settings** → **Secrets and variables** → **Actions** → **New repository secret**，依次添加：

| Secret 名称 | 值 | 说明 |
|---|---|---|
| `MP_APPID` | wxa5f0768ac93bae4d | 公众号 AppID |
| `MP_SECRET` | 重置后的 AppSecret | 公众号后台重置后填入 |
| `WECOM_CORPID` | 企业的 CorpID | 企业微信管理后台 → 我的企业 |
| `WECOM_AGENTID` | 应用 AgentId | 企业微信自建应用 |
| `WECOM_SECRET` | 应用 Secret | 同上 |
| `LLM_API_KEY` | DeepSeek API Key | 见下方说明 |
| `LLM_BASE_URL` | `https://api.deepseek.com/v1` | DeepSeek API 地址 |
| `LLM_MODEL` | `deepseek-chat` | 模型名 |

### 2. 获取 DeepSeek API Key（免费）

1. 访问 https://platform.deepseek.com/
2. 手机号注册登录
3. 左侧菜单 → API Keys → 创建 API Key
4. 复制 Key，填入 GitHub Secret `LLM_API_KEY`

注册即送 500 万 token 免费额度，每天一篇约 2000 token，够用 2-3 个月。

### 3. 企业微信自建应用

1. 登录 https://work.weixin.qq.com/wework_admin/ 企业微信管理后台
2. 应用管理 → 自建 → 创建应用
3. 填写应用名称（如"财税资讯推送"），上传 logo，可见范围选自己
4. 创建后获取：
   - **AgentId** → 填 `WECOM_AGENTID`
   - **Secret** → 填 `WECOM_SECRET`
5. 我的企业 → 企业信息 → **企业ID** → 填 `WECOM_CORPID`

### 4. 公众号 IP 白名单（按需）

公众号后台 → 设置与开发 → 基本配置 → IP 白名单。

第一次运行时，GitHub Actions 日志会打印出口 IP。如果公众号 API 报错 "40164"，把日志里的 IP 加入白名单后重试。

部分个人订阅号不强制要求白名单，可以先不加直接试。

## 运行方式

### 自动运行

配置完成后，每天北京时间 07:00 自动触发。

### 手动触发（测试用）

仓库 → **Actions** → 左侧选"每日财税资讯推送" → 右侧 **Run workflow** → 点绿色按钮。

## 查看运行结果

- **运行日志**：仓库 → Actions → 点击对应运行记录
- **企业微信**：收到资讯摘要卡片（成功）或告警文本（失败）
- **公众号草稿箱**：登录 mp.weixin.qq.com → 草稿箱 → 审核后发布

## 文件说明

```
├── .github/workflows/daily.yml  # GitHub Actions 定时工作流
├── main.py                       # 主流程（采集→生成→推送）
├── collectors.py                 # DuckDuckGo 搜索 + 正文抓取
├── generator.py                  # LLM 生成正文 + 图片生成
├── wechat_mp.py                  # 公众号草稿箱 API
├── wecom.py                      # 企业微信推送
├── template.py                   # 文章 HTML 排版模板
├── requirements.txt              # Python 依赖
└── README.md                     # 本文件
```

## 费用

- GitHub Actions：公开仓库免费，无限分钟
- DeepSeek API：注册送 500 万 token，够用数月
- DuckDuckGo 搜索：免费
- Pollinations.ai 图片生成：免费
- 公众号 / 企业微信 API：免费

**总费用：0 元**
