# Phase 0 Research: 创作资产管理技能

## 技能命名与边界

- **Decision**: 技能名 `creative-assets`（创作资产管理），description 强调「创作团队基于时间树管理素材资产与工作目录」。
- **Rationale**: 「资产管理技能」太泛，会与 `narrative-sim` 技能里既有的调研/改版/移交能力撞名；加「创作」限定并按职责命名，Agent 触发边界清晰。创建目录只是资产管理的一节，不单独成技能。
- **Alternatives considered**: 并入 `narrative-sim/SKILL.md`（受众与触发时机不同，且用户改过的技能不便覆盖）；叫 `creative-workdir`（只覆盖建目录，窄化职责）。

## 分发机制

- **Decision**: 沿用 022 三处落地——仓库副本 `skills/creative-assets/SKILL.md`、只读模板 `resources/skills/creative-assets/SKILL.md`、init 复制到 `<HOME>/skills/creative-assets/SKILL.md`；冻结包经既有 `resources/` 整包携带。
- **Rationale**: 该机制已被 022 验证；`packaging/narrative.spec` 已把整个 `resources/` 打包，新模板自动随包；init 的「不覆盖」保护用户修改。
- **Alternatives considered**: 写全局 Agent 配置（扩大副作用，022 已否决）；只在仓库放文档（创作团队拿不到）。

## WORKDIR.md 来源

- **Decision**: `WORKDIR.md` 作为静态同源文本放 `resources/skills/creative-assets/WORKDIR.md`，`export_handoff` 用 `_write` 复制到移交包根并计入 manifest items；技能「物理布局/归属」两节与其保持一致。不改 `counts` 口径。
- **Rationale**: 规范随数据走，创作团队不必先跑 init；静态文件无需读数据库或依赖 023 代码；`_write` 自带 sha256 自描述；保持既有 counts 断言不回归。
- **Alternatives considered**: 从 tree 动态生成（依赖 023，跨分支耦合）；不放移交包（下游拿不到规范）。

## 资产归属语义

- **Decision**: 资产本体全局唯一，`first_seen_node` 记录首次登场节点，后续节点只在 node.json 加引用；派生物（无 asset_id）留节点目录；游离资产 `first_seen_node` 留空。
- **Rationale**: 资产是「首次在该节点登场」而非「该节点造出来」，归属整部戏；与宪章 I「事件只引用 asset_id、不内联文本」哲学一致，也与 `export_handoff` 的 `assets/` + 引用结构对齐。
- **Alternatives considered**: 资产复制进各节点目录（多份副本、改版需同步）；freestanding 无归属字段（无法反查首次登场）。

## 独立分支耦合

- **Decision**: 024 从 main 切出，不含 023 代码；技能以「无 node_id 时的退化工序」兼容 023 未合并，规范本身不依赖 023 代码。
- **Rationale**: 两特性独立；技能是文档，描述约定而非调用实现。
- **Alternatives considered**: 从 023 切分支（把两特性绑在一起，违反「一个特性一个分支」）。

所有 NEEDS CLARIFICATION 已解决。
