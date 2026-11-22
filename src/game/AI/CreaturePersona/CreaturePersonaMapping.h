#ifndef MANGOS_CREATURE_PERSONA_MAPPING_H
#define MANGOS_CREATURE_PERSONA_MAPPING_H

#include "Common.h"
#include "SharedDefines.h"
#include <vector>

struct CreatureInfo;

enum PersonaSpec : uint8
{
    PERSONA_SPEC_NONE = 0,
    PERSONA_SPEC_WARRIOR_ARMS,
    PERSONA_SPEC_WARRIOR_FURY,
    PERSONA_SPEC_WARRIOR_PROT,
    PERSONA_SPEC_PALADIN_HOLY,
    PERSONA_SPEC_PALADIN_PROT,
    PERSONA_SPEC_PALADIN_RET,
    PERSONA_SPEC_HUNTER_BEAST,
    PERSONA_SPEC_HUNTER_MARKS,
    PERSONA_SPEC_HUNTER_SURVIVAL,
    PERSONA_SPEC_ROGUE_ASSA,
    PERSONA_SPEC_ROGUE_COMBAT,
    PERSONA_SPEC_ROGUE_SUBTLETY,
    PERSONA_SPEC_PRIEST_DISC,
    PERSONA_SPEC_PRIEST_HOLY,
    PERSONA_SPEC_PRIEST_SHADOW,
    PERSONA_SPEC_SHAMAN_ELE,
    PERSONA_SPEC_SHAMAN_ENH,
    PERSONA_SPEC_SHAMAN_RESTO,
    PERSONA_SPEC_MAGE_ARCANE,
    PERSONA_SPEC_MAGE_FIRE,
    PERSONA_SPEC_MAGE_FROST,
    PERSONA_SPEC_WARLOCK_AFFLICTION,
    PERSONA_SPEC_WARLOCK_DEMONOLOGY,
    PERSONA_SPEC_WARLOCK_DESTRUCTION,
    PERSONA_SPEC_DRUID_BALANCE,
    PERSONA_SPEC_DRUID_FERAL,
    PERSONA_SPEC_DRUID_RESTO,
};

enum PersonaMappingSource : uint8
{
    PERSONA_MAP_NONE = 0,
    PERSONA_MAP_OVERRIDE,
    PERSONA_MAP_TABLE,
    PERSONA_MAP_RULES,
};

struct PersonaMapping
{
    uint8 personaClass = 0; // CLASS_* or 0
    PersonaSpec spec = PERSONA_SPEC_NONE;
    PersonaMappingSource source = PERSONA_MAP_NONE;
};

namespace CreaturePersonaMapping
{
void LoadFromDB();
PersonaMapping Resolve(CreatureInfo const* cinfo);
PersonaMapping EvaluateRules(CreatureInfo const* cinfo);
std::vector<PersonaSpec> SpecsFor(uint8 personaClass);
PersonaSpec PickRandomSpec(uint8 personaClass);
bool IsImplemented(uint8 personaClass);
char const* ClassName(uint8 personaClass);
char const* SpecName(PersonaSpec spec);
char const* SourceName(PersonaMappingSource src);
}

#endif
