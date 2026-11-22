#include "PartyBotHire.h"
#include "PartyBotAI.h"
#include "PlayerBotMgr.h"
#include "CombatBotBaseAI.h"
#include "Player.h"
#include "Creature.h"
#include "World.h"
#include "ObjectMgr.h"
#include "ObjectAccessor.h"
#include "GossipDef.h"
#include "ScriptedGossip.h"
#include "Database/DatabaseEnv.h"
#include "Chat.h"
#include "Policies/SingletonImp.h"
#include "Utilities/Random.h"
#include <algorithm>
#include <cstdio>

INSTANTIATE_SINGLETON_1(PartyBotHireMgr);

namespace
{
enum HireGossipAction : uint32
{
    HIRE_ACT_ROOT = 1,
    HIRE_ACT_ROLE_TANK = 10,
    HIRE_ACT_ROLE_HEAL = 11,
    HIRE_ACT_ROLE_DPS = 12,
    HIRE_ACT_BUY = 1000, // + role*100 + class
};

char const* ClassName(uint8 cls)
{
    switch (cls)
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
        default: return "Unknown";
    }
}

CombatBotRoles RoleForDpsClass(uint8 cls)
{
    return CombatBotBaseAI::IsMeleeDamageClass(cls) ? ROLE_MELEE_DPS : ROLE_RANGE_DPS;
}
}

bool PartyBotHireMgr::IsEnabled() const
{
    return sWorld.getConfig(CONFIG_BOOL_PARTY_BOT_HIRE_ENABLE);
}

uint32 PartyBotHireMgr::GetCostCopper() const
{
    return sWorld.getConfig(CONFIG_UINT32_PARTY_BOT_HIRE_COST_COPPER);
}

uint32 PartyBotHireMgr::GetDurationSeconds() const
{
    return sWorld.getConfig(CONFIG_UINT32_PARTY_BOT_HIRE_DURATION_SECONDS);
}

void PartyBotHireMgr::Load()
{
    m_byOwner.clear();
    m_botToContract.clear();

    std::unique_ptr<QueryResult> result(CharacterDatabase.Query(
        "SELECT `id`,`owner_guid`,`role`,`class`,`race`,`expire_time`,`status`,`bot_guid` FROM `character_partybot_hire` WHERE `status`=0"));
    if (!result)
        return;

    do
    {
        Field* f = result->Fetch();
        PartyBotHireContract c;
        c.id = f[0].GetUInt32();
        c.ownerGuid = f[1].GetUInt32();
        c.role = CombatBotRoles(f[2].GetUInt8());
        c.cls = f[3].GetUInt8();
        c.race = f[4].GetUInt8();
        c.expireTime = time_t(f[5].GetUInt32());
        c.status = f[6].GetUInt8();
        c.botGuid = 0;
        m_byOwner[c.ownerGuid].push_back(c);
    }
    while (result->NextRow());

    CharacterDatabase.PExecute("UPDATE `character_partybot_hire` SET `bot_guid`=0 WHERE `status`=0");
}

void PartyBotHireMgr::InsertContract(PartyBotHireContract& c)
{
    CharacterDatabase.PExecute(
        "INSERT INTO `character_partybot_hire` (`owner_guid`,`role`,`class`,`race`,`expire_time`,`status`,`bot_guid`) "
        "VALUES (%u,%u,%u,%u,%u,%u,%u)",
        c.ownerGuid, uint32(c.role), uint32(c.cls), uint32(c.race),
        uint32(c.expireTime), uint32(c.status), c.botGuid);

    if (std::unique_ptr<QueryResult> r{ CharacterDatabase.Query("SELECT LAST_INSERT_ID()") })
        c.id = r->Fetch()[0].GetUInt32();
}

void PartyBotHireMgr::SaveContract(PartyBotHireContract const& c)
{
    CharacterDatabase.PExecute(
        "UPDATE `character_partybot_hire` SET `status`=%u,`bot_guid`=%u,`expire_time`=%u WHERE `id`=%u",
        uint32(c.status), c.botGuid, uint32(c.expireTime), c.id);
}

uint32 PartyBotHireMgr::CountActiveFor(uint32 ownerGuid) const
{
    auto it = m_byOwner.find(ownerGuid);
    if (it == m_byOwner.end())
        return 0;
    uint32 n = 0;
    time_t const now = time(nullptr);
    for (auto const& c : it->second)
        if (c.status == PARTYBOT_HIRE_ACTIVE && c.expireTime > now)
            ++n;
    return n;
}

