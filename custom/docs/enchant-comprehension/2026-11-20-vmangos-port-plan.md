# 附魔领悟 vmangos 移植 — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在 vmangos 上落地附魔领悟（分解/施放双入口 + line 数据 + DBC/patch），并完成十字军与一条特效线冒烟。

**Architecture:** 新建 `EnchantComprehensionMgr` 读 `enchant_line*`；挂 `EffectEnchantItemPerm` 与分解 `DoLootRelease`；Zero 的自定义 Spell/SLA 转成 `spell_template`/`skill_line_ability`，`SpellItemEnchantment.dbc` + `patch-3.MPQ` 成对部署。先探针再全量。

**Tech Stack:** C++14 / CMake / MSVC、MySQL `mangos`、DBC、Python 一次性转换脚本（可选留在 `tools/`）。

**Spec:** `docs/enchant-comprehension/2026-11-20-vmangos-port-design.md`（玩法见同目录设计说明）

## Global Constraints

- 自定义法术 ID `< 65536`；冲突则停，不静默覆盖原版
- 禁止复制 MangosZero `EnchantComprehensionMgr.cpp`；对照行为重写
- 本期不做 `EnchantUpgradeMgr`
- 服务端法术/SLA 走 DB；附魔定义走 `SpellItemEnchantment.dbc`；客户端走 `patch-3.MPQ`
- 用户规则：不主动 git commit，除非用户明确要求
- 回复中文；代码精炼；不另起无关 md

## Review Focus

- 分解仅底座装备时池中不得出现方向 rank≥1 → Task 4 冒烟断言
- formula 在 DB 存在但 enchant 不在 DBC → Load 跳过并打错误日志，不全崩溃 → Task 3
- 只更新 patch 不更新 SpellItemEnchantment（或反之）→ 施放失败/绿字空 → Task 2 部署检查清单
- 同向学会 rank3 后技能书不应仍显示 rank1 → Task 4 LearnRank 互斥
- `spell_id`/`entry` smallint 溢出或 SLA `id` 撞车 → Task 1/2 导入前校验

## File Structure

| 路径 | 职责 |
|------|------|
| `core/src/game/EnchantComprehensionMgr.{h,cpp}` | Load / 双入口 / LearnRank / 索引 |
| `core/src/game/Spells/SpellEffects.cpp` | 附魔成功钩子 |
| `core/src/game/Handlers/LootHandler.cpp` | 分解完成钩子 |
| `core/src/game/World.{h,cpp}` | conf 枚举与 LoadConfig；启动 Load |
| `core/src/game/Chat/Chat.cpp` + Commands | `.reload enchant_line` |
| `core/src/game/Language.h` + `mangos_string` SQL | 领悟提示文案 |
| `core/src/game/CMakeLists.txt` | 编入 Mgr |
| `core/sql/custom/enchant_comprehension/` | 建表、导数据、string、（生成的）spell/SLA SQL |
| `tools/enchant_comprehension/`（本仓新建，薄脚本） | DBC→SQL 探针/转换；不迁全套 Zero 生成器 |
| `data/5875/dbc/SpellItemEnchantment.dbc` | 服务端附魔定义 |
| `wow1.12/Data/patch-3.MPQ` | 客户端展示 |

冒烟锚点（`mangos0` 已核实）：line `1` 十字军 `base_spell=20034`；line `2` 特效 `base_spell=21153`；方向公式自 `35300` 起。

---

### Task 1: 适配探针 + 建表/导 line

**Files:**
- Create: `tools/enchant_comprehension/probe_dbc_overlap.py`（或同等 PS/Python）
- Create: `core/sql/custom/enchant_comprehension/01_schema.sql`
- Create: `core/sql/custom/enchant_comprehension/02_enchant_line_data.sql`（从 mangos0 导出）

**Interfaces:**
- Produces: world 库存在空可 Load 的 `enchant_line` / `enchant_line_rank`；探针报告「Spell/SLA/Enchant 增量规模 + 与 vmangos 原版 ID 重叠数」

- [ ] **Step 1: 写探针脚本**  
  输入：`mangos\tools\enchant_comprehension\out\{Spell,SkillLineAbility,SpellItemEnchantment}.dbc` 与 `data/5875/dbc/` 同名文件。  
  断言输出：自定义 formula 段 `35000–56000` 与 `mangos.spell_template` 重叠行数 == 0；打印两侧 SpellItemEnchantment 最大 ID 与 out 中 ≥30000 的 enchant 数量。

- [ ] **Step 2: 跑探针**  
  Run: `python tools/enchant_comprehension/probe_dbc_overlap.py`  
  Expected: 重叠 0；若非 0 → **停止**并报告，不进入 Task 2。

