#include "CreaturePersonaMapping.h"
#include "Creature.h"
#include "CreatureDefines.h"
#include "CreatureEventAI.h"
#include "CreatureEventAIMgr.h"
#include "Database/DatabaseEnv.h"
#include "ItemPrototype.h"
#include "Log.h"
#include "ObjectMgr.h"
#include "Maps/ScriptCommands.h"
#include "SpellDefines.h"
#include "SpellMgr.h"
#include "SpellEntry.h"
#include "Utilities/Random.h"
#include "World.h"
#include <algorithm>
#include <cctype>
#include <cstring>
#include <string>
#include <unordered_map>

namespace
{
struct MapRow
{
    uint8 personaClass = 0;
    PersonaSpec spec = PERSONA_SPEC_NONE;
    bool isOverride = false;
};

std::unordered_map<uint32, MapRow> s_mapRows;

struct Score
{
    int warlock = 0, shaman = 0, priest = 0, mage = 0, hunter = 0;
    int rogue = 0, paladin = 0, warrior = 0, druid = 0;

    void add(uint8 cls, int n)
    {
        switch (cls)
        {
            case CLASS_WARLOCK: warlock += n; break;
            case CLASS_SHAMAN: shaman += n; break;
            case CLASS_PRIEST: priest += n; break;
            case CLASS_MAGE: mage += n; break;
            case CLASS_HUNTER: hunter += n; break;
            case CLASS_ROGUE: rogue += n; break;
            case CLASS_PALADIN: paladin += n; break;
            case CLASS_WARRIOR: warrior += n; break;
            case CLASS_DRUID: druid += n; break;
            default: break;
        }
    }

    int get(uint8 cls) const
    {
        switch (cls)
        {
            case CLASS_WARLOCK: return warlock;
            case CLASS_SHAMAN: return shaman;
            case CLASS_PRIEST: return priest;
            case CLASS_MAGE: return mage;
            case CLASS_HUNTER: return hunter;
            case CLASS_ROGUE: return rogue;
            case CLASS_PALADIN: return paladin;
            case CLASS_WARRIOR: return warrior;
            case CLASS_DRUID: return druid;
            default: return 0;
        }
    }

    bool empty() const
    {
        return !(warlock || shaman || priest || mage || hunter || rogue || paladin || warrior || druid);
    }

