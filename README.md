# Demo · 李记包装报价系统 (Leekee)

玻璃化妆品包装的**报价 / 规则 / 数据**一体化 demo。三个 tab：

- **报价员** `/quote` — 选套系 → 配工艺 → 出报价单，含兼容参考（只读）
- **规则** `/rules` — 说一句话加/改规则（AI 副驾，你确认才生效）+ 规则清单 + 改动留痕
- **数据** `/data` — 上传工厂 Excel 报价单，自动解析 → 预览 → 入库

数据底座是 `pricing.db`（由 100 份报价 Excel 解析而来：3655 条价目 · 133 套系 · 兼容接口指纹）。

## 目录
```
app/            FastAPI 服务（main.py 入口）+ 静态页 + quote 模板
pricing_db/     pricing.db（已构建）+ 解析/构建脚本（build_db / build_compat / importer 复用）
requirements.txt / Procfile / railway.json / .python-version   部署配置
```
> 源 Excel（185MB）与全量产品图（155MB）已在 `.gitignore` 排除，只提交构建好的 `pricing.db`（1.6MB）+ 少量缩略图。要从头重建 DB 需本地有源 Excel，跑 `pricing_db/build_db.py`。

## 本地运行
```bash
pip install -r requirements.txt
python3 app/init_app_db.py                 # 幂等：补应用层表（首次即可）
cd app && uvicorn main:app --reload --port 8000
# 打开 http://localhost:8000
```
**AI 副驾**：OpenAI 兼容接口，**默认走 Kimi(Moonshot)**，只需设一个 `LLM_API_KEY`（不设也能用，走内置正则兜底）：
```bash
export LLM_API_KEY=sk-你的Kimi的key         # base_url/model 已默认 Kimi
# 想换别家：再设 LLM_BASE_URL 和 LLM_MODEL（DeepSeek: https://api.deepseek.com + deepseek-chat）
```

## 部署到 Railway
1. **New Project → Deploy from GitHub repo**，选本仓库。Railway 用 Nixpacks 读 `requirements.txt` 自动装依赖，按 `railway.json` 启动。
2. **加 Volume**（持久化数据）：Service → Variables/Volumes → 挂载一个卷，比如挂到 `/data`。
3. **环境变量**：
   - `PRICING_DB=/data/pricing.db` —— 指向卷里的 DB。首次启动服务会自动把仓库里的种子库复制过去，之后管理员的改动/上传都持久化在卷上，重新部署不丢。
   - AI 副驾（默认 Kimi）：只需设 `LLM_API_KEY=sk-你的Kimi的key`（base_url/model 已默认 Kimi）。
     换别家再加 `LLM_BASE_URL` / `LLM_MODEL`。
4. Railway 会注入 `$PORT`，启动命令已用 `--port $PORT`。部署完访问分配的域名即可。

> 不加 Volume 也能跑（用打包的 `pricing.db`），只是重新部署会重置数据——demo 够用，正式用建议挂卷。