- [ ] **Step 3: 建表 SQL**  
  `01_schema.sql`：`enchant_line` / `enchant_line_rank` 字段对齐设计 §5.2 / 工程手册 §2（`line_id`, `base_spell`, `base_enchant_id`, `slot_mask`, `eq_*`, `axis_kind`；rank 主键 `(line_id,direction,rank)` + `formula_spell`,`enchant_id`,`proc_spell`,`chance_pct`,`icd_ms`）。

- [ ] **Step 4: 从 mangos0 导出全量 INSERT 到 `02_enchant_line_data.sql` 并导入 mangos**  
  Verify:  
  `SELECT COUNT(*) FROM enchant_line;` → 631  
  `SELECT COUNT(*) FROM enchant_line_rank;` → 3526

---

### Task 2: Spell/SLA/Enchant/patch 部署

**Files:**
- Create: `tools/enchant_comprehension/dbc_to_vmangos_sql.py`
- Create: `core/sql/custom/enchant_comprehension/03_spell_template_custom.sql`
- Create: `core/sql/custom/enchant_comprehension/04_skill_line_ability_custom.sql`
- Create: `core/sql/custom/enchant_comprehension/05_spell_proc_event_optional.sql`（若 Zero/工具侧有可导出则生成，否则可空文件说明跳过）
- Modify/Replace: `data/5875/dbc/SpellItemEnchantment.dbc`（先备份为 `.bak`）
- Copy: `wow1.12/Data/patch-3.MPQ` ← `out/patch-zhCN-ZZ.mpq` 或文档指定的中文包（若已有 patch-3 先备份）

**Interfaces:**
- Consumes: Task 1 探针通过
- Produces: `spell_template` 含 formula/proc（build=5875）；`skill_line_ability` 新 id > 现有 max(15030)；服务端 enchant DBC 可 Lookup ≥30300；客户端 patch 就位

- [ ] **Step 1: 实现 `dbc_to_vmangos_sql.py`**  
  - 从 out `Spell.dbc` 抽出 id∈自定义段且不在原版 vmangos Spell.dbc 的行 → 映射为 `spell_template` INSERT（`build=5875`；缺列用合理默认）  
  - 从 out `SkillLineAbility.dbc` 抽新增 spell_id → `skill_line_ability` INSERT（`id` 自 `MAX(id)+1` 起，`build=5875`）  
  - 若映射失败：打印失败列并退出非 0

- [ ] **Step 2: 生成并导入 03/04（及可选 05）**  
  Verify:  
  `SELECT COUNT(*) FROM spell_template WHERE entry BETWEEN 35000 AND 56000 AND build=5875;` > 0  
  `SELECT COUNT(*) FROM spell_template WHERE entry IN (35300,35301);` → 2  
  `SELECT COUNT(*) FROM skill_line_ability WHERE spell_id BETWEEN 35000 AND 56000 AND build=5875;` > 0

- [ ] **Step 3: 备份并替换 `SpellItemEnchantment.dbc`；部署 patch-3.MPQ**  
  Verify: 文件大小 out 侧与目标侧一致（或明显大于原版 163KB）；`data/5875/dbc/SpellItemEnchantment.dbc.bak` 存在。

- [ ] **Step 4: 部署检查清单（人工/脚本打印）**  
  - [ ] DataDir enchant DBC 已换  
  - [ ] 客户端 `Data/patch-3.MPQ` 已放  
  - [ ] 未单独替换服务端 `Spell.dbc` 来「顶替」`spell_template`（避免误操作）

---

### Task 3: EnchantComprehensionMgr + conf + reload

**Files:**
- Create: `core/src/game/EnchantComprehensionMgr.h`
- Create: `core/src/game/EnchantComprehensionMgr.cpp`
- Modify: `core/src/game/CMakeLists.txt`（加入两文件）
- Modify: `core/src/game/World.h` — `CONFIG_BOOL_ENCHANT_COMPREHENSION`, `CONFIG_UINT32_ENCHANT_COMPREHENSION_DISENCHANT_CHANCE`, `CONFIG_UINT32_ENCHANT_COMPREHENSION_ENCHANT_CAST_CHANCE`
- Modify: `core/src/game/World.cpp` — `setConfig` 默认 Enable=1, Chance=25/25；启动调用 `sEnchantComprehensionMgr.Load()`（在 spells + SpellItemEnchantment 已加载之后）
- Modify: `install/mangosd.conf.dist` + 运行中 `install/mangosd.conf`
- Modify: `core/src/game/Language.h` + SQL `mangos_string` 三条（成功 / 已掌握 / 无法领悟）
- Modify: `core/src/game/Chat/Chat.cpp` + 对应 Command handler — `.reload enchant_line` → `Load()`

