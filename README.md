# qist → LunaTV / MoonTVPlus config

自动把 qist 的 TVBox `jsm.json` 里可直接转换的 MacCMS `api.php/provide/vod` 资源站转换成 LunaTV / MoonTVPlus 使用的配置格式。

## 可用配置链接

```text
https://raw.githubusercontent.com/520pt/qist-lunatv-config/main/LunaTV-config.txt
```

把上面链接填到 LunaTV / MoonTVPlus 的自定义配置地址即可。

## 说明

- 输出文件：`LunaTV-config.txt`
- 明文检查文件：`LunaTV-config.json`
- 上游来源：`https://v6.gh-proxy.org/https://raw.githubusercontent.com/qist/tvbox/master/jsm.json`
- 定时更新：GitHub Actions 每 6 小时自动拉取上游并提交变化，也支持手动触发。

TVBox 里的 `csp_*`、`drpy`、本地 jar/js/py、直播、解析、广告规则不能直接转成 LunaTV 的 `api_site`，所以只保留直连 CMS 采集接口。
