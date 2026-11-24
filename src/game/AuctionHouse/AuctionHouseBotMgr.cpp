#include "AuctionHouseBotMgr.h"
#include "AuctionHouseMgr.h"
#include "Chat.h"
#include "Config/Config.h"
#include "Database/DatabaseEnv.h"
#include "Item.h"
#include "Log.h"
#include "ObjectMgr.h"
#include "Policies/SingletonImp.h"
#include "Utilities/Random.h"
#include <algorithm>
#include <cmath>

INSTANTIATE_SINGLETON_1(AuctionHouseBotMgr);

namespace
{
bool ClassAllowed(uint32 itemClass)
{
    switch (itemClass)
    {
        case ITEM_CLASS_CONSUMABLE:
        case ITEM_CLASS_CONTAINER:
        case ITEM_CLASS_WEAPON:
        case ITEM_CLASS_ARMOR:
        case ITEM_CLASS_REAGENT:
        case ITEM_CLASS_PROJECTILE:
        case ITEM_CLASS_TRADE_GOODS:
        case ITEM_CLASS_RECIPE:
        case ITEM_CLASS_QUIVER:
            return true;
        default:
            return false;
    }
}
} // namespace

AuctionHouseBotMgr::~AuctionHouseBotMgr()
{
    m_config.reset();
}

bool AuctionHouseBotMgr::PassesFilters(ItemPrototype const* proto) const
{
    if (!proto)
        return false;
    if (proto->Quality == ITEM_QUALITY_POOR || proto->Quality >= ITEM_QUALITY_LEGENDARY)
        return false;
    if (!ClassAllowed(proto->Class))
        return false;
    if (proto->Bonding != NO_BIND && proto->Bonding != BIND_WHEN_EQUIPPED)
        return false;
    if (proto->Flags & ITEM_FLAG_CONJURED)
        return false;
    // worthless / unusable junk for AH
    if (!proto->BuyPrice && !proto->SellPrice && proto->Class != ITEM_CLASS_RECIPE)
        return false;
    if (proto->MaxCount == 1 && proto->Class == ITEM_CLASS_QUEST)
        return false;
    return true;
}

