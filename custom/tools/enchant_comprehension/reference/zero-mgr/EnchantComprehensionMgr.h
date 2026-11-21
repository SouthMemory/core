/**
 * SPDX-License-Identifier: GPL-3.0-or-later
 *
 * Copyright (C) 2005-2026 MaNGOS <https://www.getmangos.eu>
 */

#ifndef MANGOS_H_ENCHANTCOMPREHENSIONMGR
#define MANGOS_H_ENCHANTCOMPREHENSIONMGR

#include "Platform/Define.h"
#include "Policies/Singleton.h"
#include <unordered_map>
#include <unordered_set>
#include <vector>

class Player;
struct ItemPrototype;

class EnchantComprehensionMgr
{
    public:
        void Load();
        void TryAfterDisenchant(Player* player, ItemPrototype const* proto, uint32 permEnchantId);
        void TryAfterEnchantCast(Player* player, uint32 formulaSpellId, uint32 appliedEnchantId);
        uint32 GetProcIcdMs(uint32 enchantId) const;
        bool LearnRank(Player* player, uint32 formulaSpell);
        bool IsLineFormula(uint32 formulaSpell) const;
        bool IsLineEnchant(uint32 enchantId) const;

    private:
        struct Rank
        {
            uint32 lineId;
            uint8 direction;
            uint8 rank;
            uint32 formula;
            uint32 enchantId;
            uint32 procSpell;
            uint32 icdMs;
        };

        struct Line
        {
            uint32 baseSpell;
            uint8 axisKind;
            std::vector<uint32> ranks;
        };

        Rank const* RankByFormula(uint32 spellId) const;
        Rank const* RankByEnchant(uint32 enchantId) const;
        Line const* LineById(uint32 lineId) const;
        Rank const* RankAt(Line const& line, uint8 direction, uint8 rank) const;
        bool IsBaseSpell(uint32 spellId) const;
        bool Covers(Player const* player, Line const& line, uint8 direction, uint8 minRank) const;
        bool MeetsDePrereq(Player const* player, Line const& line, Rank const& row) const;
        void Consider(Player const* player, uint32 formula, bool eligible, std::vector<uint32>& pool, bool& known) const;
        void CollectItemLines(Player const* player, ItemPrototype const* proto, std::vector<uint32>& pool, bool& known) const;
        void CollectPermEnchant(Player const* player, uint32 permEnchantId, std::vector<uint32>& pool, bool& known) const;
        uint32 PickDirectionEntry(Player const* player, Line const& line) const;

        std::unordered_map<uint32, Line> m_lines;
        std::vector<Rank> m_ranks;
        std::unordered_map<uint32, uint32> m_byFormula;
        std::unordered_map<uint32, uint32> m_byEnchant;
        std::unordered_map<uint32, uint32> m_lineByItemSpell;
        std::unordered_map<uint32, uint32> m_icdByEnchant;
        std::unordered_set<uint32> m_baseSpells;
};

#define sEnchantComprehensionMgr MaNGOS::Singleton<EnchantComprehensionMgr>::Instance()

#endif
