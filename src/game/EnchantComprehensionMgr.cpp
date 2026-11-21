#include "EnchantComprehensionMgr.h"
#include "Chat.h"
#include "Database/DatabaseEnv.h"
#include "DBCStores.h"
#include "ItemPrototype.h"
#include "Language.h"
#include "Log.h"
#include "Player.h"
#include "Policies/SingletonImp.h"
#include "ProgressBar.h"
#include "SpellMgr.h"
#include "Utilities/Random.h"
#include "World.h"
#include <algorithm>

INSTANTIATE_SINGLETON_1(EnchantComprehensionMgr);

namespace
{
bool RollPercent(uint32 chance)
{
    if (chance > 100)
        chance = 100;
    return chance && urand(1, 100) <= chance;
}

bool IsItemLineTrigger(uint32 trigger)
{
    return trigger == ITEM_SPELLTRIGGER_CHANCE_ON_HIT || trigger == ITEM_SPELLTRIGGER_ON_EQUIP;
}
}

bool EnchantComprehensionMgr::Load()
{
    std::unique_ptr<QueryResult> lineRes(WorldDatabase.Query(
        "SELECT `line_id`, `base_spell`, `axis_kind` FROM `enchant_line`"));
    std::unique_ptr<QueryResult> rankRes(WorldDatabase.Query(
        "SELECT `line_id`, `direction`, `rank`, `formula_spell`, `enchant_id`, `proc_spell`, `icd_ms` "
        "FROM `enchant_line_rank`"));
    if (!lineRes || !rankRes)
    {
        sLog.Out(LOG_DBERROR, LOG_LVL_MINIMAL,
            "EnchantComprehension: query failed, keeping previous data");
        return false;
    }

    std::unordered_map<uint32, Line> lines;
    std::vector<Rank> ranks;
    std::unordered_map<uint32, uint32> byFormula;
    std::unordered_map<uint32, uint32> byEnchant;
    std::unordered_map<uint32, uint32> lineByItemSpell;
    std::unordered_map<uint32, uint32> icdByEnchant;
    std::unordered_set<uint32> baseSpells;
    uint32 lineCount = 0;
    uint32 rankCount = 0;

    {
        BarGoLink bar(lineRes->GetRowCount());
        do
        {
            Field* f = lineRes->Fetch();
            bar.step();
            uint32 lineId = f[0].GetUInt32();
            if (!lineId || lines.find(lineId) != lines.end())
            {
                sLog.Out(LOG_DBERROR, LOG_LVL_MINIMAL, "enchant_line: bad line_id %u", lineId);
                continue;
            }
            Line& line = lines[lineId];
            line.baseSpell = f[1].GetUInt32();
            line.axisKind = f[2].GetUInt8();
            if (line.baseSpell)
                baseSpells.insert(line.baseSpell);
            ++lineCount;
        }
        while (lineRes->NextRow());
    }

    {
        BarGoLink bar(rankRes->GetRowCount());
        ranks.reserve(rankRes->GetRowCount());
        do
        {
            Field* f = rankRes->Fetch();
            bar.step();
            Rank row;
            row.lineId = f[0].GetUInt32();
            row.direction = f[1].GetUInt8();
            row.rank = f[2].GetUInt8();
            row.formula = f[3].GetUInt32();
            row.enchantId = f[4].GetUInt32();
            row.procSpell = f[5].GetUInt32();
            row.icdMs = f[6].GetUInt32();

            auto lit = lines.find(row.lineId);
            if (lit == lines.end() || !row.formula || !row.enchantId
                || !sSpellMgr.GetSpellEntry(row.formula)
                || !sSpellItemEnchantmentStore.LookupEntry(row.enchantId)
                || byFormula.find(row.formula) != byFormula.end()
                || byEnchant.find(row.enchantId) != byEnchant.end())
            {
                sLog.Out(LOG_DBERROR, LOG_LVL_MINIMAL,
                    "enchant_line_rank: bad row line=%u dir=%u rank=%u formula=%u ench=%u",
                    row.lineId, row.direction, row.rank, row.formula, row.enchantId);
                continue;
            }

            uint32 idx = uint32(ranks.size());
            ranks.push_back(row);
            lit->second.ranks.push_back(idx);
            byFormula[row.formula] = idx;
            byEnchant[row.enchantId] = idx;
            if (row.icdMs)
                icdByEnchant[row.enchantId] = row.icdMs;
            ++rankCount;
        }
        while (rankRes->NextRow());
    }

    for (auto const& it : lines)
    {
        Rank const* base = nullptr;
        for (uint32 idx : it.second.ranks)
        {
            Rank const& row = ranks[idx];
            if (row.direction == 0 && row.rank == 0)
            {
                base = &row;
                break;
            }
        }
        if (base && it.second.baseSpell && base->formula != it.second.baseSpell)
            lineByItemSpell[it.second.baseSpell] = it.first;
    }
    for (size_t i = 0; i < ranks.size(); ++i)
    {
        uint32 proc = ranks[i].procSpell;
        if (!proc || lineByItemSpell.find(proc) != lineByItemSpell.end())
            continue;
        lineByItemSpell[proc] = ranks[i].lineId;
    }

    m_lines.swap(lines);
    m_ranks.swap(ranks);
    m_byFormula.swap(byFormula);
    m_byEnchant.swap(byEnchant);
    m_lineByItemSpell.swap(lineByItemSpell);
    m_icdByEnchant.swap(icdByEnchant);
    m_baseSpells.swap(baseSpells);

    sLog.Out(LOG_BASIC, LOG_LVL_MINIMAL, ">> Loaded %u enchant lines / %u ranks", lineCount, rankCount);
    return true;
}