void AuctionHouseBotMgr::Load()
{
    for (auto& q : m_pool)
        for (auto& c : q)
            c.clear();
    for (auto& q : m_target)
        q.fill(0);
    m_loaded = false;
    m_config.reset();
    m_auctionHouseEntry = nullptr;

    m_config = std::make_unique<AuctionHouseBotConfig>();
    m_config->enable = sConfig.GetBoolDefault("AHBot.Enable", false);
    m_config->ahfid = sConfig.GetIntDefault("AHBot.ah.fid", 120);
    m_config->itemcount = sConfig.GetIntDefault("AHBot.itemcount", 10000);

    m_config->amountQuality[ITEM_QUALITY_NORMAL] = sConfig.GetIntDefault("AHBot.Amount.White", 2500);
    m_config->amountQuality[ITEM_QUALITY_UNCOMMON] = sConfig.GetIntDefault("AHBot.Amount.Green", 3500);
    m_config->amountQuality[ITEM_QUALITY_RARE] = sConfig.GetIntDefault("AHBot.Amount.Blue", 2500);
    m_config->amountQuality[ITEM_QUALITY_EPIC] = sConfig.GetIntDefault("AHBot.Amount.Purple", 1200);
    m_config->amountQuality[ITEM_QUALITY_LEGENDARY] = sConfig.GetIntDefault("AHBot.Amount.Orange", 300);
    m_config->amountQuality[ITEM_QUALITY_ARTIFACT] = sConfig.GetIntDefault("AHBot.Amount.Yellow", 0);
    m_config->amountQuality[ITEM_QUALITY_POOR] = 0;

    m_config->classPriority[ITEM_CLASS_TRADE_GOODS] = sConfig.GetIntDefault("AHBot.Priority.TradeGoods", 25);
    m_config->classPriority[ITEM_CLASS_ARMOR] = sConfig.GetIntDefault("AHBot.Priority.Armor", 20);
    m_config->classPriority[ITEM_CLASS_WEAPON] = sConfig.GetIntDefault("AHBot.Priority.Weapon", 15);
    m_config->classPriority[ITEM_CLASS_CONSUMABLE] = sConfig.GetIntDefault("AHBot.Priority.Consumable", 15);
    m_config->classPriority[ITEM_CLASS_RECIPE] = sConfig.GetIntDefault("AHBot.Priority.Recipe", 10);
    m_config->classPriority[ITEM_CLASS_REAGENT] = sConfig.GetIntDefault("AHBot.Priority.Reagent", 5);
    m_config->classPriority[ITEM_CLASS_PROJECTILE] = sConfig.GetIntDefault("AHBot.Priority.Projectile", 5);
    m_config->classPriority[ITEM_CLASS_CONTAINER] = sConfig.GetIntDefault("AHBot.Priority.Container", 3);
    m_config->classPriority[ITEM_CLASS_QUIVER] = sConfig.GetIntDefault("AHBot.Priority.Quiver", 2);

    m_config->priceRatio[ITEM_QUALITY_NORMAL] = sConfig.GetIntDefault("AHBot.PriceRatio.White", 100);
    m_config->priceRatio[ITEM_QUALITY_UNCOMMON] = sConfig.GetIntDefault("AHBot.PriceRatio.Green", 150);
    m_config->priceRatio[ITEM_QUALITY_RARE] = sConfig.GetIntDefault("AHBot.PriceRatio.Blue", 200);
    m_config->priceRatio[ITEM_QUALITY_EPIC] = sConfig.GetIntDefault("AHBot.PriceRatio.Purple", 350);
    m_config->priceRatio[ITEM_QUALITY_LEGENDARY] = sConfig.GetIntDefault("AHBot.PriceRatio.Orange", 500);
    m_config->priceRatio[ITEM_QUALITY_ARTIFACT] = sConfig.GetIntDefault("AHBot.PriceRatio.Yellow", 600);
    m_config->priceRatio[ITEM_QUALITY_POOR] = 50;

    uint32 added = 0;
    for (auto const& pair : sObjectMgr.GetItemPrototypeMap())
    {
        ItemPrototype const* proto = &pair.second;
        if (!PassesFilters(proto))
            continue;
        m_pool[proto->Quality][proto->Class].push_back(proto->ItemId);
        ++added;
    }

    RebuildTargets();

    m_auctionHouseEntry = sAuctionMgr.GetAuctionHouseEntry(m_config->ahfid);
    if (!m_auctionHouseEntry)
    {
        sLog.Out(LOG_BASIC, LOG_LVL_MINIMAL, "AHBot::Load() : No auction house for faction %u.", m_config->ahfid);
        return;
    }

    sLog.Out(LOG_BASIC, LOG_LVL_MINIMAL, "");
    sLog.Out(LOG_BASIC, LOG_LVL_MINIMAL, ">> AHBot scanned %u sellable items (cap %u)", added, m_config->itemcount);
    m_loaded = true;
}

