#ifndef MANGOS_CREATURE_PERSONA_H
#define MANGOS_CREATURE_PERSONA_H

#include "Common.h"

class Creature;
class SpellEntry;
class Unit;

#define CREATURE_PERSONA_CAST_DELAY 1200

class CreaturePersona
{
public:
    explicit CreaturePersona(Creature* owner) : m_owner(owner), m_castTimer(0), m_rageCarryMs(0) {}
    virtual ~CreaturePersona() = default;

    static CreaturePersona* CreateIfEligible(Creature* c);
    static bool IsEligible(Creature const* c);

    void Update(uint32 diff);
    virtual void OnEnterCombat();

protected:
    virtual void UpdateCombat() = 0;
    virtual void OnUpdate(uint32 /*diff*/) {}
    bool CanAttemptCast() const;
    bool TryCast(Unit* target, SpellEntry const* spell);
    void GainRage(int32 amount);
    void EnsureRagePool();

    Creature* m_owner;
    uint32 m_castTimer;
    uint32 m_rageCarryMs; // fractional rage accrual (ms * rate)
};

#endif
