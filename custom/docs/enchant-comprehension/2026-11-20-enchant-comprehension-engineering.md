# 附魔领悟 — 工程手册

**日期：** 2026-11-20  
**状态：** 框架完成（一期 + Batch2–5；运行时仅 `enchant_line`）  
**受众：** 以后改功能的自己；接手维护的人  
**配对文档：** [设计说明](./2026-11-19-enchant-comprehension-design.md)（规则与取舍）  
本文只写：**怎么跑、改哪里、怎么验收、踩过哪些坑**。

---

## 1. 接手速览（约 15 分钟）

### 1.1 这是什么

玩家用附魔专业**分解**装备时，有概率学会对应特效的「领悟配方」；对装备**施放**这些配方时，有概率学会同方向的下一档强化。效果按 **line（底座 + 方向链）** 组织，客户端通过预生成 DBC + `patch-3.MPQ` 显示绿字与技能书。

### 1.2 明确边界

| 做 | 不做 |
|----|------|
| 分解领悟 + 施放进阶 | 运行时新建 DBC 行 |
| 单轴 / 多向强化 | 灵魂绑定附魔（可交易） |
| 试剂规则生成 | 客户端大改 UI |
| `enchant_line` 唯一数据源 | 再写回已删的 `enchant_comprehension_map` |

**另一套机制：** `EnchantUpgradeMgr` = 原版「冲击/攻击」式逐步升级链，与领悟无关。line 配方施放时会**跳过**升级链解析。

### 1.3 关键路径

| 层 | 路径 |
|----|------|
| 运行时 | `server/src/game/Object/EnchantComprehensionMgr.{h,cpp}` |
| 分解钩子 | `LootHandler.cpp` → `TryAfterDisenchant` |
| 附魔钩子 | `SpellEffectSkillEnchantPet.cpp` → `EffectEnchantItemPerm` + `TryAfterEnchantCast` |
| ICD | `PlayerItemApply.cpp` → `GetProcIcdMs` |
| 工具 | `tools/enchant_comprehension/` |
| 打 patch | `rebuild.py` / `_make_patch.py` |
| DB 迁移 | `database/World/Updates/Rel22/Rel22_06_006`…`009` |

### 1.4 常用命令

```text
.reload enchant_line
```

```powershell
# 仅重打客户端 patch（用当前 out/*.dbc）
python tools/enchant_comprehension/rebuild.py

# 重刷试剂并写入服务端 DataDir + 客户端 patch
python tools/enchant_comprehension/rebuild.py --password deepwise --reagents --apply
```

配置（`mangosd.conf`）：

```ini
EnchantComprehension.Enable = 1
EnchantComprehension.DisenchantChance = 25
EnchantComprehension.EnchantCastChance = 25
```

启动日志应类似：`Loaded N enchant lines / M ranks`（**不应**再出现 map fallbacks）。

### 1.5 当前规模（收口后实测）

- `enchant_line`：**631**（`axis_kind=0` 单轴 418；`=1` 多向 213）
- `enchant_line_rank`：**3526**
- 自定义法术 ID 必须 **&lt; 65536**（经典学法术包 uint16）

---

## 2. 架构与数据

### 2.1 运行时门面

`EnchantComprehensionMgr` 唯一负责：

1. **Load** `enchant_line` + `enchant_line_rank`，建索引：`formula` / `enchant` / 物品源法术 → line  
2. **TryAfterDisenchant**：组池、掷骰、`LearnRank`  
3. **TryAfterEnchantCast**：底座 → 抽方向 1；方向 k → 学 k+1  
4. **LearnRank**：同向 1/2/3 互斥（学高卸低）  
5. **GetProcIcdMs**：多向「连贯」类 ICD 覆盖（有数据时）

已删除双轨：`enchant_comprehension_map`、`enchant_comprehension_variant`（`Rel22_06_009`）。

### 2.2 表结构

**`enchant_line`**

| 字段 | 含义 |
|------|------|
| `line_id` | 主键 |
| `base_spell` | 原版本体配方法术；特效线常为源 proc 法术或 0 |
| `base_enchant_id` | rank0 附魔 ID |
| `slot_mask` / `eq_*` | 配方可附部位（与 Spell 装备条件一致） |
| `axis_kind` | `0` 单轴；`1` 多向 |

**`enchant_line_rank`**

| 字段 | 含义 |
|------|------|
| `(line_id, direction, rank)` | 主键；`direction=0` 为底座/单轴主链 |
| `formula_spell` | 可学会的配方法术 |
| `enchant_id` | 写入装备的永久附魔 |
| `proc_spell` | 触发/壳光环法术（无则 0） |
| `chance_pct` / `icd_ms` | 迅疾/ICD 等元数据 |

