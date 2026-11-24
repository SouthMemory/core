#include "CreaturePersonaRogue.h"
#include "Creature.h"
#include "CreatureEventAI.h"
#include "CreatureEventAIMgr.h"
#include "ObjectMgr.h"
#include "SpellMgr.h"
#include "ScriptMgr.h"
#include "SharedDefines.h"
#include "SpellAuraDefines.h"
#include "SpellEntry.h"

namespace
{
uint32 const CONTROL_MECHANIC_MASK =
    (1 << (MECHANIC_CHARM - 1)) | (1 << (MECHANIC_DISORIENTED - 1)) | (1 << (MECHANIC_FEAR - 1)) |
    (1 << (MECHANIC_STUN - 1)) | (1 << (MECHANIC_SLEEP - 1)) | (1 << (MECHANIC_ROOT - 1)) |
    (1 << (MECHANIC_SILENCE - 1)) | (1 << (MECHANIC_DISARM - 1)) | (1 << (MECHANIC_KNOCKOUT - 1)) |
    (1 << (MECHANIC_FREEZE - 1)) | (1 << (MECHANIC_BANISH - 1)) | (1 << (MECHANIC_POLYMORPH - 1));

SpellEntry const* PickRank(uint32 const* ranks, uint32 level)
{
    SpellEntry const* best = nullptr;
    for (uint32 i = 0; ranks[i]; ++i)
    {
        SpellEntry const* sp = sSpellMgr.GetSpellEntry(ranks[i]);
        if (!sp)
            continue;
        if (sp->spellLevel <= level)
            best = sp;
    }
    return best;
}

bool IsControlSpell(SpellEntry const* sp)
{
    return sp && (sp->GetAllSpellMechanicMask() & CONTROL_MECHANIC_MASK) != 0;
}

void CollectNativeMechanics(Creature const* c, uint32& mechanicMask)
{
    if (uint32 listId = c->GetCreatureInfo()->spell_list_id)
    {
        if (CreatureSpellsList const* list = sObjectMgr.GetCreatureSpellsList(listId))
        {
            for (auto const& e : *list)
            {
                if (SpellEntry const* sp = sSpellMgr.GetSpellEntry(e.spellId))
                    mechanicMask |= sp->GetAllSpellMechanicMask() & CONTROL_MECHANIC_MASK;
            }
        }
    }

    auto const& aiMap = sEventAIMgr.GetCreatureEventAIMap();
    auto it = aiMap.find(c->GetEntry());
    if (it == aiMap.end())
        return;

    for (auto const& ev : it->second)
    {
        for (uint32 i = 0; i < MAX_ACTIONS; ++i)
        {
            ScriptMap* sm = ev.action[i];
            if (!sm)
                continue;
            for (auto const& pair : *sm)
            {
                ScriptInfo const& si = pair.second;
                if (si.command != SCRIPT_COMMAND_CAST_SPELL)
                    continue;
                if (SpellEntry const* sp = sSpellMgr.GetSpellEntry(si.castSpell.spellId))
                    mechanicMask |= sp->GetAllSpellMechanicMask() & CONTROL_MECHANIC_MASK;
            }
        }
    }
}

SpellEntry const* FilterSpell(SpellEntry const* sp, uint32 nativeMask, bool stripAllControl)
{
    if (!sp)
        return nullptr;
    if (stripAllControl && IsControlSpell(sp))
        return nullptr;
    if (!stripAllControl && (sp->GetAllSpellMechanicMask() & nativeMask))
        return nullptr;
    return sp;
}
} // namespace

CreaturePersonaRogueSpells BuildRogueSpellbook(Creature const* c)
{
    uint32 const level = c->GetLevel();
    uint32 nativeMask = 0;
    bool const stripControl = !c->GetScriptName().empty() || c->GetScriptId() != 0;
    if (!stripControl)
        CollectNativeMechanics(c, nativeMask);

    auto pick = [&](uint32 const* ranks) {
        return FilterSpell(PickRank(ranks, level), nativeMask, stripControl);
    };

    static uint32 const SinisterStrike[] = { 1752, 1757, 1758, 1759, 1760, 8621, 11293, 11294, 0 };
    static uint32 const Eviscerate[] = { 2098, 6760, 6761, 6762, 8623, 8624, 11299, 11300, 31016, 0 };
    static uint32 const SliceAndDice[] = { 5171, 6774, 0 };
    static uint32 const Rupture[] = { 1943, 8639, 8640, 11273, 11274, 11275, 0 };
    static uint32 const Kick[] = { 1766, 1767, 1768, 1769, 0 };
    static uint32 const BladeFlurry[] = { 13877, 0 };
    static uint32 const AdrenalineRush[] = { 13750, 0 };

    CreaturePersonaRogueSpells s;
    s.sinisterStrike = pick(SinisterStrike);
    s.eviscerate = pick(Eviscerate);
    s.sliceAndDice = PickRank(SliceAndDice, level);
    s.rupture = pick(Rupture);
    s.kick = pick(Kick);
    s.bladeFlurry = (level >= 30) ? PickRank(BladeFlurry, level) : nullptr;
    s.adrenalineRush = (level >= 40) ? PickRank(AdrenalineRush, level) : nullptr;
    return s;
}

