#ifndef MANGOS_CREATURE_PERSONA_TRACE_H
#define MANGOS_CREATURE_PERSONA_TRACE_H

#include "Common.h"
#include <string>

class Creature;

namespace CreaturePersonaTrace
{
bool IsEntry(uint32 entry);
void SetEntry(uint32 entry, bool enable);
void Clear();
std::string Status();
void Log(Creature const* c, char const* fmt, ...) ATTR_PRINTF(2, 3);
}

#endif
