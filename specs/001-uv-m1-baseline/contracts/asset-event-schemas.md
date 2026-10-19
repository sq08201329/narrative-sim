# Contracts: 资产与事件数据契约

本特性对外的核心契约是两张 JSON Schema。Schema 文件是唯一权威定义
（`schemas/asset.schema.json` / `schemas/event.schema.json`），本文件只做说明，
不复制定义全文 —— 字段口径见 `../data-model.md`，规则来源为宪章原则 I 与手册第 3 章。

## 消费方式

- **写入方**（orchestrator 内部模块）：调用 `store.put_asset` / `store.put_event`，
  由 store 在入库前强制校验；校验失败抛错，数据不落库
- **读取方**（下游视频管线）：消费 `exports/*.jsonl`，每行一个事件；
  只通过 `asset_id` 引用资产，不得依赖事件内出现外貌文本
- **校验方**：任何持有数据的一方都可用两份 Schema 独立复验
  （`jsonschema.validate(payload, schema)`）

## 关键不变量

1. `asset_id` 是跨系统唯一引用键：事件流与视频管线只认它
2. 事件流有序：`run_id → tick → seq` 严格递增可排
3. 事件不内联资产外貌：外貌演进只改资产库，事件流保持稳定
4. Schema 变更必须先升版本、带迁移方案、M1 回归通过（宪章原则 I）

## 错误契约

校验失败时抛出异常，消息格式：

```
<schema 名> 校验失败: <JSON 路径>: <原因>
```

示例：`asset.schema.json 校验失败: $.appearance: 'visual_prompt' is a required property`