EnchantComprehensionMgr::Rank const* EnchantComprehensionMgr::RankByFormula(uint32 spellId) const
{
    auto it = m_byFormula.find(spellId);
    return it == m_byFormula.end() ? nullptr : &m_ranks[it->second];
}

EnchantComprehensionMgr::Rank const* EnchantComprehensionMgr::RankByEnchant(uint32 enchantId) const
{
    auto it = m_byEnchant.find(enchantId);
    return it == m_byEnchant.end() ? nullptr : &m_ranks[it->second];
}

EnchantComprehensionMgr::Line const* EnchantComprehensionMgr::LineById(uint32 lineId) const
{
    auto it = m_lines.find(lineId);
    return it == m_lines.end() ? nullptr : &it->second;
}

EnchantComprehensionMgr::Rank const* EnchantComprehensionMgr::RankAt(Line const& line, uint8 direction, uint8 rank) const
{
    for (uint32 idx : line.ranks)
    {
        Rank const& row = m_ranks[idx];
        if (row.direction == direction && row.rank == rank)
            return &row;
    }
    return nullptr;
}

bool EnchantComprehensionMgr::IsBaseSpell(uint32 spellId) const
{
    return spellId && m_baseSpells.count(spellId);
}

bool EnchantComprehensionMgr::IsLineFormula(uint32 formulaSpell) const
{
    return m_byFormula.count(formulaSpell) != 0;
}

bool EnchantComprehensionMgr::IsLineEnchant(uint32 enchantId) const
{
    return m_byEnchant.count(enchantId) != 0;
}

bool EnchantComprehensionMgr::Covers(Player const* player, Line const& line, uint8 direction, uint8 minRank) const
{
    for (uint32 idx : line.ranks)
    {
        Rank const& row = m_ranks[idx];
        if (row.direction == direction && row.rank >= minRank && player->HasSpell(row.formula))
            return true;
    }
    return false;
}

bool EnchantComprehensionMgr::MeetsDePrereq(Player const* player, Line const& line, Rank const& row) const
{
    if (!row.rank)
        return true;
    Rank const* prev = RankAt(line, row.direction, uint8(row.rank - 1));
    if (!prev && row.direction)
        prev = RankAt(line, 0, 0);
    if (!prev)
        return false;
    if (row.rank == 1)
        return player->HasSpell(prev->formula);
    return Covers(player, line, row.direction, uint8(row.rank - 1));
}

void EnchantComprehensionMgr::Consider(Player const* player, uint32 formula, bool eligible,
                                       std::vector<uint32>& pool, bool& known) const
{
    if (!formula || IsBaseSpell(formula))
        return;
    if (player->HasSpell(formula))
    {
        known = true;
        return;
    }
    if (!eligible)
        return;
    if (std::find(pool.begin(), pool.end(), formula) == pool.end())
        pool.push_back(formula);
}

void EnchantComprehensionMgr::CollectItemLines(Player const* player, ItemPrototype const* proto,
                                               std::vector<uint32>& pool, bool& known) const
{
    for (int i = 0; i < MAX_ITEM_PROTO_SPELLS; ++i)
    {
        uint32 spellId = proto->Spells[i].SpellId;
        if (!spellId || !IsItemLineTrigger(proto->Spells[i].SpellTrigger))
            continue;
        auto it = m_lineByItemSpell.find(spellId);
        if (it == m_lineByItemSpell.end())
            continue;
        Line const* line = LineById(it->second);
        if (!line)
            continue;
        Rank const* base = RankAt(*line, 0, 0);
        if (!base)
            continue;
        Consider(player, base->formula, base->formula != line->baseSpell, pool, known);
    }
}

void EnchantComprehensionMgr::CollectPermEnchant(Player const* player, uint32 permEnchantId,
                                                 std::vector<uint32>& pool, bool& known) const
{
    Rank const* cur = RankByEnchant(permEnchantId);
    if (!cur)
        return;
    Line const* line = LineById(cur->lineId);
    if (!line)
        return;

    for (uint32 idx : line->ranks)
    {
        Rank const& row = m_ranks[idx];
        if (row.rank > cur->rank || row.formula == line->baseSpell)
            continue;
        bool covered = row.rank ? Covers(player, *line, row.direction, row.rank) : player->HasSpell(row.formula);
        if (covered)
        {
            known = true;
            continue;
        }
        Consider(player, row.formula, MeetsDePrereq(player, *line, row), pool, known);
    }
}