约定：

- **rank 0** = 底座；方向档 **rank 1..3**  
- 多向默认三向：`1` 迅疾、`2` 强度、`3` 时间（延展/急促）  
- 原版本体配方 **不可** 通过领悟学会；特效底座公式可学

### 2.3 DBC / 客户端

生成并同步三份：

- `Spell.dbc`
- `SpellItemEnchantment.dbc`
- `SkillLineAbility.dbc`

服务端：`server_install/tools/extracted_data/dbc`（或 conf 的 DataDir）  
客户端：`Data/patch-3.MPQ`（由 `out/patch-zhCN-ZZ.mpq` 复制；需排在更早 zhCN patch 之后加载）

**改 DBC 后必须：** 服务端 DataDir 与客户端 patch **成对更新**，并重启 `mangosd` / 重登客户端。

### 2.4 与 EnchantUpgradeMgr

| | 领悟 line | 升级链 |
|--|-----------|--------|
| 目的 | 学会并直打强化档 | 同签名原版配方逐步爬升 |
| 数据 | `enchant_line*` | DBC 扫描 + `enchant_upgrade_override` |
| 施放 | 公式对应附魔 ID 直写 | `Resolve` 可能改写目标 enchant |

`EffectEnchantItemPerm`：若公式/附魔属于 line，则**不走** `EnchantUpgradeMgr::Resolve`。

---

## 3. 玩家闭环（行为语义）

规则细节以设计说明 §5 为准；实现对应关系：

```
分解成功
  → CollectItemLines（装备固有命中/装备触发法术 → line 底座）
  → CollectPermEnchant（当前永久附魔所属 line，等级 ≤ 装备当前档）
  → 空池：提示已掌握 / 无法领悟
  → 否则 DisenchantChance% → LearnRank

施放附魔成功
  → 若施放的是多向底座：EnchantCastChance% → 随机学一个尚未覆盖的方向 1
  → 若施放的是方向 rank&lt;3：同概率学 rank+1
  → 已满 / 已覆盖：不学
```

重要约束（反目标）：

- 分解**不能**从仅有底座的装备悟出方向 1（进阶只靠施放）  
- 同向技能书互斥；换方向 = 覆盖为另一方向对应等级  
- 可直打已学会的最高档（不必装备从 0 爬）

---

## 4. 内容生产线

### 4.1 工具一览

| 脚本 | 作用 |
|------|------|
| `generate.py` | 扫物品命中触发 → 种子 `candidates.csv` + 初始 DBC 配方 |
| `generate_phase1_pilots.py` | 十字军 / 削骨等试点 |
| `generate_batch2_weapon_procs.py` | 武器命中 → 多向 line（读 `candidates.csv`） |
| `generate_batch3_equip_procs.py` | 装备 PROC → **EQUIP_SPELL** 壳 + 多向 |
| `generate_batch4_single_axis.py` | A 族纯被动 → 单轴 |
| `generate_batch5_reagents.py` | 全库试剂 + 旋风等缺口 |
| `rebuild.py` | 日常：打 patch / 可选重刷试剂 |
| `_make_patch.py` | 打 MPQ |

历史 spike（`generate_bonereaver_variants.py` / `generate_whirlwind_variants.py`）产出旧 variant SQL，**勿再灌库**；内容已迁入 line。

### 4.2 ID 段（避免撞车）

| 批次 | formula / spell 大致段 | enchant 大致段 |
|------|------------------------|----------------|
| 初始 map 配方 | 35000+ | 30000+ |
| Phase1 试点 | 35300+ | 30300+ |
| Batch2 | 36000+（proc 40000+） | 31000+ |
| Batch3 | 45000+ | 34000+ |
| Batch4 | 52000+ | 36000+ |
| Batch5 旋风缺口 | 55400+ | 38000+ |

新内容：**先查空闲段**，且全部 **&lt; 65536**。

### 4.3 何时可以重跑

| 操作 | 安全？ | 说明 |
|------|--------|------|
| `rebuild.py` | 是 | 只打包现有 `out/*.dbc` |
| `rebuild.py --reagents --apply` | 通常是 | 按当前 line 重写试剂数量；会改 DBC |
| 单独重跑 Batch2/3/4 | **危险** | 假定空 ID 段与空 line；易重复插入/撞 ID |
| 全量从零再生 | 需专用流程 | 清空相关 ID 段 + line 行 + 备份 DBC；非日常 |

