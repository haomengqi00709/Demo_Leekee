# 李记包装报价系统 · 服务端 (app/)

阶段5：把前面的想法落地成一个**分角色的 Web 服务**（本地版；Railway 部署放最后）。

## 角色
- **报价员 `/quote`**（只读）：搜套系→选产品→配工艺→出报价单，含兼容参考。数据由服务端从 `pricing.db` **现场注入**——管理员一改，刷新即见。
- **管理员 `/admin`**（读写）：改规则（加成/数量档/工艺费）、维护兼容人工规则，并有 **AI 副驾**：说一句话→AI 提议改动→你确认→入库+留痕。

## 一次性初始化
```bash
cd pricing_db && python3 build_db.py && python3 build_compat.py && python3 gen_quote_app.py   # 生成 DB + 兼容指纹 + quote 模板
cd ../app && python3 init_app_db.py                                                            # 叠加用户/审计表，播种账号
```
演示账号：管理员 `admin/admin123`，报价员 `sales/sales123`。

## 启动
```bash
cd app && uvicorn main:app --reload --port 8000
# 打开 http://localhost:8000
```

## AI 副驾
- 设 `export ANTHROPIC_API_KEY=sk-...` 后，AI 副驾用 Claude（`claude-opus-4-8`，可用 `COPILOT_MODEL` 改）把自然语言转成结构化改动。
- **没设 key 也能用**：内置确定性正则兜底，保证可演示。
- 无论哪种，**都要人点“确认应用”才写库**，并写入 `audit_log`。

## 数据库
默认用 `../pricing_db/pricing.db`；可用环境变量 `PRICING_DB` 覆盖（Railway 上指向挂载卷里的 db 文件）。

## Railway（最后一步，待做）
- 挂一个 volume 放 `pricing.db`；设环境变量 `PRICING_DB`、`ANTHROPIC_API_KEY`、`COPILOT_MODEL`。
- 启动命令：`uvicorn main:app --host 0.0.0.0 --port $PORT`。