    // tie-break: warlock > shaman > priest > mage > hunter > rogue > paladin > warrior > druid
    uint8 winner() const
    {
        static uint8 const order[] = {
            CLASS_WARLOCK, CLASS_SHAMAN, CLASS_PRIEST, CLASS_MAGE, CLASS_HUNTER,
            CLASS_ROGUE, CLASS_PALADIN, CLASS_WARRIOR, CLASS_DRUID
        };
        uint8 best = 0;
        int bestScore = 0;
        for (uint8 cls : order)
        {
            int s = get(cls);
            if (s > bestScore)
            {
                bestScore = s;
                best = cls;
            }
        }
        return bestScore > 0 ? best : 0;
    }
};

std::string Lower(std::string const& s)
{
    std::string o;
    o.reserve(s.size());
    for (unsigned char c : s)
        o.push_back(char(std::tolower(c)));
    return o;
}

bool Has(std::string const& hay, char const* needle)
{
    return hay.find(needle) != std::string::npos;
}

void ScoreName(std::string const& n, Score& sc)
{
    if (Has(n, "warlock") || Has(n, "necromancer") || Has(n, "necrolyte") || Has(n, "shadowmage"))
        sc.add(CLASS_WARLOCK, 10);
    if (Has(n, "shaman") || Has(n, "witch doctor") || Has(n, "geomancer") || Has(n, "earthcaller")
        || Has(n, "windtalker") || Has(n, "spiritchaser") || Has(n, "oracle") || Has(n, "seer")
        || Has(n, "tidecaller") || Has(n, "wave rider"))
        sc.add(CLASS_SHAMAN, 10);
    if (Has(n, "priest") || Has(n, "preserver") || Has(n, "cleric") || Has(n, "chaplain")
        || Has(n, "appraiser"))
        sc.add(CLASS_PRIEST, 10);
    if (Has(n, "mage") || Has(n, "sorcerer") || Has(n, "wizard") || Has(n, "arcanist"))
        sc.add(CLASS_MAGE, 10);
    if (Has(n, "hunter") || Has(n, "cannoneer") || Has(n, "archer") || Has(n, "marksman")
        || Has(n, "scout") || Has(n, "outrunner") || Has(n, "pathfinder"))
        sc.add(CLASS_HUNTER, 10);
    if (Has(n, "rogue") || Has(n, "assassin") || Has(n, "cutthroat") || Has(n, "bandit"))
        sc.add(CLASS_ROGUE, 10);
    if (Has(n, "paladin") || Has(n, "templar") || Has(n, "crusader") || Has(n, "knight of"))
        sc.add(CLASS_PALADIN, 10);
    if (Has(n, "warrior") || Has(n, "grunt") || Has(n, "gladiator") || Has(n, "champion")
        || Has(n, "defender") || Has(n, "guardsman") || Has(n, "footman") || Has(n, "executioner")
        || Has(n, "battleguard") || Has(n, "mauler") || Has(n, "enforcer"))
        sc.add(CLASS_WARRIOR, 10);
    if (Has(n, "druid") || Has(n, "keeper of the grove") || Has(n, "dryad") || Has(n, "cenarion"))
        sc.add(CLASS_DRUID, 10);
}

void ScoreSpellName(std::string const& n, Score& sc)
{
    if (Has(n, "shadow bolt") || Has(n, "corruption") || Has(n, "immolate") || Has(n, "curse of")
        || Has(n, "summon succubus") || Has(n, "summon voidwalker") || Has(n, "summon felhunter")
        || Has(n, "death & decay") || Has(n, "banish") || Has(n, "drain life") || Has(n, "bone armor")
        || Has(n, "shadow barrier") || Has(n, "shadow shock"))
        sc.add(CLASS_WARLOCK, 3);
    if (Has(n, "lightning bolt") || Has(n, "chain lightning") || Has(n, "healing wave")
        || Has(n, "lightning shield") || Has(n, "totem") || Has(n, "bloodlust") || Has(n, "frost shock")
        || Has(n, "earth shock") || Has(n, "flame shock") || Has(n, "searing totem")
        || Has(n, "healing ward") || Has(n, "gust of wind"))
        sc.add(CLASS_SHAMAN, 3);
    if (Has(n, "holy smite") || Has(n, "lesser heal") || Has(n, "heal") || Has(n, "renew")
        || Has(n, "power word") || Has(n, "mind blast") || Has(n, "shadow word") || Has(n, "cure disease")
        || Has(n, "flash heal") || Has(n, "holy fire"))
        sc.add(CLASS_PRIEST, 3);
    if (Has(n, "fireball") || Has(n, "frostbolt") || Has(n, "flamestrike") || Has(n, "blizzard")
        || Has(n, "arcane explosion") || Has(n, "fire blast") || Has(n, "cone of cold")
        || Has(n, "frost armor") || Has(n, "ice armor") || Has(n, "polymorph") || Has(n, "scorch"))
        sc.add(CLASS_MAGE, 3);
    if (Has(n, "shoot") || Has(n, "aimed shot") || Has(n, "multi-shot") || Has(n, "serpent sting")
        || Has(n, "arcane shot") || Has(n, "concussive shot") || Has(n, "auto shot"))
        sc.add(CLASS_HUNTER, 3);
    if (Has(n, "backstab") || Has(n, "sinister strike") || Has(n, "eviscerate") || Has(n, "garrote")
        || Has(n, "cheap shot") || Has(n, "kidney shot") || Has(n, "dual wield"))
        sc.add(CLASS_ROGUE, 3);
    if (Has(n, "holy light") || Has(n, "flash of light") || Has(n, "judgement") || Has(n, "seal of")
        || Has(n, "divine shield") || Has(n, "hammer of justice") || Has(n, "consecration"))
        sc.add(CLASS_PALADIN, 3);
    if (Has(n, "heroic strike") || Has(n, "rend") || Has(n, "thunder clap") || Has(n, "thunderclap")
        || Has(n, "battle shout") || Has(n, "demoralizing shout") || Has(n, "shield block")
        || Has(n, "shield slam") || Has(n, "revenge") || Has(n, "execute") || Has(n, "overpower")
        || Has(n, "battle stance") || Has(n, "defensive stance") || Has(n, "berserker stance")
        || Has(n, "cleave") || Has(n, "mortal strike") || Has(n, "bloodthirst") || Has(n, "whirlwind")
        || Has(n, "disarm") || Has(n, "hamstring") || Has(n, "charge") || Has(n, "improved blocking"))
        sc.add(CLASS_WARRIOR, 3);
    if (Has(n, "wrath") || Has(n, "moonfire") || Has(n, "rejuvenation") || Has(n, "regrowth")
        || Has(n, "starfire") || Has(n, "entangling roots") || Has(n, "bear form") || Has(n, "cat form")
        || Has(n, "healing touch") || Has(n, "mark of the wild"))
        sc.add(CLASS_DRUID, 3);
}

void CollectSpellNames(CreatureInfo const* cinfo, Score& sc)
{
    auto scoreId = [&](uint32 spellId)
    {
        if (!spellId)
            return;
        SpellEntry const* sp = sSpellMgr.GetSpellEntry(spellId);
        if (!sp)
            return;
        ScoreSpellName(Lower(sp->SpellName[0]), sc);
    };

    if (cinfo->spell_list_id)
    {
        if (CreatureSpellsList const* list = sObjectMgr.GetCreatureSpellsList(cinfo->spell_list_id))
        {
            for (auto const& e : *list)
                scoreId(e.spellId);
        }
    }

    auto const& aiMap = sEventAIMgr.GetCreatureEventAIMap();
    auto it = aiMap.find(cinfo->entry);
    if (it == aiMap.end())
        return;
    for (auto const& ev : it->second)
    {
        for (uint32 i = 0; i < MAX_ACTIONS; ++i)
        {
            ScriptMap* sm = ev.action[i];
            if (!sm)
                continue;
            for (auto const& pair : *sm)
            {
                ScriptInfo const& si = pair.second;
                if (si.command != SCRIPT_COMMAND_CAST_SPELL)
                    continue;
                scoreId(si.castSpell.spellId);
            }
        }
    }
}

struct EquipFlags
{
    bool ranged = false;
    bool dagger = false;
    bool dualDagger = false;
    bool shield = false;
    bool staff = false;
    bool twoHandMelee = false;
};

EquipFlags ReadEquip(CreatureInfo const* cinfo)
{
    EquipFlags f;
    if (!cinfo->equipment_id)
        return f;
    EquipmentTemplate const* eq = sObjectMgr.GetEquipmentTemplate(cinfo->equipment_id);
    if (!eq || eq->equipment.empty())
        return f;

    auto consider = [&](uint32 itemId)
    {
        if (!itemId)
            return;
        ItemPrototype const* proto = sObjectMgr.GetItemPrototype(itemId);
        if (!proto)
            return;
        if (proto->InventoryType == INVTYPE_SHIELD)
        {
            f.shield = true;
            return;
        }
        if (!proto->IsWeapon())
            return;
        if (proto->IsRangedWeapon())
            f.ranged = true;
        if (proto->SubClass == ITEM_SUBCLASS_WEAPON_DAGGER)
            f.dagger = true;
        if (proto->SubClass == ITEM_SUBCLASS_WEAPON_STAFF)
            f.staff = true;
        else if (proto->InventoryType == INVTYPE_2HWEAPON)
            f.twoHandMelee = true;
    };

    // Use first equip row as representative
    EquipmentEntry const& row = eq->equipment.front();
    consider(row.item[0]);
    consider(row.item[1]);
    consider(row.item[2]);
    if (row.item[0] && row.item[1])
    {
        ItemPrototype const* a = sObjectMgr.GetItemPrototype(row.item[0]);
        ItemPrototype const* b = sObjectMgr.GetItemPrototype(row.item[1]);
        if (a && b && a->SubClass == ITEM_SUBCLASS_WEAPON_DAGGER && b->SubClass == ITEM_SUBCLASS_WEAPON_DAGGER)
            f.dualDagger = true;
    }
    return f;
}

void ScoreEquip(EquipFlags const& f, Score& sc)
{
    if (f.ranged)
        sc.add(CLASS_HUNTER, 5);
    if (f.dualDagger)
        sc.add(CLASS_ROGUE, 5);
    else if (f.dagger && !f.staff)
        sc.add(CLASS_ROGUE, 2);
    if (f.shield)
        sc.add(CLASS_WARRIOR, 3);
    if (f.twoHandMelee)
        sc.add(CLASS_WARRIOR, 2);
    if (f.staff)
    {
        sc.add(CLASS_MAGE, 1);
        sc.add(CLASS_PRIEST, 1);
        sc.add(CLASS_SHAMAN, 1);
        sc.add(CLASS_WARLOCK, 1);
    }
}

bool HasManaPool(CreatureInfo const* cinfo)
{
    CreatureClassLevelStats const* cls = sObjectMgr.GetCreatureClassLevelStats(cinfo->unit_class, cinfo->level_min);
    return cls && cls->mana > 0;
}

PersonaSpec InferSpec(uint8 cls, CreatureInfo const* cinfo, EquipFlags const& eq, Score const& spellScore)
{
    if (cls == CLASS_SHAMAN && !HasManaPool(cinfo) && !eq.staff && !eq.ranged)
        return PERSONA_SPEC_SHAMAN_ENH;

    if (cls == CLASS_WARRIOR && eq.shield)
        return PERSONA_SPEC_WARRIOR_PROT;

    if (cls == CLASS_MAGE)
    {
        // name/spell fire vs frost dominance via simple recount not stored; leave none for random
        std::string n = Lower(cinfo->name);
        if (Has(n, "frost") || Has(n, "ice"))
            return PERSONA_SPEC_MAGE_FROST;
        if (Has(n, "fire") || Has(n, "flame"))
            return PERSONA_SPEC_MAGE_FIRE;
        (void)spellScore;
    }
    return PERSONA_SPEC_NONE;
}
} // namespace

