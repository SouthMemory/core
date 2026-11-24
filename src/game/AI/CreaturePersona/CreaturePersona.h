#ifndef MANGOS_CREATURE_PERSONA_H
#define MANGOS_CREATURE_PERSONA_H

#include "Common.h"
#include "CreaturePersonaMapping.h"
#include <sstream>

class Creature;
class SpellEntry;
class Unit;

#define CREATURE_PERSONA_CAST_DELAY 1200

class CreaturePersona
{
public:
    explicit CreaturePersona(Creature* owner, uint8 personaClass, PersonaSpec spec = PERSONA_SPEC_NONE)
        : m_owner(owner), m_castTimer(0), m_rageCarryMs(0), m_energyCarryMs(0),
          m_personaClass(personaClass), m_spec(spec), m_comboPoints(0) {}
    virtual ~CreaturePersona() = default;

    static CreaturePersona* CreateIfEligible(Creature* c);
    static bool PassesBaseGate(Creature const* c);

    void Update(uint32 diff);
    virtual void OnEnterCombat();
    PersonaSpec GetSpec() const { return m_spec; }
    uint8 GetPersonaClass() const { return m_personaClass; }
    uint8 GetComboPoints() const { return m_comboPoints; }
    void AddComboPoints(int8 count);
    void ClearComboPoints();
    virtual void AppendSpellInfo(std::ostringstream& os) const = 0;

protected:
    virtual void UpdateCombat() = 0;
    virtual void OnUpdate(uint32 /*diff*/) {}
    bool CanAttemptCast() const;
    bool TryCast(Unit* target, SpellEntry const* spell);
    void GainRage(int32 amount);
    void GainEnergy(int32 amount);
    void EnsureRagePool();
    void EnsureManaPool();
    void EnsureEnergyPool();
    void AppendSpellLine(std::ostringstream& os, char const* label, SpellEntry const* spell) const;
    void Trace(char const* fmt, ...) const ATTR_PRINTF(2, 3);
    bool Tracing() const;

    Creature* m_owner;
    uint32 m_castTimer;
    uint32 m_rageCarryMs;
    uint32 m_energyCarryMs;
    uint8 m_personaClass;
    PersonaSpec m_spec;
    uint8 m_comboPoints;
};

#endif
