# 附魔领悟 → vmangos 复刻交接包

**日期：** 2026-11-20  
**策略：** 纯文档重写（C++ / 表结构按 vmangos 重做；**不要**从 MangosZero 硬搬 `.cpp`）  
**执行方：** 新开 Cursor Agent，工作区根目录 = 本仓库  
`C:\Users\Administrator\Documents\vmangos`

---

## 0. 给新 Agent 的开场提示（可整段粘贴）

```
工作区：C:\Users\Administrator\Documents\vmangos
任务：按 docs/enchant-comprehension/ 下文档，在 vmangos 上从零实现「附魔领悟」功能并验收。

必读（按顺序）：
1. docs/enchant-comprehension/PORT_BRIEF.md（本交接包）
2. docs/enchant-comprehension/2026-11-19-enchant-comprehension-design.md（规则）
3. docs/enchant-comprehension/2026-11-20-enchant-comprehension-engineering.md（工程与验收；其中路径是 Zero 的，仅作语义参考）

硬性约束：
- 不要复制 MangosZero 的 EnchantComprehensionMgr.cpp 等源码；对照行为在 vmangos 挂点重写。
- 不要实现 EnchantUpgradeMgr（冲击式升级链）——本期不做。
- 自定义法术 ID 必须 < 65536。
- 客户端 patch 与服务端 DataDir DBC 必须成对更新。
- 先摸清 vmangos 的分解成功路径与 EffectEnchantItemPerm，再写代码。
- 用中文回复用户；不要主动写无关 md；代码风格精炼。

数据资产（可复用，路径在另一仓库）：
C:\Users\Administrator\Documents\mangos\tools\enchant_comprehension\out\
  含 Spell.dbc / SpellItemEnchantment.dbc / SkillLineAbility.dbc / patch-3.MPQ
以及 mangos0 库中的 enchant_line / enchant_line_rank（若需导出）。
Zero 库密码曾用 deepwise / 库名 mangos0；vmangos 当前 conf 为用户 mangos/mangos、库 mangos。
```

---

## 1. 环境

