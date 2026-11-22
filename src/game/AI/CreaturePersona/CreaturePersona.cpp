#include "CreaturePersona.h"
#include "CreaturePersonaWarrior.h"
#include "Creature.h"
#include "World.h"
#include "SpellEntry.h"
#include <algorithm>

CreaturePersona* CreaturePersona::CreateIfEligible(Creature* c)
{
    if (!IsEligible(c))
        return nullptr;

    if (c->GetClass() == CLASS_WARRIOR)
        return new CreaturePersonaWarrior(c, BuildWarriorSpellbook(c));

    return nullptr;
}

bool CreaturePersona::IsEligible(Creature const* c)
{
    if (!c || !sWorld.getConfig(CONFIG_BOOL_CREATURE_PERSONA_ENABLE))
        return false;
    if (c->IsPet() || c->IsTotem() || c->GetCreatureType() == CREATURE_TYPE_CRITTER)
        return false;
    if (c->GetCreatureType() != CREATURE_TYPE_HUMANOID)
        return false;
    if (c->GetClass() != CLASS_WARRIOR)
        return false;
    if (c->GetPowerType() != POWER_RAGE)
        return false;
    if (c->IsCivilian() || c->IsServiceProvider() || c->IsSpiritService())
        return false;
    return true;
}

void CreaturePersona::Update(uint32 diff)
{
    OnUpdate(diff);

    if (!m_owner->IsInCombat() || !m_owner->GetVictim())
    {
        m_castTimer = 0;
        m_rageCarryMs = 0;
        return;
    }

    if (m_owner->CanReachWithMeleeAutoAttack(m_owner->GetVictim()))
    {
        // 7 rage/sec; carry remainder so short diffs don't truncate to 0
        m_rageCarryMs += diff * 7;
        if (uint32 const add = m_rageCarryMs / 1000)
        {
            m_rageCarryMs %= 1000;
            GainRage(int32(add));
        }
    }

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
    EnsureRagePool();
    GainRage(25);
}

bool CreaturePersona::CanAttemptCast() const
{
    return !m_owner->IsNonMeleeSpellCasted(false, false, true)
        && !m_owner->HasUnitState(UNIT_STATE_STUNNED | UNIT_STATE_CONFUSED | UNIT_STATE_FLEEING | UNIT_STATE_PENDING_STUNNED);
}

bool CreaturePersona::TryCast(Unit* target, SpellEntry const* spell)
{
    if (!spell || !target)
        return false;
    if (!m_owner->IsSpellReady(spell))
        return false;
    return m_owner->TryToCast(target, spell, 0, 100) == SPELL_CAST_OK;
}

void CreaturePersona::EnsureRagePool()
{
    uint32 const cap = m_owner->GetCreatePowers(POWER_RAGE);
    uint32 const maxRage = cap ? cap : 1000;
    if (m_owner->GetPowerType() != POWER_RAGE)
        m_owner->SetPowerType(POWER_RAGE);
    // Bind into UNIT_MOD so UpdateAllStats cannot wipe max rage to 0
    m_owner->SetModifierValue(UNIT_MOD_RAGE, BASE_VALUE, float(maxRage));
    if (m_owner->GetMaxPower(POWER_RAGE) != maxRage)
        m_owner->SetMaxPower(POWER_RAGE, maxRage);
}

void CreaturePersona::GainRage(int32 amount)
{
    if (amount <= 0 || m_owner->GetPowerType() != POWER_RAGE)
        return;
    EnsureRagePool();
    // classic stores rage *10 (100 rage => 1000)
    int32 add = amount * 10;
    int32 cur = m_owner->GetPower(POWER_RAGE);
    int32 max = m_owner->GetMaxPower(POWER_RAGE);
    if (max <= 0)
        max = 1000;
    m_owner->SetPower(POWER_RAGE, std::min(cur + add, max));
}