日常维护默认只动 **试剂 / patch**，不要随意「再跑一遍 Batch」。

### 4.4 试剂规则（Batch5）

- 种类：继承该 line **rank0** 试剂种类（分解尘类 + 制造材料类）  
- 数量：相对底座倍率约 `1 / 1.25 / 1.5 / 2.0`，且**每升一档每种材料至少 +1**（避免 `ceil(1×1.25)=2` 导致 I/II/III 同量）  
- 实现：`generate_batch5_reagents.py` → `scale_counts`

---

## 5. 已知坑与验收

### 5.1 已踩过的坑

| 现象 | 原因 | 处理要点 |
|------|------|----------|
| 饰品/护甲「命中」领悟不触发 | 用了武器 `COMBAT_SPELL` | Batch3 用 **EQUIP_SPELL** 挂壳光环 |
| 迅疾档体感无效 | 仅 PPM/低 CustomChance | 查 `spell_proc_event` / 附魔 chance；试点用百分比档 |
| 十字军强化试剂种类不对 | 未继承底座 | Batch5 按 rank0 种类缩放 |
| 削骨延展各档材料一样 | 小基数 ceil 塌缩 | `scale_counts` 强制每档 +1 |
| 学不会自定义法术 | ID ≥ 65536 | 全部分配压在 uint16 内 |
| 绿字空白 | 客户端无 DBC 行 | 必须打 patch，且与服务端同版 |

### 5.2 冒烟清单

1. 启动：line/rank 加载成功；无 map 相关报错  
2. 十字军：训练师底座 → 施放悟方向 1 → 再施放逐级；分解仅底座装**悟不出**方向 1  
3. 削骨/特效：分解得底座 → 施放进方向；技能书同向互斥  
4. 饰品类 Batch3：装备后壳光环在，触发正常  
5. 抽检试剂：同方向 I &lt; II &lt; III，种类与底座一致  
6. 客户端：新配方名可见；`patch-3.MPQ` 已更新  

### 5.3 抽检 SQL 示例

```sql
-- 某 line 全档
SELECT * FROM enchant_line_rank WHERE line_id = 2 ORDER BY direction, rank;

-- 确认无旧表
SHOW TABLES LIKE 'enchant_comprehension%';  -- 应为空
```

试剂需对 `Spell.dbc` 读 `Reagent`/`ReagentCount`（生成脚本或本地 Python），不能只看 SQL。

---

## 6. 改功能检查表

改规则或加内容前过一遍：

1. **改的是规则还是数据？** 规则 → `EnchantComprehensionMgr` + 设计说明；数据 → 生成脚本 + DBC + SQL  
2. **会不会破坏「分解不能跳级」？**  
3. **新方向有没有真实杠杆？**（无 ICD 勿开减 CD）  
4. **ID 是否 &lt; 65536 且不与现有段重叠？**  
5. **武器 proc vs 装备 proc：** 后者优先 EQUIP_SPELL  
6. **试剂是否继承底座且分档严格递增？**  
7. **服务端 DBC 与客户端 patch 是否成对发布？**  
8. **是否误动 `EnchantUpgradeMgr` / 冲击链？**  
9. **reload：** `.reload enchant_line`；改 DBC 仍需重启进程并重登客户端  
10. **更新本文 + 设计说明状态**（若语义变了）

---

## 7. 发布与回滚备忘

**发布最小集**

- 更新后的 `mangosd`（含 Mgr）  
- World DB：`Rel22_06_008` 表 + 内容 SQL + `Rel22_06_009` 收口  
- DataDir 三份 DBC  
- 客户端 `patch-3.MPQ`  
- conf 三项（若改过默认概率）

**回滚**

- 二进制 / DBC / patch 按版本回退  
- line 数据可从生成器 `out/*.sql` 与备份恢复；`06_009` 之后勿再依赖 map 表  

**不要做**

- 在未备份情况下清空 `enchant_line*` 后重跑历史 Batch  
- 只更新服务端 DBC 不更新客户端（或反之）

---

## 8. 文档维护

| 变更类型 | 更新哪里 |
|----------|----------|
| 玩法/规则 | 设计说明 |
| 路径、命令、坑、批次、ID 段 | **本文** |
| 表结构迁移 | `database/World/Updates/Rel22/` + 本文 §2 |

最后工程收口：`Rel22_06_009_Enchant_Line_Only`；入口脚本 `tools/enchant_comprehension/rebuild.py`。