**Interfaces:**
- Produces:
  - `void EnchantComprehensionMgr::Load()`
  - `void TryAfterDisenchant(Player*, ItemPrototype const*, uint32 permEnchantId)`
  - `void TryAfterEnchantCast(Player*, uint32 formulaSpellId, uint32 appliedEnchantId)`
  - `bool LearnRank(Player*, uint32 formulaSpell)`
  - `uint32 GetProcIcdMs(uint32 enchantId) const`（可先实现索引，挂钩可延后）
  - `bool IsLineFormula(uint32) const` / `IsLineEnchant(uint32) const`
- Load 规则：rank 行若 `!GetSpellEntry(formula)` 或 `!sSpellItemEnchantmentStore.LookupEntry(enchant)` → 跳过并 `LOG_DBERROR`，不中止进程

- [ ] **Step 1: 实现 Mgr（对照 Zero 行为，不复制源码）**  
  语义钉死：  
  - Disenchant：`CollectItemLines`（物品 spell trigger ON_HIT/ON_EQUIP）+ `CollectPermEnchant`（等级≤当前；排除原版 baseSpell；底座装不得进方向1）→ 概率 → `LearnRank`  
  - EnchantCast：多向底座 → 随机未覆盖方向1；方向 rank&lt;3 → rank+1  
  - LearnRank：同向 1..3 `RemoveSpell` 低档后 `LearnSpell`

- [ ] **Step 2: 接线 conf / Load / reload / mangos_string**

- [ ] **Step 3: 编译**  
  Run:  
  `cmake -S core -B build -G "Visual Studio 17 2022" -A x64 -DCMAKE_INSTALL_PREFIX=.../install -DBUILD_EXTRACTORS=1`  
  `cmake --build build --config Release --target mangosd`  
  Expected: 成功；安装覆盖 `install/mangosd.exe`

- [ ] **Step 4: 启动验证 Load**  
  重启 mangosd；`Server.log` 含 `Loaded N enchant lines / M ranks`；N/M 接近 631/3526（允许少量 bad row，需在日志可见）。  
  若 N 远小于 631 → 先修 Task 2 数据，再继续 Task 4。

---

### Task 4: 挂钩子 + 冒烟

**Files:**
- Modify: `core/src/game/Spells/SpellEffects.cpp` — `EffectEnchantItemPerm` 成功路径末尾调用 `TryAfterEnchantCast(pCaster, m_spellInfo->Id, enchantId)`
- Modify: `core/src/game/Handlers/LootHandler.cpp` — `LOOT_DISENCHANTING` 在 `DestroyItem` 前：  
  `uint32 perm = pItem->GetEnchantmentId(PERM_ENCHANTMENT_SLOT);`  
  `ItemPrototype const* proto = pItem->GetProto();`  
  然后 `TryAfterDisenchant(player, proto, perm);`
- Optional: `Player.cpp` `CastItemCombatSpell` 使用 `GetProcIcdMs`（有 icd 数据再做；不阻塞冒烟）

**Interfaces:**
- Consumes: Task 3 Mgr API

- [ ] **Step 1: 打两个钩子并编译安装**（同 Task 3 编译命令）

- [ ] **Step 2: 配置冒烟概率（临时）**  
  `EnchantComprehension.DisenchantChance = 100`  
  `EnchantComprehension.EnchantCastChance = 100`  
  测完改回 25 或保持按需。

- [ ] **Step 3: 十字军冒烟（line 1）**  
  - 角色已会 `20034`  
  - 对武器施放 `20034` → 应学会方向1 之一（`35300`/`35303`/`35306`）  
  - 再施放该方向1 → 学会同向2  
  - 分解**仅**带 enchant `1900` 的武器 → **不得**学会任何 `3530x` 方向档  
  - 分解已打 `30300`（迅疾1）的武器 → 允许补齐 ≤该档且未掌握的同线可学公式（仍受逐级前提）

- [ ] **Step 4: 特效线冒烟（line 2）**  
  - 分解带固有特效来源的装备 → 学会 rank0 formula（非 `21153` 原版本体若规则排除）  
  - 施放 rank0 → 悟方向1；同向互斥：学会 rank2 后 `HasSpell(rank1)==false`

- [ ] **Step 5: 客户端**  
  重登；技能书/法术名非空白（patch 生效）。

- [ ] **Step 6: 在回复中汇总冒烟通过/失败项**；若失败只修本 Task/数据，不扩大范围到生成器重跑，除非 Task 1/2 证明复用失败。

---

## Self-Review (done)

1. **Spec coverage:** 挂点、表、DBC/DB 分流、Mgr、conf/reload、patch、冒烟、冲突停止 — 均有 Task。  
2. **Steps:** 无单测框架；用 SQL/编译/游戏内断言代替。  
3. **Types:** Mgr API 在 Task 3 Produces 与 Task 4 Consumes 一致。  
4. **Review Focus:** 五条均挂到 Task 1–4。  
5. **Proportion:** 计划短于实现代码；未贴 Mgr 函数体。