uint32 EnchantComprehensionMgr::GetProcIcdMs(uint32 enchantId) const
{
    auto it = m_icdByEnchant.find(enchantId);
    return it == m_icdByEnchant.end() ? 0 : it->second;
}

bool EnchantComprehensionMgr::LearnRank(Player* player, uint32 formulaSpell)
{
    if (!player || IsBaseSpell(formulaSpell))
        return false;
    Rank const* row = RankByFormula(formulaSpell);
    Line const* line = row ? LineById(row->lineId) : nullptr;
    if (!row || !line || formulaSpell == line->baseSpell)
        return false;

    for (uint32 idx : line->ranks)
    {
        Rank const& other = m_ranks[idx];
        if (other.direction != row->direction || other.rank < 1 || other.rank > 3)
            continue;
        if (other.formula == formulaSpell || !player->HasSpell(other.formula))
            continue;
        player->RemoveSpell(other.formula, false, false);
    }

    if (!player->HasSpell(formulaSpell))
        player->LearnSpell(formulaSpell, false);
    return true;
}

void EnchantComprehensionMgr::TryAfterDisenchant(Player* player, ItemPrototype const* proto, uint32 permEnchantId)
{
    if (!player || !proto || !sWorld.getConfig(CONFIG_BOOL_ENCHANT_COMPREHENSION))
        return;

    std::vector<uint32> pool;
    bool known = false;
    CollectItemLines(player, proto, pool, known);
    CollectPermEnchant(player, permEnchantId, pool, known);

    if (pool.empty())
    {
        ChatHandler(player).PSendSysMessage(known ? LANG_ENCHANT_COMPREHEND_KNOWN : LANG_ENCHANT_COMPREHEND_NONE);
        return;
    }
    if (!RollPercent(sWorld.getConfig(CONFIG_UINT32_ENCHANT_COMPREHENSION_DISENCHANT_CHANCE)))
        return;

    uint32 formula = pool[urand(0, uint32(pool.size() - 1))];
    if (!LearnRank(player, formula))
        return;
    ChatHandler(player).PSendSysMessage(LANG_ENCHANT_COMPREHEND_SUCCESS);
}

uint32 EnchantComprehensionMgr::PickDirectionEntry(Player const* player, Line const& line) const
{
    std::vector<uint32> options;
    for (uint32 idx : line.ranks)
    {
        Rank const& row = m_ranks[idx];
        if (row.direction < 1 || row.rank != 1 || IsBaseSpell(row.formula))
            continue;
        if (Covers(player, line, row.direction, 1))
            continue;
        options.push_back(row.formula);
    }
    if (options.empty())
        return 0;
    return options[urand(0, uint32(options.size() - 1))];
}

void EnchantComprehensionMgr::TryAfterEnchantCast(Player* player, uint32 formulaSpellId, uint32 appliedEnchantId)
{
    if (!player || !sWorld.getConfig(CONFIG_BOOL_ENCHANT_COMPREHENSION))
        return;

    Rank const* cur = RankByFormula(formulaSpellId);
    if (!cur)
        cur = RankByEnchant(appliedEnchantId);
    Line const* line = cur ? LineById(cur->lineId) : nullptr;
    if (!cur || !line)
        return;

    bool side = false;
    for (uint32 idx : line->ranks)
    {
        if (m_ranks[idx].direction >= 1)
        {
            side = true;
            break;
        }
    }

    uint32 learn = 0;
    bool baseCast = cur->direction == 0 && cur->rank == 0 && side;
    if (baseCast)
    {
        Rank const* base = RankAt(*line, 0, 0);
        if (!base)
            return;
        bool needBase = base->formula != line->baseSpell || line->axisKind == 1;
        if (needBase && !player->HasSpell(base->formula))
            return;
        learn = PickDirectionEntry(player, *line);
    }
    else
    {
        if (!player->HasSpell(cur->formula) || cur->rank >= 3)
            return;
        Rank const* next = RankAt(*line, cur->direction, uint8(cur->rank + 1));
        if (!next || IsBaseSpell(next->formula) || Covers(player, *line, cur->direction, next->rank))
            return;
        learn = next->formula;
    }

    if (!learn || !RollPercent(sWorld.getConfig(CONFIG_UINT32_ENCHANT_COMPREHENSION_ENCHANT_CAST_CHANCE)))
        return;
    if (LearnRank(player, learn))
        ChatHandler(player).PSendSysMessage(LANG_ENCHANT_COMPREHEND_SUCCESS);
}