void AuctionHouseBotMgr::RebuildTargets()
{
    for (auto& q : m_target)
        q.fill(0);

    if (!m_config || !m_config->itemcount)
        return;

    uint32 sumAmount = 0;
    for (uint32 q = ITEM_QUALITY_NORMAL; q < MAX_ITEM_QUALITY; ++q)
        sumAmount += m_config->amountQuality[q];
    if (!sumAmount)
        return;

    for (uint32 q = ITEM_QUALITY_NORMAL; q < MAX_ITEM_QUALITY; ++q)
    {
        uint32 qAmt = uint32(uint64(m_config->amountQuality[q]) * m_config->itemcount / sumAmount);
        uint32 sumPrio = 0;
        for (uint32 c = 0; c < MAX_ITEM_CLASS; ++c)
            if (m_config->classPriority[c] && !m_pool[q][c].empty())
                sumPrio += m_config->classPriority[c];
        if (!sumPrio || !qAmt)
            continue;

        uint32 assigned = 0;
        uint32 lastC = 0;
        for (uint32 c = 0; c < MAX_ITEM_CLASS; ++c)
        {
            if (!m_config->classPriority[c] || m_pool[q][c].empty())
                continue;
            uint32 n = uint32(uint64(qAmt) * m_config->classPriority[c] / sumPrio);
            m_target[q][c] = n;
            assigned += n;
            lastC = c;
        }
        if (assigned < qAmt)
            m_target[q][lastC] += (qAmt - assigned);
    }
}

void AuctionHouseBotMgr::Update(bool force /* = false */)
{
    if (!m_loaded || !m_config || !m_auctionHouseEntry)
        return;
    if (!(m_config->enable || force))
        return;

    AuctionHouseObject* auctionHouse = sAuctionMgr.GetAuctionsMap(m_auctionHouseEntry);
    if (!auctionHouse)
        return;

    std::array<std::array<uint32, MAX_ITEM_CLASS>, MAX_ITEM_QUALITY> current{};
    for (auto const& itr : *auctionHouse->GetAuctions())
    {
        AuctionEntry const* a = itr.second;
        if (!a || a->owner != 0)
            continue;
        ItemPrototype const* proto = sObjectMgr.GetItemPrototype(a->itemTemplate);
        if (!proto || proto->Quality >= MAX_ITEM_QUALITY || proto->Class >= MAX_ITEM_CLASS)
            continue;
        ++current[proto->Quality][proto->Class];
    }

    uint32 added = 0;
    for (uint32 q = ITEM_QUALITY_NORMAL; q < MAX_ITEM_QUALITY; ++q)
    {
        for (uint32 c = 0; c < MAX_ITEM_CLASS; ++c)
        {
            while (current[q][c] < m_target[q][c] && auctionHouse->GetCount() < m_config->itemcount)
            {
                if (m_pool[q][c].empty())
                    break;
                AddRandomFromPool(q, c, auctionHouse);
                ++current[q][c];
                ++added;
            }
        }
    }

    // rounding leftovers: fill any non-empty pool until cap
    while (auctionHouse->GetCount() < m_config->itemcount)
    {
        std::vector<std::pair<uint32, uint32>> buckets;
        for (uint32 q = ITEM_QUALITY_NORMAL; q < MAX_ITEM_QUALITY; ++q)
        {
            if (!m_config->amountQuality[q])
                continue;
            for (uint32 c = 0; c < MAX_ITEM_CLASS; ++c)
                if (!m_pool[q][c].empty() && m_config->classPriority[c])
                    buckets.emplace_back(q, c);
        }
        if (buckets.empty())
            break;
        auto const& b = buckets[urand(0, buckets.size() - 1)];
        AddRandomFromPool(b.first, b.second, auctionHouse);
        ++added;
        if (added > m_config->itemcount + 100) // safety
            break;
    }

    if (added)
        sLog.Out(LOG_BASIC, LOG_LVL_MINIMAL, "AHBot::Update() : added %u listings (AH now %u)", added, auctionHouse->GetCount());
}

void AuctionHouseBotMgr::AddRandomFromPool(uint32 quality, uint32 itemClass, AuctionHouseObject* auctionHouse)
{
    auto& pool = m_pool[quality][itemClass];
    if (pool.empty())
        return;
    AddItem(pool[urand(0, pool.size() - 1)], auctionHouse);
}