| 项 | 路径 / 值 |
|----|-----------|
| 仓库根 | `C:\Users\Administrator\Documents\vmangos` |
| 源码 | `core\`（CMake 工程） |
| 运行目录 | `install\`（`mangosd.exe` / `realmd.exe`） |
| DataDir | `C:/Users/Administrator/Documents/vmangos/data` |
| 客户端 | `C:\Users\Administrator\Documents\vmangos\wow1.12`（已有 `Data\patch.MPQ` 等） |
| World DB | `127.0.0.1;3306;mangos;mangos;mangos`（见 `install/mangosd.conf`） |
| 参考实现（只读） | `C:\Users\Administrator\Documents\mangos` |

已确认：游戏可启动并进入。客户端 Data 里目前**没有** `patch-3.MPQ`（需在接入领悟 DBC 后放入）。

---

## 2. 范围

### 做

- 统一运行时：底座 + 方向链（`enchant_line` / `enchant_line_rank` 语义）
- 分解领悟 + 施放进阶（双概率可配置）
- 技能书同向 1/2/3 互斥；可直打已知最高档；换向覆盖
- 客户端绿字：DBC + `patch-3.MPQ`
- conf 开关与概率；reload 命令

### 不做

- `EnchantUpgradeMgr` / 冲击式原版升级链
- 从 Zero 复制 C++ 或 Rel22 迁移脚本当「能直接跑的 SQL」（表字段按 vmangos 风格新建）
- 客户端大改 UI、灵魂绑定附魔
- 重跑 Batch2–5 全量生成（除非 DBC 复用失败）

### 玩法成功标准（摘自设计）

- 原版底座（如十字军）：施放悟方向 1 → 再施放逐级；分解**仅底座**装悟不出方向 1
- 特效线：分解得 rank0 → 施放进方向
- 部位锁正确；patch 后名称可见

---

## 3. 数据策略（已定）

| 资产 | 策略 |
|------|------|
| 规则/验收 | 以本目录三份 md 为准 |
| C++ | **vmangos 重写**；Zero 源码仅作行为对照 |
| 表 | 在 vmangos world 库**新建** `enchant_line` / `enchant_line_rank`（字段对齐工程手册 §2；类型按 vmangos 惯例调整） |
| 行数据 | **优先**从 Zero 的 `mangos0.enchant_line*` **导出导入**（631 / 3526 行已验收）；不要手填 |
| DBC + patch | **优先复用** `mangos\tools\enchant_comprehension\out\` 三份 DBC + `patch-3.MPQ` → 拷到 vmangos `data` 的 dbc 目录（若有）与 `wow1.12\Data\patch-3.MPQ` |
| 生成器 | 本期可不迁 Python 工具；缺内容再从 mangos 工具链补 |

若导入后 ID 与 vmangos 原版 Spell 冲突：停下来对比，再决定是否重生成；不要 silently 覆盖原版。

---

## 4. 建议实现顺序

1. **勘察挂点（只读）**  
   - 永久附魔：`core/src/game/Spells/SpellEffects.cpp` → `EffectEnchantItemPerm`  
   - 分解：从 `Player.cpp` 分解产物 / loot 完成路径追到「物品已毁、材料已给」之后（Zero 是 `LootHandler`；vmangos 可能不同）  
   - 装备附魔 combat/equip 触发与 ICD 相关代码  
2. **建表 + 导入 line 数据**（先空跑 Load 日志）  
3. **实现 Mgr**：Load / Disenchant / EnchantCast / LearnRank / 索引  
4. **挂钩子 + conf + reload + mangos_string**  
5. **部署 DBC + patch-3.MPQ**，重启服务与客户端  
6. **按工程手册 §5.2 冒烟**（十字军 + 一条特效线 + 试剂抽检可选）

---

## 5. Zero 对照索引（禁止复制，只对照）

| 语义 | Zero 位置（参考） |
|------|-------------------|
| Mgr | `server/src/game/Object/EnchantComprehensionMgr.*` |
| 分解 | `LootHandler.cpp` → `TryAfterDisenchant` |
| 附魔 | `SpellEffectSkillEnchantPet.cpp` → 附魔成功后 `TryAfterEnchantCast`；line 公式跳过 Upgrade |
| ICD | `PlayerItemApply.cpp` → `GetProcIcdMs` |
| conf | `EnchantComprehension.Enable` / `DisenchantChance` / `EnchantCastChance` |
| 工程细节与坑 | 本目录 `2026-11-20-…-engineering.md` |

已知坑（实现时主动规避）：饰品/护甲用 EQUIP_SPELL 壳；试剂分档须严格递增；法术 ID &lt; 65536；服务端 DBC 与客户端 patch 成对。

---

## 6. 交付物清单

- [x] World SQL：`core/sql/custom/enchant_comprehension/`（建表 + line 数据 + spell/SLA + mangos_string）  
- [x] C++：`EnchantComprehensionMgr` + `EffectEnchantItemPerm` / `DoLootRelease(LOOT_DISENCHANTING)` + conf + `.reload enchant_line`  
- [x] 客户端 `wow1.12\Data\patch-3.MPQ` + `data/5875/dbc/SpellItemEnchantment.dbc`  
- [x] 冒烟：用户 2026-11-21 游戏内验收通过（无问题）  
- [x] 偏差旁注：vmangos 法术/SLA 走 DB（非拷 Spell.dbc）；分解钩在 `LootHandler`；无 UpgradeMgr 可跳过  

**收口：** 概率已从冒烟用 100% 改回 conf 默认 25/25；改 conf 后需重启 `mangosd` 生效。

---

## 7. 给用户的操作

1. Cursor **打开文件夹** `C:\Users\Administrator\Documents\vmangos`（新窗口）  
2. 新 Agent 粘贴上面 §0 提示词  
3. 需要对照 Zero 行为时，只读打开  
   `C:\Users\Administrator\Documents\mangos`  
   或让 Agent 读该路径文件（不要把 Zero 当工作区根去改）