CreaturePersonaRogue::CreaturePersonaRogue(Creature* owner, CreaturePersonaRogueSpells const& spells,
                                           uint8 personaClass, PersonaSpec spec)
    : CreaturePersona(owner, personaClass, spec), m_spells(spells)
{
    EnsureEnergyPool();
}

void CreaturePersonaRogue::AppendSpellInfo(std::ostringstream& os) const
{
    AppendSpellLine(os, "Sinister Strike", m_spells.sinisterStrike);
    AppendSpellLine(os, "Eviscerate", m_spells.eviscerate);
    AppendSpellLine(os, "Slice and Dice", m_spells.sliceAndDice);
    AppendSpellLine(os, "Rupture", m_spells.rupture);
    AppendSpellLine(os, "Kick", m_spells.kick);
    AppendSpellLine(os, "Blade Flurry", m_spells.bladeFlurry);
    AppendSpellLine(os, "Adrenaline Rush", m_spells.adrenalineRush);
}

void CreaturePersonaRogue::OnEnterCombat()
{
    EnsureEnergyPool();
    ClearComboPoints();
    Trace("OnEnterCombat energy=%u/%u", m_owner->GetPower(POWER_ENERGY), m_owner->GetMaxPower(POWER_ENERGY));
}

bool CreaturePersonaRogue::Cast(Unit* target, SpellEntry const* spell)
{
    return TryCast(target, spell);
}

void CreaturePersonaRogue::UpdateCombat()
{
    Unit* victim = m_owner->GetVictim();
    if (!victim)
        return;

    EnsureEnergyPool();
    uint8 const cp = GetComboPoints();

    if (Tracing())
        Trace("tick melee=%d hp=%.0f energy=%u/%u cp=%u casting=%d",
            int(m_owner->CanReachWithMeleeAutoAttack(victim)),
            m_owner->GetHealthPercent(),
            m_owner->GetPower(POWER_ENERGY), m_owner->GetMaxPower(POWER_ENERGY),
            uint32(cp), int(victim->IsNonMeleeSpellCasted(false, false, true)));

    if (m_spells.kick && victim->IsNonMeleeSpellCasted(false, false, true))
    {
        if (Cast(victim, m_spells.kick))
            return;
    }
    else if (Tracing() && !m_spells.kick)
        Trace("skip Kick: not learned");

    if (m_spells.adrenalineRush && m_owner->GetHealthPercent() < 40.0f &&
        !m_owner->HasAura(m_spells.adrenalineRush->Id))
    {
        if (Cast(m_owner, m_spells.adrenalineRush))
            return;
    }

    if (m_spells.bladeFlurry && m_owner->GetAttackers().size() > 1 &&
        !m_owner->HasAura(m_spells.bladeFlurry->Id))
    {
        if (Cast(m_owner, m_spells.bladeFlurry))
            return;
    }

    if (m_spells.sliceAndDice && cp >= 2 && !m_owner->HasAura(m_spells.sliceAndDice->Id))
    {
        if (Cast(m_owner, m_spells.sliceAndDice))
            return;
    }
    else if (Tracing() && m_spells.sliceAndDice && cp < 2)
        Trace("skip Slice and Dice: cp<%u", uint32(cp));
    else if (Tracing() && m_spells.sliceAndDice)
        Trace("skip Slice and Dice: aura up");

    if (m_spells.eviscerate && (cp >= 4 || (cp >= 2 && victim->GetHealthPercent() < 20.0f)))
    {
        if (Cast(victim, m_spells.eviscerate))
            return;
    }

    if (m_spells.rupture && cp >= 3 && !victim->HasAura(m_spells.rupture->Id))
    {
        if (Cast(victim, m_spells.rupture))
            return;
    }

    if (m_spells.sinisterStrike)
    {
        if (Cast(victim, m_spells.sinisterStrike))
            return;
    }
    else if (Tracing())
        Trace("skip Sinister Strike: not learned");

    Trace("tick: no action");
}
