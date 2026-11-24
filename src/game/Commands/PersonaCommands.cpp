#include "Chat.h"
#include "Creature.h"
#include "CreaturePersona.h"
#include "CreaturePersonaMapping.h"
#include "CreaturePersonaTrace.h"
#include "Language.h"
#include "SpellEntry.h"
#include <cstring>
#include <sstream>

namespace
{
char const* PowerTypeName(Powers p)
{
    switch (p)
    {
        case POWER_MANA: return "Mana";
        case POWER_RAGE: return "Rage";
        case POWER_FOCUS: return "Focus";
        case POWER_ENERGY: return "Energy";
        case POWER_HAPPINESS: return "Happiness";
        default: return "Unknown";
    }
}
} // namespace

bool ChatHandler::HandlePersonaInfoCommand(char* /*args*/)
{
    Creature* target = GetSelectedCreature();
    if (!target)
    {
        SendSysMessage(LANG_SELECT_CREATURE);
        SetSentErrorMessage(true);
        return false;
    }

    CreatureInfo const* cinfo = target->GetCreatureInfo();
    PersonaMapping const map = CreaturePersonaMapping::Resolve(cinfo);
    bool const gate = CreaturePersona::PassesBaseGate(target);
    CreaturePersona const* persona = target->GetPersona();

    PSendSysMessage("Persona: %s (entry %u) guid %s",
        cinfo->name.c_str(), target->GetEntry(), target->GetGuidStr().c_str());
    PSendSysMessage("  level %u  unit_class %u  spell_list %u",
        target->GetLevel(), cinfo->unit_class, cinfo->spell_list_id);
    PSendSysMessage("  mapping: %s / %s  source=%s  implemented=%s",
        CreaturePersonaMapping::ClassName(map.personaClass),
        CreaturePersonaMapping::SpecName(map.spec),
        CreaturePersonaMapping::SourceName(map.source),
        CreaturePersonaMapping::IsImplemented(map.personaClass) ? "yes" : "no");
    PSendSysMessage("  base_gate=%s  attached=%s",
        gate ? "pass" : "fail",
        persona ? "yes" : "no");

    if (!persona)
        return true;

    PSendSysMessage("  live: %s / %s",
        CreaturePersonaMapping::ClassName(persona->GetPersonaClass()),
        CreaturePersonaMapping::SpecName(persona->GetSpec()));

    Powers const pt = target->GetPowerType();
    PSendSysMessage("  power: %s %u/%u  combo=%u",
        PowerTypeName(pt), target->GetPower(pt), target->GetMaxPower(pt),
        uint32(persona->GetComboPoints()));

    std::ostringstream spells;
    persona->AppendSpellInfo(spells);
    if (spells.str().empty())
        SendSysMessage("  spells: (none learned for level/filters)");
    else
    {
        SendSysMessage("  spells:");
        std::string const blob = spells.str();
        size_t start = 0;
        while (start < blob.size())
        {
            size_t end = blob.find('\n', start);
            if (end == std::string::npos)
                end = blob.size();
            std::string line = blob.substr(start, end - start);
            if (!line.empty())
                SendSysMessage(line.c_str());
            start = end + 1;
        }
    }
    return true;
}

bool ChatHandler::HandlePersonaTraceCommand(char* args)
{
    if (!args || !*args)
    {
        SendSysMessage(CreaturePersonaTrace::Status().c_str());
        SendSysMessage("usage: .persona trace <entry> on|off | .persona trace clear");
        return true;
    }

    char* arg1 = strtok(args, " ");
    if (!arg1)
    {
        SendSysMessage(CreaturePersonaTrace::Status().c_str());
        return true;
    }

    if (!strcmp(arg1, "clear") || !strcmp(arg1, "status"))
    {
        if (!strcmp(arg1, "clear"))
            CreaturePersonaTrace::Clear();
        SendSysMessage(CreaturePersonaTrace::Status().c_str());
        return true;
    }

    uint32 const entry = uint32(strtoul(arg1, nullptr, 10));
    if (!entry)
    {
        SendSysMessage("usage: .persona trace <entry> on|off | .persona trace clear");
        SetSentErrorMessage(true);
        return false;
    }

    char* arg2 = strtok(nullptr, " ");
    if (!arg2)
    {
        PSendSysMessage("persona trace %u: %s", entry,
            CreaturePersonaTrace::IsEntry(entry) ? "on" : "off");
        return true;
    }

    bool enable = false;
    if (!strcmp(arg2, "on") || !strcmp(arg2, "1"))
        enable = true;
    else if (!strcmp(arg2, "off") || !strcmp(arg2, "0"))
        enable = false;
    else
    {
        SendSysMessage("usage: .persona trace <entry> on|off");
        SetSentErrorMessage(true);
        return false;
    }

    CreaturePersonaTrace::SetEntry(entry, enable);
    PSendSysMessage("persona trace %u: %s (logs/persona/%u_<guid>.log)",
        entry, enable ? "on" : "off", entry);
    return true;
}
