#include "CreaturePersona.h"
#include "CreaturePersonaWarrior.h"
#include "CreaturePersonaShaman.h"
#include "CreaturePersonaMapping.h"
#include "CreaturePersonaTrace.h"
#include "Creature.h"
#include "ObjectMgr.h"
#include "World.h"
#include "SpellEntry.h"
#include <algorithm>
#include <cstdarg>
#include <cmath>

CreaturePersona* CreaturePersona::CreateIfEligible(Creature* c)
{
    if (!PassesBaseGate(c))
        return nullptr;

    PersonaMapping const map = CreaturePersonaMapping::Resolve(c->GetCreatureInfo());
    if (!map.personaClass || !CreaturePersonaMapping::IsImplemented(map.personaClass))
        return nullptr;

    PersonaSpec spec = map.spec;
    if (spec == PERSONA_SPEC_NONE && sWorld.getConfig(CONFIG_BOOL_CREATURE_PERSONA_RANDOM_SPEC))
        spec = CreaturePersonaMapping::PickRandomSpec(map.personaClass);

    switch (map.personaClass)
    {
        case CLASS_WARRIOR:
            return new CreaturePersonaWarrior(c, BuildWarriorSpellbook(c), CLASS_WARRIOR, spec);
        case CLASS_SHAMAN:
            if (spec != PERSONA_SPEC_SHAMAN_ENH)
                spec = PERSONA_SPEC_SHAMAN_ENH;
            return new CreaturePersonaShaman(c, BuildShamanSpellbook(c), CLASS_SHAMAN, spec);
        default:
            return nullptr;
    }
}

bool CreaturePersona::PassesBaseGate(Creature const* c)
{
    if (!c || !sWorld.getConfig(CONFIG_BOOL_CREATURE_PERSONA_ENABLE))
        return false;
    if (c->IsPet() || c->IsTotem() || c->GetCreatureType() == CREATURE_TYPE_CRITTER)
        return false;
    if (c->GetCreatureType() != CREATURE_TYPE_HUMANOID)
        return false;
    if (c->IsCivilian() || c->IsServiceProvider() || c->IsSpiritService())
        return false;
    return true;
}

void CreaturePersona::Update(uint32 diff)
{
    OnUpdate(diff);

    if (!m_owner->IsInCombat())
    {
        m_castTimer = 0;
        m_rageCarryMs = 0;
        return;
    }

    if (m_owner->GetPowerType() == POWER_RAGE)
    {
        m_rageCarryMs += diff * 7;
        if (uint32 const add = m_rageCarryMs / 1000)
        {
            m_rageCarryMs %= 1000;
            GainRage(int32(add));
        }
    }

    if (!m_owner->GetVictim())
        return;

    if (m_castTimer > diff)
    {
        m_castTimer -= diff;
        return;
    }

    m_castTimer = CREATURE_PERSONA_CAST_DELAY;
    if (!CanAttemptCast())
        return;

    UpdateCombat();
}

void CreaturePersona::OnEnterCombat()
{
}

bool CreaturePersona::CanAttemptCast() const
{
    return !m_owner->IsNonMeleeSpellCasted(false, false, true)
        && !m_owner->HasUnitState(UNIT_STATE_STUNNED | UNIT_STATE_CONFUSED | UNIT_STATE_FLEEING | UNIT_STATE_PENDING_STUNNED);
}

bool CreaturePersona::TryCast(Unit* target, SpellEntry const* spell)
{
    if (!spell || !target)
    {
        if (Tracing())
            Trace("TryCast abort: null spell/target");
        return false;
    }
    if (!m_owner->IsSpellReady(spell))
    {
        if (Tracing())
            Trace("skip %s (%u): cooldown", spell->SpellName[0].c_str(), spell->Id);
        return false;
    }
    SpellCastResult const rc = m_owner->TryToCast(target, spell, 0, 100);
    if (Tracing())
        Trace("%s %s (%u) -> %s : %d",
            rc == SPELL_CAST_OK ? "CAST" : "FAIL",
            spell->SpellName[0].c_str(), spell->Id,
            target == m_owner ? "self" : "victim", int32(rc));
    return rc == SPELL_CAST_OK;
}

bool CreaturePersona::Tracing() const
{
    return CreaturePersonaTrace::IsEntry(m_owner->GetEntry());
}

void CreaturePersona::Trace(char const* fmt, ...) const
{
    if (!Tracing())
        return;
    char buf[512];
    va_list ap;
    va_start(ap, fmt);
    vsnprintf(buf, sizeof(buf), fmt, ap);
    va_end(ap);
    CreaturePersonaTrace::Log(m_owner, "%s", buf);
}

void CreaturePersona::EnsureRagePool()
{
    uint32 const cap = m_owner->GetCreatePowers(POWER_RAGE);
    uint32 const maxRage = cap ? cap : 1000;
    if (m_owner->GetPowerType() != POWER_RAGE)
        m_owner->SetPowerType(POWER_RAGE);
    m_owner->SetModifierValue(UNIT_MOD_RAGE, BASE_VALUE, float(maxRage));
    if (m_owner->GetMaxPower(POWER_RAGE) != maxRage)
        m_owner->SetMaxPower(POWER_RAGE, maxRage);
}

void CreaturePersona::EnsureManaPool()
{
    if (m_owner->GetPowerType() != POWER_MANA)
        m_owner->SetPowerType(POWER_MANA);

    uint32 maxMana = m_owner->GetMaxPower(POWER_MANA);
    if (!maxMana)
    {
        CreatureClassLevelStats const* cls = sObjectMgr.GetCreatureClassLevelStats(2, m_owner->GetLevel());
        float mult = m_owner->GetCreatureInfo() ? m_owner->GetCreatureInfo()->mana_multiplier : 1.0f;
        if (cls && cls->mana > 0)
            maxMana = std::max(1u, uint32(std::round(cls->mana * mult)));
        else
            maxMana = 100u + m_owner->GetLevel() * 15u;

        m_owner->SetModifierValue(UNIT_MOD_MANA, BASE_VALUE, float(maxMana));
        m_owner->SetMaxPower(POWER_MANA, maxMana);
        m_owner->SetPower(POWER_MANA, maxMana);
        return;
    }

    m_owner->SetModifierValue(UNIT_MOD_MANA, BASE_VALUE, float(maxMana));
    if (m_owner->GetPower(POWER_MANA) == 0)
        m_owner->SetPower(POWER_MANA, maxMana);
}

void CreaturePersona::GainRage(int32 amount)
{
    if (amount <= 0 || m_owner->GetPowerType() != POWER_RAGE)
        return;
    EnsureRagePool();
    int32 add = amount * 10;
    int32 cur = m_owner->GetPower(POWER_RAGE);
    int32 max = m_owner->GetMaxPower(POWER_RAGE);
    if (max <= 0)
        max = 1000;
    m_owner->SetPower(POWER_RAGE, std::min(cur + add, max));
}

void CreaturePersona::AppendSpellLine(std::ostringstream& os, char const* label, SpellEntry const* spell) const
{
    if (!spell)
        return;
    os << "  " << label << ": " << spell->SpellName[0] << " (" << spell->Id << ")"
       << (m_owner->IsSpellReady(spell) ? " ready" : " cd") << "\n";
}
