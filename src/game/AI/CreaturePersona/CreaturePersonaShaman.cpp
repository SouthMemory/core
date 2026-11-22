#include "CreaturePersonaShaman.h"
#include "Creature.h"
#include "CreatureEventAI.h"
#include "CreatureEventAIMgr.h"
#include "ObjectMgr.h"
#include "SpellMgr.h"
#include "ScriptMgr.h"
#include "SharedDefines.h"
#include "SpellAuraDefines.h"
#include "SpellAuras.h"
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

bool HasMagicBuff(Unit const* u)
{
    for (auto const& pair : u->GetSpellAuraHolderMap())
    {
        SpellAuraHolder const* h = pair.second;
        if (!h || !h->IsPositive())
            continue;
        if (h->GetSpellProto()->Dispel == DISPEL_MAGIC)
            return true;
    }
    return false;
}
} // namespace

CreaturePersonaShamanSpells BuildShamanSpellbook(Creature const* c)
{
    uint32 const level = c->GetLevel();
    uint32 nativeMask = 0;
    bool const stripControl = !c->GetScriptName().empty() || c->GetScriptId() != 0;
    if (!stripControl)
        CollectNativeMechanics(c, nativeMask);

    auto pick = [&](uint32 const* ranks) {
        return FilterSpell(PickRank(ranks, level), nativeMask, stripControl);
    };

    static uint32 const Stormstrike[] = { 17364, 0 };
    static uint32 const EarthShock[] = { 8042, 8044, 8045, 8046, 10412, 10413, 10414, 0 };
    static uint32 const FlameShock[] = { 8050, 8052, 8053, 10447, 10448, 29228, 0 };
    static uint32 const FrostShock[] = { 8056, 8058, 10472, 10473, 0 };
    static uint32 const LightningShield[] = { 324, 325, 905, 945, 8134, 10431, 10432, 0 };
    static uint32 const LightningBolt[] = { 403, 529, 548, 915, 943, 6041, 10391, 10392, 15207, 15208, 0 };
    static uint32 const Purge[] = { 370, 8012, 0 };
    static uint32 const HealingWave[] = { 331, 332, 547, 913, 939, 959, 8005, 10395, 10396, 25357, 0 };
    static uint32 const LesserHealingWave[] = { 8004, 8008, 8010, 10466, 10467, 10468, 0 };

    CreaturePersonaShamanSpells s;
    s.stormstrike = pick(Stormstrike);
    s.earthShock = pick(EarthShock);
    s.flameShock = pick(FlameShock);
    s.frostShock = pick(FrostShock);
    s.lightningShield = PickRank(LightningShield, level);
    s.lightningBolt = pick(LightningBolt);
    s.purge = pick(Purge);
    s.healingWave = PickRank(HealingWave, level);
    s.lesserHealingWave = PickRank(LesserHealingWave, level);
    return s;
}

CreaturePersonaShaman::CreaturePersonaShaman(Creature* owner, CreaturePersonaShamanSpells const& spells,
                                             uint8 personaClass, PersonaSpec spec)
    : CreaturePersona(owner, personaClass, spec), m_spells(spells)
{
    EnsureManaPool();
}

void CreaturePersonaShaman::AppendSpellInfo(std::ostringstream& os) const
{
    AppendSpellLine(os, "Stormstrike", m_spells.stormstrike);
    AppendSpellLine(os, "Earth Shock", m_spells.earthShock);
    AppendSpellLine(os, "Flame Shock", m_spells.flameShock);
    AppendSpellLine(os, "Frost Shock", m_spells.frostShock);
    AppendSpellLine(os, "Lightning Shield", m_spells.lightningShield);
    AppendSpellLine(os, "Lightning Bolt", m_spells.lightningBolt);
    AppendSpellLine(os, "Purge", m_spells.purge);
    AppendSpellLine(os, "Healing Wave", m_spells.healingWave);
    AppendSpellLine(os, "Lesser Healing Wave", m_spells.lesserHealingWave);
}

