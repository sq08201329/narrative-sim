# Phase 0 Research: 初始化与使用技能分发

## 初始化边界

- **Decision**: `init_app.initialize(home)` 统一负责目录创建和缺失模板复制；显式 init 与现有 start 自动初始化都调用它。
- **Rationale**: 避免两套逻辑漂移；已有文件只报告 existing，不提供 force。
- **Alternatives considered**: 只在 start 初始化（缺少显式配置入口）；每次覆盖模板（破坏用户修改）。

## 技能分发

- **Decision**: 模板存 `resources/skills/narrative-sim/SKILL.md`，PyInstaller datas 原样携带，init 复制到 `<HOME>/skills/narrative-sim/SKILL.md`。
- **Rationale**: 同一模板覆盖开发与冻结，用户可以决定把该目录接入哪个 Agent；不修改全局配置。
- **Alternatives considered**: 直接写用户全局技能目录（扩大副作用）；只在 ZIP 提供而不复制（不符合初始化需求）。

## 配置模板

- **Decision**: `.env.example` 同时放发行根目录与只读资源；初始化复制为 HOME `.env` 仅在目标不存在时进行。
- **Rationale**: 模板可公开随包，真实 `.env` 继续被排除。
- **Alternatives considered**: 让用户凭空新建 `.env`（易漏配置）；把真实 `.env` 打包（禁止）。

所有未知项已解决，无 NEEDS CLARIFICATION。
