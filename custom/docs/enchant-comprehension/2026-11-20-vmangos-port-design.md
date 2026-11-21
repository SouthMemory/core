# 附魔领悟 → vmangos 移植设计

**日期：** 2026-11-20  
**状态：** 已实现并验收（2026-11-21）  
**配对：** [设计说明](./2026-11-19-enchant-comprehension-design.md)（玩法规则）· [工程手册](./2026-11-20-enchant-comprehension-engineering.md)（Zero 语义参考）· [交接包](./PORT_BRIEF.md)

## 1. 意图

在已可运行的 vmangos 上，按既有玩法规则落地「附魔领悟」：分解补配方、施放进阶，底座+方向链，客户端可见绿字。不从 MangosZero 复制 C++；行为对照后重写。

## 2. 目标 / 非目标 / 反目标

**目标**
- 统一运行时读 `enchant_line` / `enchant_line_rank`
- 分解领悟 + 施放领悟（双概率 conf）
- 同向 1/2/3 技能书互斥；可直打最高已知档；换向覆盖
- 客户端 `patch-3.MPQ` 与服务端附魔/法术数据成对可用
- 冒烟：十字军 + 一条特效线

**非目标**
- `EnchantUpgradeMgr` / 冲击式升级链
- 重跑 Batch2–5 全量生成（除非复用失败）
- 客户端大改 UI、灵魂绑定附魔
- 迁整套 Python 生产线（长期维护另议）

**反目标**
- 分解从仅底座装备悟出方向 1
- 静默覆盖原版 Spell / 冲突 ID
- 只更服务端或只更客户端一侧 DBC/patch

## 3. 约束

- 自定义法术 ID `< 65536`（`spell_template.entry` / `skill_line_ability.spell_id` 均为 smallint）
- vmangos：**法术与专业行在 DB**（`spell_template`、`skill_line_ability`）；**永久附魔定义在 DBC**（`SpellItemEnchantment.dbc`）；客户端展示靠 `patch-3.MPQ`
- World：`mangos`/`mangos`；DataDir：`.../vmangos/data`（dbc 在 `5875/dbc`）；客户端：`wow1.12`
- 行数据优先从 `mangos0.enchant_line*` 导出（631 / 3526）；DBC/patch 优先复用 `mangos\tools\enchant_comprehension\out\`
- 代码风格精炼；不主动写无关文档

## 4. Approaches

| 方案 | 摘要 | 取舍 |
|------|------|------|
| A 复用 Zero 内容 + 适配层 | 导 line SQL；DBC 增量 → `spell_template`/`skill_line_ability`；换 `SpellItemEnchantment.dbc` + patch；Mgr 重写 | 最快出全量；需验证字段映射 |
| B 先运行时后内容 | 先挂点+空/少行，再灌内容 | 稳但中间不可玩 |
| C 迁生成器重生成 | 对 vmangos 直接吐 DB SQL | 长期干净，本期过重 |

**选定：A，带探针顺序（近似 B 的前半）。**  
先做适配探针 + 十字军/一条特效线冒烟，通过后再全量导入。C 仅在复用撞车或映射失败时启用。

## 5. 已定实现要点

### 5.1 挂点（勘察已确认）

- 附魔成功：`Spell::EffectEnchantItemPerm` 成功写 enchant 之后 → `TryAfterEnchantCast`
- 分解完成：`WorldSession::DoLootRelease` 中 `LOOT_DISENCHANTING`，`DestroyItem` 之前捕获 `proto` + `GetEnchantmentId(PERM)` → `TryAfterDisenchant`
- 学法：`Player::LearnSpell` / `RemoveSpell`（同向互斥由 Mgr 卸低档）
- ICD（若有 `icd_ms`）：在 combat/equip 应用路径查 `GetProcIcdMs`（对照 Zero 的 `CastItemCombatSpell` 一带；无 UpgradeMgr 可跳过）

### 5.2 数据

- 新建 `enchant_line` / `enchant_line_rank`（字段对齐工程手册 §2；类型按 vmangos 惯例，如 unsigned / tinyint）
- 导入前：校验 `formula_spell` 不在现有 `spell_template` 冲突段；`enchant_id` 能在目标 `SpellItemEnchantment.dbc` 查到
- 自定义法术：由 Zero `out/Spell.dbc` 增量转为 `spell_template`（及必要 `locales_spell` / `spell_proc_event`）插入，`build=5875`
- 专业行：由 `SkillLineAbility.dbc` 增量转为 `skill_line_ability`（新 `id` 接在现有 max 之后，同 build）
- 服务端：替换/合并 `data/5875/dbc/SpellItemEnchantment.dbc`（**不要**指望只靠拷 `Spell.dbc` 让服务端学会配方）
- 客户端：`wow1.12/Data/patch-3.MPQ`（用 out 中与中文客户端匹配的包；需排在已有 patch 之后加载）

### 5.3 运行时

- 新建 `EnchantComprehensionMgr`（Load / Disenchant / EnchantCast / LearnRank / 索引）；行为语义以设计说明 §5 与工程手册 §3 为准；**禁止**粘贴 Zero `.cpp`
- conf：`EnchantComprehension.Enable` / `DisenchantChance` / `EnchantCastChance`
- reload：`.reload enchant_line`（或等价）+ `mangos_string` 提示文案
- Load 校验用 `sSpellMgr.GetSpellEntry` + `sSpellItemEnchantmentStore`（不用 Zero 的 `sSpellStore`）

### 5.4 建议落地顺序

1. 适配探针：抽样对比 Zero out DBC 与 vmangos 表/DBC 格式；确认中文 patch 选用  
2. 建表 + 导 line（可先全量导，Load 时跳过缺 spell/enchant 的行并打日志）  
3. 转换并灌 formula/proc + SLA；部署 SpellItemEnchantment + patch  
4. 实现 Mgr + 钩子 + conf + reload  
5. 冒烟（工程手册 §5.2：十字军 + 特效线）；再确认全量行加载数接近 631/3526  

## 6. 留给建造者

- DBC→`spell_template` 列映射与缺失列默认值  
- `skill_line_ability.id` 分配策略  
- 同向互斥：Mgr 内 `RemoveSpell` 即可（不必强上 `spell_chain`），除非验收要求技能书 rank 显示  
- SQL 落盘方式：`core/sql/custom/` 或一次性导入脚本（适合本服，无需 Rel22 编号）  
- `spell_proc_event` 是否从 Zero 库/工具侧一并导出（迅疾档需要时再补）  
- ICD 挂钩精确函数（有数据再挂，不阻塞主路径）

## 7. 成功标准

- 启动日志：Loaded N lines / M ranks；无大面积 bad row  
- 十字军：底座施放可悟方向；分解仅底座**不能**悟方向 1  
- 特效线：分解得 rank0 → 施放进阶；技能书同向互斥  
- 客户端新配方名可见；服务端可施放对应 formula  
- 若 ID/格式冲突：停止并报告，不静默覆盖  

## 8. 建造者自行拍板（已记入 §6）

无额外需用户拍板项；用户已选定 **A+探针**。