PartyBotHireContract* PartyBotHireMgr::FindByBotGuid(uint32 botGuid)
{
    auto it = m_botToContract.find(botGuid);
    if (it == m_botToContract.end())
        return nullptr;
    uint32 const id = it->second;
    for (auto& kv : m_byOwner)
        for (auto& c : kv.second)
            if (c.id == id)
                return &c;
    return nullptr;
}

PartyBotHireContract const* PartyBotHireMgr::FindByBotGuid(uint32 botGuid) const
{
    return const_cast<PartyBotHireMgr*>(this)->FindByBotGuid(botGuid);
}

void PartyBotHireMgr::VoidContract(PartyBotHireContract& c)
{
    if (c.status == PARTYBOT_HIRE_VOIDED)
        return;
    if (c.botGuid)
        m_botToContract.erase(c.botGuid);
    c.status = PARTYBOT_HIRE_VOIDED;
    c.botGuid = 0;
    SaveContract(c);
}

void PartyBotHireMgr::ExpireIfNeeded(PartyBotHireContract& c, time_t now)
{
    if (c.status != PARTYBOT_HIRE_ACTIVE)
        return;
    if (c.expireTime > now)
        return;
    if (c.botGuid)
    {
        if (Player* bot = sObjectAccessor.FindPlayer(ObjectGuid(HIGHGUID_PLAYER, c.botGuid)))
            if (bot->IsBot())
                sPlayerBotMgr.DeleteBot(c.botGuid);
        m_botToContract.erase(c.botGuid);
        c.botGuid = 0;
    }
    c.status = PARTYBOT_HIRE_VOIDED;
    SaveContract(c);
}

bool PartyBotHireMgr::CanHire(Player* player, std::string& error) const
{
    if (!IsEnabled())
    {
        error = "Mercenary hire is disabled.";
        return false;
    }
    if (!player || player->IsBot())
    {
        error = "Cannot hire.";
        return false;
    }
    if (player->IsTaxiFlying())
    {
        error = "Cannot hire while flying.";
        return false;
    }
    if (player->InBattleGround())
    {
        error = "Cannot hire in battlegrounds.";
        return false;
    }
    if (player->GetMoney() < GetCostCopper())
    {
        error = "Not enough money.";
        return false;
    }

    if (player->GetGroup() && (player->GetGroup()->IsFull() ||
        (sWorld.getConfig(CONFIG_UINT32_PARTY_BOT_MAX_BOTS) &&
         player->GetGroup()->GetMembersCount() - 1 >= sWorld.getConfig(CONFIG_UINT32_PARTY_BOT_MAX_BOTS))))
    {
        error = "Cannot hire more bots. Group is full.";
        return false;
    }

    if (!player->GetGroup() && sWorld.getConfig(CONFIG_UINT32_PARTY_BOT_MAX_BOTS) &&
        CountActiveFor(player->GetGUIDLow()) >= sWorld.getConfig(CONFIG_UINT32_PARTY_BOT_MAX_BOTS))
    {
        error = "Hire limit reached.";
        return false;
    }

    if (Map const* map = player->GetMap())
    {
        if (map->IsDungeon() && map->GetPlayers().getSize() >= map->GetMapEntry()->maxPlayers)
        {
            error = "Instance is full.";
            return false;
        }
    }

    if (player->GetSession()->GetSecurity() <= SEC_PLAYER && !sWorld.getConfig(CONFIG_BOOL_PARTY_BOT_SKIP_CHECKS))
    {
        if (player->IsDead())
        {
            error = "Cannot hire while dead.";
            return false;
        }
        if (player->IsInCombat())
        {
            error = "Cannot hire while in combat.";
            return false;
        }
        if (player->GetMap()->IsDungeon())
        {
            error = "Cannot hire inside instances.";
            return false;
        }
    }

    return true;
}

bool PartyBotHireMgr::SpawnFromContract(Player* owner, PartyBotHireContract& c)
{
    if (!owner || c.status != PARTYBOT_HIRE_ACTIVE)
        return false;
    if (c.botGuid)
        if (sObjectAccessor.FindPlayer(ObjectGuid(HIGHGUID_PLAYER, c.botGuid)))
            return true;

    if (owner->IsTaxiFlying() || owner->InBattleGround())
        return false;
    if (owner->GetGroup() && owner->GetGroup()->IsFull())
        return false;
    if (sWorld.getConfig(CONFIG_UINT32_PARTY_BOT_MAX_BOTS) && owner->GetGroup() &&
        owner->GetGroup()->GetMembersCount() - 1 >= sWorld.getConfig(CONFIG_UINT32_PARTY_BOT_MAX_BOTS))
        return false;
    if (Map const* map = owner->GetMap())
        if (map->IsDungeon() && map->GetPlayers().getSize() >= map->GetMapEntry()->maxPlayers)
            return false;

    float x, y, z;
    owner->GetNearPoint(owner, x, y, z, 0, 5.0f, frand(0.0f, 6.0f));

    auto* ai = new PartyBotAI(owner, nullptr, c.role, c.race, c.cls, owner->GetLevel(),
        owner->GetMapId(), owner->GetMap()->GetInstanceId(), x, y, z, owner->GetOrientation());
    ai->m_hireContractId = c.id;

    if (!sPlayerBotMgr.AddBot(ai))
    {
        delete ai;
        return false;
    }

    c.botGuid = uint32(ai->botEntry->playerGUID);
    m_botToContract[c.botGuid] = c.id;
    SaveContract(c);
    return true;
}

