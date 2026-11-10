# 📡 Paper Radar

每天自动抓取 arXiv、CVPR / ICLR / ICML / CoRL 等来源中与 **扩散模型 / 自动驾驶 / 强化学习 / 世界模型 / 机器人** 相关的新论文，
打分排序、翻译成中文、生成一个静态网站，并私聊推送到飞书。

- 零服务器：GitHub Actions 定时跑，GitHub Pages 托管，完全免费
- 零数据库：每天的论文存成 JSON，随仓库一起版本化
- 断网也能看：页面数据内联，单文件即可浏览

```
arXiv API ──► 方向匹配 ──► 重要度打分 ──► 中文翻译 ──► 静态站 ──► Pages
                                                  └──► RSS / 邮件 / 微信
```

---

## 一、5 分钟上线

### 1. 建仓库
在 GitHub 新建一个仓库（例如 `paper-radar`），把本项目文件传上去：

```bash
git init && git add . && git commit -m "init"
git branch -M main
git remote add origin git@github.com:<你的用户名>/paper-radar.git
git push -u origin main
```

### 2. 打开 Pages
仓库 → **Settings → Pages → Build and deployment → Source 选 `GitHub Actions`**。

> 这一步必须做，否则 `deploy-pages` 会报错。

### 3. 跑第一次
仓库 → **Actions → Daily Paper Radar → Run workflow**。
约 3~5 分钟后，你的站点就在 `https://<用户名>.github.io/paper-radar/`。

GitHub Actions 在北京时间每天 10:00 做一次兜底抓取。若需要每天 08:30 准点收到飞书，
使用仓库根目录的本地定时任务（04:30 准备，08:30 只发送），这样耗时较长的两篇全文精读不会挤占发送时间。

```cron
30 4 * * * /path/to/paper-radar/run-daily.sh --prepare
0 6 * * *  /path/to/paper-radar/run-daily.sh --prepare
30 8 * * * /path/to/paper-radar/run-daily.sh --send
```

第一次 `--prepare` 成功后，06:00 的重试会自动跳过；失败时则用于补跑。

### 4. 填站点地址（重要）
**Settings → Secrets and variables → Actions → Variables → New variable**

| Name | Value |
|---|---|
| `SITE_BASE_URL` | `https://<用户名>.github.io/paper-radar` |

RSS 和推送消息里的「查看完整列表」链接靠它。

---

## 二、可选：开启中文翻译

不配置也能用（页面显示英文摘要），配了就变中文。

**Settings → Secrets and variables → Actions → Secrets → New secret**

| Name | 说明 |
|---|---|
| `OPENAI_API_KEY` | 任意 OpenAI 兼容接口的 Key |

再在 **Variables** 里加（不填则用默认）：

| Name | 默认值 | 可选值示例 |
|---|---|---|
| `OPENAI_BASE_URL` | `https://api.openai.com/v1` | `https://api.deepseek.com/v1`、`https://dashscope.aliyuncs.com/compatible-mode/v1` |
| `OPENAI_MODEL` | `gpt-4o-mini` | `deepseek-chat`、`qwen-plus` |

**成本**：默认每天翻译 `max_papers: 90` 篇（优先翻精选）。用 `gpt-4o-mini` 约 **$0.01~0.03/天**，
用 DeepSeek 更便宜。翻译结果缓存在 `data/cache/translations.json`，同一篇论文只翻一次，
所以长期成本几乎不增长——`data/` 目录会被自动提交回仓库，缓存才留得住。

想更省钱：把 `config.yaml` 里的 `translate.max_papers` 调成 `30`（只翻精选）。

---

## 三、可选：每日推送

在 `config.yaml` 里把对应开关改成 `enabled: true`，再配 Secrets：

