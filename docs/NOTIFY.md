# 推送与数据源配置

## 1. RSS 是输入源，不是推送渠道

RSS 只负责“从哪里找论文”。在 `config.yaml` 的 `sources.extra` 里增加：

```yaml
sources:
  extra:
    - id: my-feed
      name: 我的会议源
      rss: "https://example.com/feed.xml"
      enabled: true
```

构建时会把这些条目与 arXiv 合并，再走同一套打分、摘要中文化和精读流程。

注意：
- OpenReview 和知乎的公开页面有反爬挑战，直接抓取经常返回 403。
- 想稳定接入知乎/会议，推荐使用 RSSHub 生成 RSS，再把 RSSHub 地址填到 `rss`。
- 会议没有统一 RSS 时，最稳的是会议官网的 accepted papers 页面或 OpenReview 导出。

## 2. 微信推送

微信没有像飞书应用那样的官方“机器人私聊”接口。可选方案：

### 方案 A：ServerChan（个人微信，最省事）

1. 打开 `https://sct.ftqq.com/`，微信扫码登录。
2. 创建一个 SendKey。
3. 设置：

```bash
export SERVERCHAN_KEY=你的SendKey
```

4. 在 `config.yaml` 打开：

```yaml
notify:
  serverchan:
    enabled: true
```

ServerChan 会把消息推送到你的微信服务号会话。

### 方案 B：企业微信群机器人

1. 在企业微信群里添加“群机器人”，复制 webhook。
2. 设置 `WECOM_WEBHOOK`。
3. 打开 `notify.wecom.enabled: true`。

这种方式发到群，不是个人私聊。

## 3. 给别人的飞书邮箱也推送

同一个飞书应用可以给多人私聊，只要对方在同一个企业内。

设置多个邮箱：

```bash
export FEISHU_RECEIVE_EMAILS="xuzhouliang@qianli-drive.com,other@qianli-drive.com"
```

也可以追加已知 `open_id`：

```bash
export FEISHU_RECEIVE_IDS="ou_xxx,ou_yyy"
```

应用需要具备：
- `im:message:send_as_bot`
- `contact:user.id:readonly`