bool PartyBotHireMgr::Purchase(Player* player, CombatBotRoles role, uint8 botClass)
{
    std::string err;
    if (!CanHire(player, err))
    {
        ChatHandler(player).SendSysMessage(err.c_str());
        return false;
    }

    if (role == ROLE_INVALID || !botClass)
        return false;

    if (botClass == CLASS_PALADIN && player->GetTeam() != ALLIANCE)
        return false;
    if (botClass == CLASS_SHAMAN && player->GetTeam() != HORDE)
        return false;

    uint8 race = SelectRandomRaceForClass(botClass, player->GetTeam());
    if (!race)
    {
        ChatHandler(player).SendSysMessage("Unable to select race for bot.");
        return false;
    }

    CombatBotRoles finalRole = role;
    if (role == ROLE_MELEE_DPS || role == ROLE_RANGE_DPS)
        finalRole = RoleForDpsClass(botClass);
    else if (role == ROLE_TANK)
        finalRole = ROLE_TANK;
    else if (role == ROLE_HEALER)
        finalRole = ROLE_HEALER;

    player->ModifyMoney(-int32(GetCostCopper()));

    PartyBotHireContract c;
    c.ownerGuid = player->GetGUIDLow();
    c.role = finalRole;
    c.cls = botClass;
    c.race = race;
    c.expireTime = time(nullptr) + time_t(GetDurationSeconds());
    c.status = PARTYBOT_HIRE_ACTIVE;
    c.botGuid = 0;
    InsertContract(c);
    m_byOwner[c.ownerGuid].push_back(c);
    PartyBotHireContract& stored = m_byOwner[c.ownerGuid].back();

    if (!SpawnFromContract(player, stored))
    {
        ChatHandler(player).SendSysMessage("Failed to spawn mercenary. Contract kept; try again later.");
        return false;
    }

    ChatHandler(player).PSendSysMessage("Hired %s for %u hours.", ClassName(botClass), GetDurationSeconds() / 3600);
    return true;
}

void PartyBotHireMgr::OnOwnerLogin(Player* player)
{
    if (!player || !IsEnabled())
        return;

    auto it = m_byOwner.find(player->GetGUIDLow());
    if (it == m_byOwner.end())
        return;

    time_t const now = time(nullptr);
    uint32 recalled = 0;
    for (auto& c : it->second)
    {
        ExpireIfNeeded(c, now);
        if (c.status != PARTYBOT_HIRE_ACTIVE)
            continue;
        if (SpawnFromContract(player, c))
            ++recalled;
    }
    if (recalled)
        ChatHandler(player).PSendSysMessage("Recalled %u mercenary(ies).", recalled);
}

void PartyBotHireMgr::OnHireBotKicked(Player* bot)
{
    if (!bot || !bot->IsBot())
        return;
    PartyBotHireContract* c = FindByBotGuid(bot->GetGUIDLow());
    if (!c)
        return;
    VoidContract(*c);
    sPlayerBotMgr.DeleteBot(bot->GetGUIDLow());
}

void PartyBotHireMgr::OnHireBotLogout(uint32 botGuid)
{
    PartyBotHireContract* c = FindByBotGuid(botGuid);
    if (!c)
        return;
    m_botToContract.erase(botGuid);
    c->botGuid = 0;
    SaveContract(*c);
}

void PartyBotHireMgr::Update(uint32 diff)
{
    m_expireCheckTimer += diff;
    if (m_expireCheckTimer < 30000)
        return;
    m_expireCheckTimer = 0;

    time_t const now = time(nullptr);
    for (auto& kv : m_byOwner)
        for (auto& c : kv.second)
            ExpireIfNeeded(c, now);
}

void PartyBotHireMgr::SendHireGossip(Player* player, Creature* source)
{
    player->PlayerTalkClass->SendGossipMenu(DEFAULT_GOSSIP_MESSAGE, source->GetObjectGuid());
}

