# qist → LunaTV / MoonTVPlus config

这个仓库提供两种方式：

1. **直连可用配置**：只收录 LunaTV / MoonTVPlus 原生支持的标准苹果 CMS V10 源。
2. **TVBox 桥接工具**：把 TVBox 源包装成 LunaTV / MoonTVPlus 认识的 `api.php/provide/vod` 接口。

## 直连可用配置

```text
https://raw.githubusercontent.com/520pt/qist-lunatv-config/main/LunaTV-config.txt
```

这个链接会定时检测 qist 里能按 MoonTVPlus 搜索方式返回 `.m3u8` 的苹果 CMS 源，并自动更新。

## TVBox 桥接工具

LunaTV / MoonTVPlus 不能直接运行 TVBox 的 `csp_*`、`drpy`、jar、js、py。要让这些源进入 LunaTV，必须先部署一个桥接服务：

```powershell
cd qist-lunatv-config\bridge
docker compose up -d --build
```

本地测试：

```text
http://127.0.0.1:8787/health
http://127.0.0.1:8787/sites
```

用你的公网桥接地址生成 LunaTV 配置：

```powershell
python -X utf8 scripts\generate_bridge_lunatv_config.py --base-url https://你的桥接域名
```

生成：

```text
LunaTV-config-bridge.txt
LunaTV-config-bridge.json
```

把 `LunaTV-config-bridge.txt` 上传到 GitHub raw，或放到任意静态文件地址，然后填进 LunaTV / MoonTVPlus。

### 当前桥接支持状态

- 已支持：TVBox 里的直连苹果 CMS / MacCMS `api.php/provide/vod` 源。
- 明确不伪装：`csp_*`、`drpy`、jar/js/py 等源会返回 `unsupported TVBox engine`，等对应引擎适配后再变成可用。

这样不会出现“配置里看起来有源，但实际不能用还不知道原因”的情况。


## 完整测试

运行：

```powershell
python -X utf8 scripts\full_test_sources.py
```

当前完整测试结果：

- qist sites 总数：163
- LunaTV/MoonTVPlus 可直接使用：6
- 需要后续实现 TVBox 引擎适配：148
- 上游异常：8
- 有 JSON 但没有 MoonTVPlus 会保留的 `.m3u8` 播放结果：1

测试报告：

- `full-test-report.json`
- `full-test-report.md`

## 文件说明

- `LunaTV-config.txt`：直连实测可用版，Base58 编码。
- `LunaTV-config.json`：直连实测可用版明文。
- `validation-report.json`：直连源检测报告。
- `bridge/tvbox_luna_bridge.py`：TVBox → LunaTV 桥接服务。
- `scripts/generate_bridge_lunatv_config.py`：桥接版 LunaTV 配置生成器。
- `tvbox-jsm.json`：qist 原始配置快照。
