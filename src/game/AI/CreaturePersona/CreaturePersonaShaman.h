#ifndef MANGOS_CREATURE_PERSONA_SHAMAN_H
#define MANGOS_CREATURE_PERSONA_SHAMAN_H

#include "CreaturePersona.h"

struct CreaturePersonaShamanSpells
{
    SpellEntry const* stormstrike = nullptr;
    SpellEntry const* earthShock = nullptr;
    SpellEntry const* flameShock = nullptr;
    SpellEntry const* frostShock = nullptr;
    SpellEntry const* lightningShield = nullptr;
    SpellEntry const* lightningBolt = nullptr;
    SpellEntry const* purge = nullptr;
    SpellEntry const* healingWave = nullptr;
    SpellEntry const* lesserHealingWave = nullptr;
};

class CreaturePersonaShaman : public CreaturePersona
{
public:
    explicit CreaturePersonaShaman(Creature* owner, CreaturePersonaShamanSpells const& spells,
                                   uint8 personaClass, PersonaSpec spec = PERSONA_SPEC_NONE);

    void OnEnterCombat() override;
    void UpdateCombat() override;
    void AppendSpellInfo(std::ostringstream& os) const override;

private:
    bool Cast(Unit* target, SpellEntry const* spell);
    CreaturePersonaShamanSpells m_spells;
};

CreaturePersonaShamanSpells BuildShamanSpellbook(Creature const* c);

#endif
