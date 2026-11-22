#ifndef MANGOS_PARTYBOT_HIRE_H
#define MANGOS_PARTYBOT_HIRE_H

#include "Common.h"
#include "Policies/Singleton.h"
#include "SharedDefines.h"
#include "ObjectGuid.h"
#include <unordered_map>
#include <vector>

class Player;
class Creature;

enum PartyBotHireStatus : uint8
{
    PARTYBOT_HIRE_ACTIVE = 0,
    PARTYBOT_HIRE_VOIDED = 1,
};

struct PartyBotHireContract
{
    uint32 id = 0;
    uint32 ownerGuid = 0;
    CombatBotRoles role = ROLE_INVALID;
    uint8 cls = 0;
    uint8 race = 0;
    time_t expireTime = 0;
    uint8 status = PARTYBOT_HIRE_ACTIVE;
    uint32 botGuid = 0;
};

// Gossip sender for innkeeper hire menus (avoid script collisions)
#define GOSSIP_SENDER_PARTYBOT_HIRE 50

class PartyBotHireMgr
{
public:
    void Load();
    void Update(uint32 diff);

    bool IsEnabled() const;
    uint32 GetCostCopper() const;
    uint32 GetDurationSeconds() const;

    bool CanHire(Player* player, std::string& error) const;
    bool Purchase(Player* player, CombatBotRoles role, uint8 botClass);
    void OnOwnerLogin(Player* player);
    void OnHireBotKicked(Player* bot);
    void OnHireBotLogout(uint32 botGuid); // clear bot_guid, do not void
    void AppendInnkeeperGossip(Player* player, Creature* innkeeper);
    bool HandleGossipSelect(Player* player, Creature* source, uint32 action);

    PartyBotHireContract* FindByBotGuid(uint32 botGuid);
    PartyBotHireContract const* FindByBotGuid(uint32 botGuid) const;

private:
    void VoidContract(PartyBotHireContract& c);
    void ExpireIfNeeded(PartyBotHireContract& c, time_t now);
    bool SpawnFromContract(Player* owner, PartyBotHireContract& c);
    uint32 CountActiveFor(uint32 ownerGuid) const;
    void SaveContract(PartyBotHireContract const& c);
    void InsertContract(PartyBotHireContract& c);
    void ShowRoleMenu(Player* player, Creature* source);
    void ShowClassMenu(Player* player, Creature* source, CombatBotRoles role);
    void SendHireGossip(Player* player, Creature* source);

    std::unordered_map<uint32 /*owner*/, std::vector<PartyBotHireContract>> m_byOwner;
    std::unordered_map<uint32 /*botGuid*/, uint32 /*contractId*/> m_botToContract;
    uint32 m_expireCheckTimer = 0;
};

#define sPartyBotHire MaNGOS::Singleton<PartyBotHireMgr>::Instance()

#endif