void PartyBotHireMgr::ShowRoleMenu(Player* player, Creature* source)
{
    player->PlayerTalkClass->ClearMenus();
    auto& menu = player->PlayerTalkClass->GetGossipMenu();
    char buf[128];
    snprintf(buf, sizeof(buf), "Hire mercenary (%u copper, %u hours)", GetCostCopper(), GetDurationSeconds() / 3600);
    menu.AddMenuItem(GOSSIP_ICON_CHAT, buf, GOSSIP_SENDER_PARTYBOT_HIRE, HIRE_ACT_ROOT, "", false);
    menu.AddGossipMenuItemData(0, 0, 0);
    menu.AddMenuItem(GOSSIP_ICON_BATTLE, "Hire Tank", GOSSIP_SENDER_PARTYBOT_HIRE, HIRE_ACT_ROLE_TANK, "", false);
    menu.AddGossipMenuItemData(0, 0, 0);
    menu.AddMenuItem(GOSSIP_ICON_CHAT, "Hire Healer", GOSSIP_SENDER_PARTYBOT_HIRE, HIRE_ACT_ROLE_HEAL, "", false);
    menu.AddGossipMenuItemData(0, 0, 0);
    menu.AddMenuItem(GOSSIP_ICON_BATTLE, "Hire DPS", GOSSIP_SENDER_PARTYBOT_HIRE, HIRE_ACT_ROLE_DPS, "", false);
    menu.AddGossipMenuItemData(0, 0, 0);
    SendHireGossip(player, source);
}

void PartyBotHireMgr::ShowClassMenu(Player* player, Creature* source, CombatBotRoles role)
{
    player->PlayerTalkClass->ClearMenus();
    auto& menu = player->PlayerTalkClass->GetGossipMenu();

    std::vector<uint8> classes;
    switch (role)
    {
        case ROLE_TANK:
            classes = { CLASS_WARRIOR };
            break;
        case ROLE_HEALER:
            classes = { CLASS_PRIEST, CLASS_DRUID };
            if (player->GetTeam() == ALLIANCE)
                classes.push_back(CLASS_PALADIN);
            else
                classes.push_back(CLASS_SHAMAN);
            break;
        default:
            classes = { CLASS_WARRIOR, CLASS_HUNTER, CLASS_ROGUE, CLASS_MAGE, CLASS_WARLOCK, CLASS_DRUID, CLASS_PRIEST };
            if (player->GetTeam() == ALLIANCE)
                classes.push_back(CLASS_PALADIN);
            else
                classes.push_back(CLASS_SHAMAN);
            break;
    }

    for (uint8 cls : classes)
    {
        uint32 const act = HIRE_ACT_BUY + uint32(role) * 100 + cls;
        menu.AddMenuItem(GOSSIP_ICON_CHAT, ClassName(cls), GOSSIP_SENDER_PARTYBOT_HIRE, act, "", false);
        menu.AddGossipMenuItemData(0, 0, 0);
    }
    menu.AddMenuItem(GOSSIP_ICON_CHAT, "Back", GOSSIP_SENDER_PARTYBOT_HIRE, HIRE_ACT_ROOT, "", false);
    menu.AddGossipMenuItemData(0, 0, 0);
    SendHireGossip(player, source);
}

void PartyBotHireMgr::AppendInnkeeperGossip(Player* player, Creature* /*innkeeper*/)
{
    if (!IsEnabled() || !player)
        return;
    auto& menu = player->PlayerTalkClass->GetGossipMenu();
    menu.AddMenuItem(GOSSIP_ICON_TALK, "Hire Mercenary", GOSSIP_SENDER_PARTYBOT_HIRE, HIRE_ACT_ROOT, "", false);
    menu.AddGossipMenuItemData(0, 0, 0);
}

bool PartyBotHireMgr::HandleGossipSelect(Player* player, Creature* source, uint32 action)
{
    if (!player || !source || !IsEnabled())
        return false;

    if (action == HIRE_ACT_ROOT)
    {
        ShowRoleMenu(player, source);
        return true;
    }
    if (action == HIRE_ACT_ROLE_TANK)
    {
        ShowClassMenu(player, source, ROLE_TANK);
        return true;
    }
    if (action == HIRE_ACT_ROLE_HEAL)
    {
        ShowClassMenu(player, source, ROLE_HEALER);
        return true;
    }
    if (action == HIRE_ACT_ROLE_DPS)
    {
        ShowClassMenu(player, source, ROLE_MELEE_DPS);
        return true;
    }
    if (action >= HIRE_ACT_BUY)
    {
        uint32 packed = action - HIRE_ACT_BUY;
        CombatBotRoles role = CombatBotRoles(packed / 100);
        uint8 cls = uint8(packed % 100);
        player->PlayerTalkClass->CloseGossip();
        Purchase(player, role, cls);
        return true;
    }
    return false;
}
