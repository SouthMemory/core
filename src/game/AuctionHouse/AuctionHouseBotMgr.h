#ifndef _AUCTION_HOUSE_BOT_MGR_H
#define _AUCTION_HOUSE_BOT_MGR_H

#include "Policies/Singleton.h"
#include "SharedDefines.h"
#include "ItemPrototype.h"

#include <array>
#include <memory>
#include <vector>

class AuctionHouseObject;
struct AuctionHouseEntry;

struct AuctionHouseBotConfig
{
    bool enable = false;
    uint32 ahfid = 120;
    uint32 itemcount = 10000;
    std::array<uint32, MAX_ITEM_QUALITY> amountQuality{};
    std::array<uint32, MAX_ITEM_CLASS> classPriority{};
    std::array<uint32, MAX_ITEM_QUALITY> priceRatio{};
};

class AuctionHouseBotMgr
{
public:
    AuctionHouseBotMgr() = default;
    ~AuctionHouseBotMgr();

    void Load();
    void Update(bool force = false);

protected:
    bool PassesFilters(ItemPrototype const* proto) const;
    void RebuildTargets();
    void AddRandomFromPool(uint32 quality, uint32 itemClass, AuctionHouseObject* auctionHouse);
    void AddItem(uint32 itemId, AuctionHouseObject* auctionHouse);
    uint32 CalcBuyout(ItemPrototype const* proto, uint32 stack) const;
    uint32 PickStack(ItemPrototype const* proto) const;

    std::array<std::array<std::vector<uint32>, MAX_ITEM_CLASS>, MAX_ITEM_QUALITY> m_pool{};
    std::array<std::array<uint32, MAX_ITEM_CLASS>, MAX_ITEM_QUALITY> m_target{};
    std::unique_ptr<AuctionHouseBotConfig> m_config;
    AuctionHouseEntry const* m_auctionHouseEntry = nullptr;
    bool m_loaded = false;
};

#define sAuctionHouseBotMgr MaNGOS::Singleton<AuctionHouseBotMgr>::Instance()
#endif