uint32 AuctionHouseBotMgr::PickStack(ItemPrototype const* proto) const
{
    uint32 maxStack = proto->GetMaxStackSize();
    if (maxStack <= 1)
        return 1;
    uint32 cap = std::min(maxStack, 20u);
    if (proto->Class == ITEM_CLASS_TRADE_GOODS || proto->Class == ITEM_CLASS_REAGENT ||
        proto->Class == ITEM_CLASS_PROJECTILE || proto->Class == ITEM_CLASS_CONSUMABLE)
        return urand(std::max(1u, cap / 4), cap);
    return urand(1, std::min(maxStack, 5u));
}

uint32 AuctionHouseBotMgr::CalcBuyout(ItemPrototype const* proto, uint32 stack) const
{
    uint32 ratio = m_config->priceRatio[proto->Quality];
    if (!ratio)
        ratio = 100;

    uint32 unit = proto->SellPrice ? proto->SellPrice : proto->BuyPrice;
    if (!unit)
    {
        uint32 lvl = proto->ItemLevel ? proto->ItemLevel : std::max(1u, proto->RequiredLevel);
        float q = proto->Quality ? float(proto->Quality) : 1.0f;
        unit = uint32(std::max(1.0f, lvl * q * lvl * 0.4f));
    }

    uint64 buy = uint64(unit) * stack * ratio / 100;
    if (buy < 1)
        buy = 1;
    if (buy > 0x7FFFFFFF)
        buy = 0x7FFFFFFF;
    return uint32(buy);
}

void AuctionHouseBotMgr::AddItem(uint32 itemId, AuctionHouseObject* auctionHouse)
{
    ItemPrototype const* prototype = sObjectMgr.GetItemPrototype(itemId);
    if (!prototype)
        return;

    uint32 stack = PickStack(prototype);
    Item* item = Item::CreateItem(itemId, stack);
    if (!item)
        return;

    // AH placeholders are ownerless; strip timed charges so nothing ticks them in-world.
    if (item->GetUInt32Value(ITEM_FIELD_DURATION))
        item->SetUInt32Value(ITEM_FIELD_DURATION, 0);

    if (uint32 randomPropertyId = Item::GenerateItemRandomPropertyId(itemId))
        item->SetItemRandomProperties(randomPropertyId);

    uint32 etime = 86400;
    switch (urand(1, 3))
    {
        case 1: etime = 43200; break;
        case 2: etime = 86400; break;
        default: etime = 172800; break;
    }

    uint32 buyout = CalcBuyout(prototype, stack);
    uint32 bid = std::max(1u, buyout * urand(60, 85) / 100);
    if (bid >= buyout)
        bid = std::max(1u, buyout - 1);

    uint32 dep = sAuctionMgr.GetAuctionDeposit(m_auctionHouseEntry, etime, item);

    AuctionEntry* auctionEntry = new AuctionEntry;
    auctionEntry->Id = sObjectMgr.GenerateAuctionID();
    auctionEntry->auctionHouseEntry = m_auctionHouseEntry;
    auctionEntry->itemGuidLow = item->GetGUIDLow();
    auctionEntry->itemTemplate = item->GetEntry();
    auctionEntry->owner = 0;
    auctionEntry->startbid = bid;
    auctionEntry->buyout = buyout;
    auctionEntry->bidder = 0;
    auctionEntry->bid = 0;
    auctionEntry->deposit = dep;
    auctionEntry->depositTime = time(nullptr);
    auctionEntry->expireTime = time_t(etime) + time(nullptr);

    item->SaveToDB();
    sAuctionMgr.AddAItem(item);
    auctionHouse->AddAuction(auctionEntry);
    auctionEntry->SaveToDB();
}

bool ChatHandler::HandleAHBotUpdateCommand(char* /*args*/)
{
    sAuctionHouseBotMgr.Update(true);
    SendSysMessage("[AHBot] Update finished.");
    return true;
}

bool ChatHandler::HandleAHBotReloadCommand(char* /*args*/)
{
    sAuctionHouseBotMgr.Load();
    SendSysMessage("[AHBot] Reload finished.");
    return true;
}