void CreaturePersonaShaman::OnEnterCombat()
{
    EnsureManaPool();
    Trace("OnEnterCombat mana=%u/%u", m_owner->GetPower(POWER_MANA), m_owner->GetMaxPower(POWER_MANA));
}

bool CreaturePersonaShaman::Cast(Unit* target, SpellEntry const* spell)
{
    return TryCast(target, spell);
}

void CreaturePersonaShaman::UpdateCombat()
{
    Unit* victim = m_owner->GetVictim();
    if (!victim)
        return;

    EnsureManaPool();

    bool const melee = m_owner->CanReachWithMeleeAutoAttack(victim);
    if (Tracing())
        Trace("tick melee=%d hp=%.0f mana=%u/%u moving=%d casting=%d",
            int(melee), m_owner->GetHealthPercent(),
            m_owner->GetPower(POWER_MANA), m_owner->GetMaxPower(POWER_MANA),
            int(victim->IsMoving()),
            int(victim->IsNonMeleeSpellCasted(false, false, true)));

    if (m_spells.lightningShield && !m_owner->HasAura(m_spells.lightningShield->Id))
    {
        if (Cast(m_owner, m_spells.lightningShield))
            return;
    }
    else if (Tracing() && m_spells.lightningShield)
        Trace("skip Lightning Shield: aura up");
    else if (Tracing())
        Trace("skip Lightning Shield: not learned");

    if (m_spells.earthShock && victim->IsNonMeleeSpellCasted(false, false, true))
    {
        if (Cast(victim, m_spells.earthShock))
            return;
    }
    else if (Tracing() && m_spells.earthShock)
        Trace("skip Earth Shock interrupt: victim not casting");
    else if (Tracing())
        Trace("skip Earth Shock interrupt: not learned");

    if (m_spells.frostShock && victim->IsMoving())
    {
        if (Cast(victim, m_spells.frostShock))
            return;
    }
    else if (Tracing() && m_spells.frostShock)
        Trace("skip Frost Shock: victim not moving");
    else if (Tracing())
        Trace("skip Frost Shock: not learned");

    if (m_spells.stormstrike)
    {
        if (Cast(victim, m_spells.stormstrike))
            return;
    }
    else if (Tracing())
        Trace("skip Stormstrike: not learned");

    if (m_spells.purge && HasMagicBuff(victim))
    {
        if (Cast(victim, m_spells.purge))
            return;
    }
    else if (Tracing() && m_spells.purge)
        Trace("skip Purge: no magic buff");
    else if (Tracing())
        Trace("skip Purge: not learned");

    if (m_spells.flameShock && !victim->HasAura(m_spells.flameShock->Id))
    {
        if (Cast(victim, m_spells.flameShock))
            return;
    }
    else if (Tracing() && m_spells.flameShock)
        Trace("skip Flame Shock: aura up");
    else if (Tracing())
        Trace("skip Flame Shock: not learned");

    if (m_spells.lightningBolt && !melee)
    {
        if (Cast(victim, m_spells.lightningBolt))
            return;
    }
    else if (Tracing() && m_spells.lightningBolt)
        Trace("skip Lightning Bolt: in melee");
    else if (Tracing())
        Trace("skip Lightning Bolt: not learned");

    if (m_owner->GetHealthPercent() < 30.0f)
    {
        if (m_spells.lesserHealingWave && Cast(m_owner, m_spells.lesserHealingWave))
            return;
        if (m_spells.healingWave && Cast(m_owner, m_spells.healingWave))
            return;
        if (Tracing())
            Trace("skip heal: cast failed");
    }
    else if (Tracing())
        Trace("skip heal: hp>=30 (hw=%d lhw=%d)",
            int(m_spells.healingWave != nullptr), int(m_spells.lesserHealingWave != nullptr));

    if (m_spells.earthShock)
    {
        if (Cast(victim, m_spells.earthShock))
            return;
    }
    else if (Tracing())
        Trace("skip Earth Shock filler: not learned");

    Trace("tick: no action");
}
