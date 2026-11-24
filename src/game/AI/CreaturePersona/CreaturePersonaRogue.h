#ifndef MANGOS_CREATURE_PERSONA_ROGUE_H
#define MANGOS_CREATURE_PERSONA_ROGUE_H

#include "CreaturePersona.h"

struct CreaturePersonaRogueSpells
{
    SpellEntry const* sinisterStrike = nullptr;
    SpellEntry const* eviscerate = nullptr;
    SpellEntry const* sliceAndDice = nullptr;
    SpellEntry const* rupture = nullptr;
    SpellEntry const* kick = nullptr;
    SpellEntry const* bladeFlurry = nullptr;
    SpellEntry const* adrenalineRush = nullptr;
};

class CreaturePersonaRogue : public CreaturePersona
{
public:
    explicit CreaturePersonaRogue(Creature* owner, CreaturePersonaRogueSpells const& spells,
                                  uint8 personaClass, PersonaSpec spec = PERSONA_SPEC_NONE);

    void OnEnterCombat() override;
    void UpdateCombat() override;
    void AppendSpellInfo(std::ostringstream& os) const override;

private:
    bool Cast(Unit* target, SpellEntry const* spell);
    CreaturePersonaRogueSpells m_spells;
};

CreaturePersonaRogueSpells BuildRogueSpellbook(Creature const* c);

#endif