namespace CreaturePersonaMapping
{
void LoadFromDB()
{
    s_mapRows.clear();
    std::unique_ptr<QueryResult> result(WorldDatabase.Query(
        "SELECT `entry`, `persona_class`, `persona_spec`, `override` FROM `creature_persona_map`"));
    if (!result)
    {
        sLog.Out(LOG_BASIC, LOG_LVL_MINIMAL, ">> Loaded 0 creature_persona_map rows (table empty or missing).");
        return;
    }

    uint32 count = 0;
    do
    {
        Field* f = result->Fetch();
        MapRow row;
        uint32 entry = f[0].GetUInt32();
        row.personaClass = f[1].GetUInt8();
        row.spec = PersonaSpec(f[2].GetUInt8());
        row.isOverride = f[3].GetBool();
        s_mapRows[entry] = row;
        ++count;
    } while (result->NextRow());

    sLog.Out(LOG_BASIC, LOG_LVL_MINIMAL, ">> Loaded %u creature_persona_map rows.", count);
}

PersonaMapping EvaluateRules(CreatureInfo const* cinfo)
{
    PersonaMapping out;
    if (!cinfo)
        return out;

    Score nameSc, spellSc, equipSc;
    ScoreName(Lower(cinfo->name), nameSc); // name is std::string
    CollectSpellNames(cinfo, spellSc);
    EquipFlags eq = ReadEquip(cinfo);
    ScoreEquip(eq, equipSc);

    uint8 cls = 0;
    if (!nameSc.empty())
        cls = nameSc.winner();
    else if (!spellSc.empty())
        cls = spellSc.winner();
    else if (!equipSc.empty())
        cls = equipSc.winner();
    else
    {
        switch (cinfo->unit_class)
        {
            case CLASS_WARRIOR: cls = CLASS_WARRIOR; break;
            case CLASS_MAGE: cls = CLASS_MAGE; break;
            case CLASS_PALADIN: cls = CLASS_SHAMAN; break; // mana bucket → shaman default
            case CLASS_ROGUE: cls = CLASS_ROGUE; break;
            default: cls = 0; break;
        }
    }

    if (!cls)
        return out;

    out.personaClass = cls;
    out.spec = InferSpec(cls, cinfo, eq, spellSc);
    out.source = PERSONA_MAP_RULES;
    return out;
}

PersonaMapping Resolve(CreatureInfo const* cinfo)
{
    PersonaMapping out;
    if (!cinfo)
        return out;

    auto itr = s_mapRows.find(cinfo->entry);
    if (itr != s_mapRows.end())
    {
        out.personaClass = itr->second.personaClass;
        out.spec = itr->second.spec;
        out.source = itr->second.isOverride ? PERSONA_MAP_OVERRIDE : PERSONA_MAP_TABLE;
        if (out.personaClass)
        {
            if (sWorld.getConfig(CONFIG_BOOL_CREATURE_PERSONA_MAPPING_DEBUG))
                sLog.Out(LOG_BASIC, LOG_LVL_MINIMAL, "CreaturePersona map entry %u -> class %u spec %u (%s)",
                    cinfo->entry, out.personaClass, uint32(out.spec),
                    out.source == PERSONA_MAP_OVERRIDE ? "override" : "table");
            return out;
        }
    }

    out = EvaluateRules(cinfo);
    if (out.personaClass && sWorld.getConfig(CONFIG_BOOL_CREATURE_PERSONA_MAPPING_DEBUG))
        sLog.Out(LOG_BASIC, LOG_LVL_MINIMAL, "CreaturePersona rules entry %u (%s) -> class %u spec %u",
            cinfo->entry, cinfo->name.c_str(), out.personaClass, uint32(out.spec));
    return out;
}

std::vector<PersonaSpec> SpecsFor(uint8 personaClass)
{
    switch (personaClass)
    {
        case CLASS_WARRIOR:
            return { PERSONA_SPEC_WARRIOR_ARMS, PERSONA_SPEC_WARRIOR_FURY, PERSONA_SPEC_WARRIOR_PROT };
        case CLASS_PALADIN:
            return { PERSONA_SPEC_PALADIN_HOLY, PERSONA_SPEC_PALADIN_PROT, PERSONA_SPEC_PALADIN_RET };
        case CLASS_HUNTER:
            return { PERSONA_SPEC_HUNTER_BEAST, PERSONA_SPEC_HUNTER_MARKS, PERSONA_SPEC_HUNTER_SURVIVAL };
        case CLASS_ROGUE:
            // P1: Combat only
            return { PERSONA_SPEC_ROGUE_COMBAT };
        case CLASS_PRIEST:
            return { PERSONA_SPEC_PRIEST_DISC, PERSONA_SPEC_PRIEST_HOLY, PERSONA_SPEC_PRIEST_SHADOW };
        case CLASS_SHAMAN:
            // P1: Enhancement only (Ele/Resto not implemented yet)
            return { PERSONA_SPEC_SHAMAN_ENH };
        case CLASS_MAGE:
            return { PERSONA_SPEC_MAGE_ARCANE, PERSONA_SPEC_MAGE_FIRE, PERSONA_SPEC_MAGE_FROST };
        case CLASS_WARLOCK:
            return { PERSONA_SPEC_WARLOCK_AFFLICTION, PERSONA_SPEC_WARLOCK_DEMONOLOGY, PERSONA_SPEC_WARLOCK_DESTRUCTION };
        case CLASS_DRUID:
            return { PERSONA_SPEC_DRUID_BALANCE, PERSONA_SPEC_DRUID_FERAL, PERSONA_SPEC_DRUID_RESTO };
        default:
            return {};
    }
}

PersonaSpec PickRandomSpec(uint8 personaClass)
{
    auto pool = SpecsFor(personaClass);
    if (pool.empty())
        return PERSONA_SPEC_NONE;
    return pool[urand(0, pool.size() - 1)];
}

bool IsImplemented(uint8 personaClass)
{
    return personaClass == CLASS_WARRIOR || personaClass == CLASS_SHAMAN || personaClass == CLASS_ROGUE;
}

char const* ClassName(uint8 personaClass)
{
    switch (personaClass)
    {
        case CLASS_WARRIOR: return "Warrior";
        case CLASS_PALADIN: return "Paladin";
        case CLASS_HUNTER: return "Hunter";
        case CLASS_ROGUE: return "Rogue";
        case CLASS_PRIEST: return "Priest";
        case CLASS_SHAMAN: return "Shaman";
        case CLASS_MAGE: return "Mage";
        case CLASS_WARLOCK: return "Warlock";
        case CLASS_DRUID: return "Druid";
        default: return "None";
    }
}

char const* SpecName(PersonaSpec spec)
{
    switch (spec)
    {
        case PERSONA_SPEC_NONE: return "none";
        case PERSONA_SPEC_WARRIOR_ARMS: return "Arms";
        case PERSONA_SPEC_WARRIOR_FURY: return "Fury";
        case PERSONA_SPEC_WARRIOR_PROT: return "Protection";
        case PERSONA_SPEC_PALADIN_HOLY: return "Holy";
        case PERSONA_SPEC_PALADIN_PROT: return "Protection";
        case PERSONA_SPEC_PALADIN_RET: return "Retribution";
        case PERSONA_SPEC_HUNTER_BEAST: return "Beast Mastery";
        case PERSONA_SPEC_HUNTER_MARKS: return "Marksmanship";
        case PERSONA_SPEC_HUNTER_SURVIVAL: return "Survival";
        case PERSONA_SPEC_ROGUE_ASSA: return "Assassination";
        case PERSONA_SPEC_ROGUE_COMBAT: return "Combat";
        case PERSONA_SPEC_ROGUE_SUBTLETY: return "Subtlety";
        case PERSONA_SPEC_PRIEST_DISC: return "Discipline";
        case PERSONA_SPEC_PRIEST_HOLY: return "Holy";
        case PERSONA_SPEC_PRIEST_SHADOW: return "Shadow";
        case PERSONA_SPEC_SHAMAN_ELE: return "Elemental";
        case PERSONA_SPEC_SHAMAN_ENH: return "Enhancement";
        case PERSONA_SPEC_SHAMAN_RESTO: return "Restoration";
        case PERSONA_SPEC_MAGE_ARCANE: return "Arcane";
        case PERSONA_SPEC_MAGE_FIRE: return "Fire";
        case PERSONA_SPEC_MAGE_FROST: return "Frost";
        case PERSONA_SPEC_WARLOCK_AFFLICTION: return "Affliction";
        case PERSONA_SPEC_WARLOCK_DEMONOLOGY: return "Demonology";
        case PERSONA_SPEC_WARLOCK_DESTRUCTION: return "Destruction";
        case PERSONA_SPEC_DRUID_BALANCE: return "Balance";
        case PERSONA_SPEC_DRUID_FERAL: return "Feral";
        case PERSONA_SPEC_DRUID_RESTO: return "Restoration";
        default: return "unknown";
    }
}

char const* SourceName(PersonaMappingSource src)
{
    switch (src)
    {
        case PERSONA_MAP_OVERRIDE: return "override";
        case PERSONA_MAP_TABLE: return "table";
        case PERSONA_MAP_RULES: return "rules";
        default: return "none";
    }
}
} // namespace CreaturePersonaMapping
