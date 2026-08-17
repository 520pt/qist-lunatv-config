# qist → LunaTV / MoonTVPlus config

自动把 qist 的 TVBox `jsm.json` 转成 LunaTV / MoonTVPlus 可导入的 Base58 配置，并通过 GitHub Actions 定时更新。

## 链接

### 1. 推荐可用版（CMS 直连源）

```text
https://raw.githubusercontent.com/520pt/qist-lunatv-config/main/LunaTV-config.txt
```

这个版本只包含 LunaTV / MoonTVPlus 原生支持的标准苹果 CMS V10 `api.php/provide/vod` 源，当前 13 个。

### 2. 全量保留版（包含 qist 全部 sites）

```text
https://raw.githubusercontent.com/520pt/qist-lunatv-config/main/LunaTV-config-all.txt
```

这个版本把 qist 的 163 个 `sites` 全部写进 `api_site` 结构，并附带 3 个直播源 `lives`。

注意：LunaTV / MoonTVPlus 的订阅配置原生只支持标准苹果 CMS V10 API。TVBox 里的 `csp_*`、`drpy`、本地 jar/js/py、Bili/网盘/体育/听书等条目没有 TVBox 运行环境，虽然全量版会保留名字和原始字段，但不保证都能在 LunaTV / MoonTVPlus 中搜索播放。

## 文件说明

- `LunaTV-config.txt`：推荐可用版，Base58 编码，给 LunaTV / MoonTVPlus 使用。
- `LunaTV-config.json`：推荐可用版明文检查文件。
- `LunaTV-config-all.txt`：全量保留版，Base58 编码。
- `LunaTV-config-all.json`：全量保留版明文检查文件。
- `tvbox-jsm.json`：定时同步到的 qist 原始配置快照。
- `scripts/update_lunatv_config.py`：转换脚本。

## 更新机制

GitHub Actions 每 6 小时自动执行一次，也可以手动触发：

- 拉取 qist 上游：`https://v6.gh-proxy.org/https://raw.githubusercontent.com/qist/tvbox/master/jsm.json`
- 失败时回退官方 raw：`https://raw.githubusercontent.com/qist/tvbox/master/jsm.json`
- 重新生成两个 LunaTV 配置
- 有变化就自动提交到 `main`
