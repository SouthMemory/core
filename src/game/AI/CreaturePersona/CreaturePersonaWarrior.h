#ifndef MANGOS_CREATURE_PERSONA_WARRIOR_H
#define MANGOS_CREATURE_PERSONA_WARRIOR_H

#include "CreaturePersona.h"
#include "SharedDefines.h"

struct CreaturePersonaWarriorSpells
{
    SpellEntry const* battleStance = nullptr;
    SpellEntry const* defensiveStance = nullptr;
    SpellEntry const* berserkerStance = nullptr;
    SpellEntry const* charge = nullptr;
    SpellEntry const* intercept = nullptr;
    SpellEntry const* overpower = nullptr;
    SpellEntry const* heroicStrike = nullptr;
    SpellEntry const* cleave = nullptr;
    SpellEntry const* execute = nullptr;
    SpellEntry const* mortalStrike = nullptr;
    SpellEntry const* bloodthirst = nullptr;
    SpellEntry const* bloodrage = nullptr;
    SpellEntry const* berserkerRage = nullptr;
    SpellEntry const* recklessness = nullptr;
    SpellEntry const* retaliation = nullptr;
    SpellEntry const* deathWish = nullptr;
    SpellEntry const* intimidatingShout = nullptr;
    SpellEntry const* pummel = nullptr;
    SpellEntry const* rend = nullptr;
    SpellEntry const* disarm = nullptr;
    SpellEntry const* whirlwind = nullptr;
    SpellEntry const* battleShout = nullptr;
    SpellEntry const* demoShout = nullptr;
    SpellEntry const* hamstring = nullptr;
    SpellEntry const* thunderClap = nullptr;
    SpellEntry const* sweepingStrikes = nullptr;
    SpellEntry const* mockingBlow = nullptr;
    SpellEntry const* concussionBlow = nullptr;
};

class CreaturePersonaWarrior : public CreaturePersona
{
public:
    explicit CreaturePersonaWarrior(Creature* owner, CreaturePersonaWarriorSpells const& spells,
                                    uint8 personaClass, PersonaSpec spec = PERSONA_SPEC_NONE);

    void OnEnterCombat() override;
    void UpdateCombat() override;
    void OnUpdate(uint32 diff) override;
    void AppendSpellInfo(std::ostringstream& os) const override;

private:
    bool Cast(Unit* target, SpellEntry const* spell);
    // true = spent this tick switching (caller must return)
    bool SwitchToStance(ShapeshiftForm form, bool urgent = false);
    SpellEntry const* StanceSpell(ShapeshiftForm form) const;
    ShapeshiftForm ChooseStance(Unit* victim) const;

    CreaturePersonaWarriorSpells m_spells;
    uint32 m_stanceLockMs = 0;
};

CreaturePersonaWarriorSpells BuildWarriorSpellbook(Creature const* c);

#endif