| 渠道 | 开关 | Secret |
|---|---|---|
| 邮件 | `notify.email.enabled` + 填 `notify.email.to` | `SMTP_HOST` `SMTP_PORT` `SMTP_USER` `SMTP_PASS` |
| 微信（Server酱） | `notify.serverchan.enabled` | `SERVERCHAN_KEY`（[sct.ftqq.com](https://sct.ftqq.com) 免费申请） |
| 企业微信群 | `notify.wecom.enabled` | `WECOM_WEBHOOK`（群设置 → 群机器人 → 添加） |
| 飞书私聊 | `notify.feishu.enabled` | 本机 `~/.config/paper-radar/feishu.env` 中的 `FEISHU_APP_ID`、`FEISHU_APP_SECRET`、`FEISHU_RECEIVE_EMAILS` |

邮件用 QQ 邮箱示例：`SMTP_HOST=smtp.qq.com`、`SMTP_PORT=465`、`SMTP_USER=你的QQ邮箱`、
`SMTP_PASS=授权码`（不是登录密码）。

**RSS 永远是免费的**：站点根目录的 `feed.xml`，直接丢进任何阅读器即可。

飞书接收者按邮箱解析为 `open_id`，只发个人私聊，不会发到群：

```bash
FEISHU_RECEIVE_EMAILS="xuzhouliang@qianli-drive.com"
```

---

## 四、定制方向与关键词

全部在 `config.yaml`，改完 push 就会重建。

```yaml
topics:
  - id: diffusion          # 唯一标识，会出现在 URL 和标签里
    name: 扩散 / 生成模型    # 页面上显示的名字
    color: "#7c5cff"       # 圆点与标签颜色
    keywords:              # 命中标题算 3 倍权重，命中摘要算 1 倍
      - diffusion model
      - flow matching
```

**关键词写法的坑**：匹配用的是「词边界正则」，所以 `diffusion model` 不会命中 `diffusion models`，
需要的话两个都写；反之 `ppo` 不会误命中 `support`。多词短语直接写，大小写无所谓。

想加新方向（比如 3D 重建 / 多模态大模型），照着复制一段就行，其余全自动。

### 打分规则

每篇论文的「重要度」由 `boost.weights` 决定，最后归一化成 0–100：

| 因素 | 默认权重 | 说明 |
|---|---|---|
| 方向关键词命中标题 | 7 | 最多算 2 次 |
| 方向关键词命中摘要 | 1.6 | 最多算 5 次 |
| 知名机构 | 5 | DeepMind、清华、上海AI Lab… 见 `boost.labs` |
| 已被顶会接收 | 9 | 从 `comment` 里识别 CVPR/NeurIPS/CoRL… |
| 有开源代码 | 7 | 摘要或注释里的 GitHub 链接 |
| 当天提交 | 3 | 为了避免时差，默认回看 2 天 |

觉得「精选」不准，就调这几个数字；想收紧收录量，把 `site.max_papers` 调小。

---

## 五、本地调试

```bash
pip install -r requirements.txt

python run.py                  # 完整跑一遍（抓取+翻译+生成）
python run.py --no-translate   # 快速跑，不翻译
python run.py --offline        # 不抓取，用已有数据重建站点（改样式时用这个）
python run.py --days 7         # 回看 7 天
```

生成结果在 `site/`，直接用浏览器打开 `site/index.html` 就能看（数据内联，不需要起服务器）。

```bash
python -m http.server -d site 8000   # 需要测试相对路径时
```

---

## 六、目录结构

```
config.yaml                 # 全部配置都在这（方向、关键词、权重、推送）
run.py                      # 主流程
psradar/
  arxiv_client.py           # arXiv API 抓取 + LaTeX/URL 清洗
  ranker.py                 # 方向匹配 + 重要度打分
  translator.py             # 中文翻译（带缓存）
  renderer.py               # 生成 HTML / JSON / RSS
  notify.py                 # 邮件 / Server酱 / 企业微信
assets/
  style.css  app.js         # 前端（构建时内联进页面）
templates/page.html         # 页面骨架
data/
  history/YYYY-MM-DD.json   # 每天的论文数据（自动提交）
  cache/translations.json   # 翻译缓存
  days.json                 # 归档索引
site/                       # 生成产物（gitignore，由 CI 产出）
```

## 七、常见问题

**Q: 想改成早上 7 点更新？**
改 `.github/workflows/daily.yml` 里的 cron，注意是 **UTC**：`0 23 * * *` = 北京 7:00。
GitHub 定时任务在高峰期可能延迟几分钟到半小时，属正常。

**Q: 抓取失败了？**
arXiv API 对频率敏感，`fetch.request_interval` 默认 3.2 秒（官方要求 ≥3 秒），别调小。
脚本内置重试，偶发失败重跑一次即可。

**Q: 页面太大？**
单日 150~300 篇约 500KB，gzip 后 ~120KB。可以调小 `site.max_papers`，
或在 `renderer.py` 的 `_slim()` 里截断 `abstract`。

**Q: 能换成别的数据源吗？**
可以。只要你的 `papers` 列表里每篇都有 `id/title/abstract/authors/published/abs_url/pdf_url`
这几个字段，后面的打分、翻译、渲染全都能复用（比如接 bioRxiv、OpenReview）。
