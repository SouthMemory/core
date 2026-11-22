#include "CreaturePersonaWarrior.h"
#include "Creature.h"
#include "CreatureEventAI.h"
#include "CreatureEventAIMgr.h"
#include "ObjectMgr.h"
#include "SpellMgr.h"
#include "ScriptMgr.h"
#include "SharedDefines.h"
#include "SpellAuraDefines.h"

namespace
{
uint32 const CONTROL_MECHANIC_MASK =
    (1 << (MECHANIC_CHARM - 1)) | (1 << (MECHANIC_DISORIENTED - 1)) | (1 << (MECHANIC_FEAR - 1)) |
    (1 << (MECHANIC_STUN - 1)) | (1 << (MECHANIC_SLEEP - 1)) | (1 << (MECHANIC_ROOT - 1)) |
    (1 << (MECHANIC_SILENCE - 1)) | (1 << (MECHANIC_DISARM - 1)) | (1 << (MECHANIC_KNOCKOUT - 1)) |
    (1 << (MECHANIC_FREEZE - 1)) | (1 << (MECHANIC_BANISH - 1)) | (1 << (MECHANIC_POLYMORPH - 1));

SpellEntry const* PickRank(uint32 const* ranks, uint32 level)
{
    SpellEntry const* best = nullptr;
    for (uint32 i = 0; ranks[i]; ++i)
    {
        SpellEntry const* sp = sSpellMgr.GetSpellEntry(ranks[i]);
        if (!sp)
            continue;
        if (sp->spellLevel <= level)
            best = sp;
    }
    return best;
}

bool IsControlSpell(SpellEntry const* sp)
{
    return sp && (sp->GetAllSpellMechanicMask() & CONTROL_MECHANIC_MASK) != 0;
}

void CollectNativeMechanics(Creature const* c, uint32& mechanicMask)
{
    if (uint32 listId = c->GetCreatureInfo()->spell_list_id)
    {
        if (CreatureSpellsList const* list = sObjectMgr.GetCreatureSpellsList(listId))
        {
            for (auto const& e : *list)
            {
                if (SpellEntry const* sp = sSpellMgr.GetSpellEntry(e.spellId))
                    mechanicMask |= sp->GetAllSpellMechanicMask() & CONTROL_MECHANIC_MASK;
            }
        }
    }

    auto const& aiMap = sEventAIMgr.GetCreatureEventAIMap();
    auto it = aiMap.find(c->GetEntry());
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
                if (SpellEntry const* sp = sSpellMgr.GetSpellEntry(si.castSpell.spellId))
                    mechanicMask |= sp->GetAllSpellMechanicMask() & CONTROL_MECHANIC_MASK;
            }
        }
    }
}

SpellEntry const* FilterSpell(SpellEntry const* sp, uint32 nativeMask, bool stripAllControl)
{
    if (!sp)
        return nullptr;
    if (stripAllControl && IsControlSpell(sp))
        return nullptr;
    if (!stripAllControl && (sp->GetAllSpellMechanicMask() & nativeMask))
        return nullptr;
    return sp;
}
} // namespace

CreaturePersonaWarriorSpells BuildWarriorSpellbook(Creature const* c)
{
    uint32 const level = c->GetLevel();
    uint32 nativeMask = 0;
    bool const stripControl = !c->GetScriptName().empty() || c->GetScriptId() != 0;
    if (!stripControl)
        CollectNativeMechanics(c, nativeMask);

    auto pick = [&](uint32 const* ranks) {
        return FilterSpell(PickRank(ranks, level), nativeMask, stripControl);
    };

    static uint32 const BattleStance[] = { 2457, 0 };
    static uint32 const DefensiveStance[] = { 71, 0 };
    static uint32 const BerserkerStance[] = { 2458, 0 };
    static uint32 const Charge[] = { 100, 6178, 11578, 0 };
    static uint32 const Intercept[] = { 20252, 20616, 20617, 0 };
    static uint32 const Overpower[] = { 7384, 7887, 11584, 11585, 0 };
    static uint32 const HeroicStrike[] = { 78, 284, 285, 1608, 11564, 11565, 11566, 11567, 25286, 0 };
    static uint32 const Cleave[] = { 845, 7369, 11608, 11609, 20569, 0 };
    static uint32 const Execute[] = { 5308, 20658, 20660, 20661, 20662, 0 };
    static uint32 const MortalStrike[] = { 12294, 21551, 21552, 21553, 0 };
    static uint32 const Bloodthirst[] = { 23881, 23892, 23893, 23894, 0 };
    static uint32 const Bloodrage[] = { 2687, 0 };
    static uint32 const BerserkerRage[] = { 18499, 0 };
    static uint32 const Recklessness[] = { 1719, 0 };
    static uint32 const Retaliation[] = { 20230, 0 };
    static uint32 const DeathWish[] = { 12328, 0 };
    static uint32 const IntimidatingShout[] = { 5246, 0 };
    static uint32 const Pummel[] = { 6552, 6554, 0 };
    static uint32 const Rend[] = { 772, 6546, 6547, 6548, 11572, 11573, 11574, 0 };
    static uint32 const Disarm[] = { 676, 0 };
    static uint32 const Whirlwind[] = { 1680, 0 };
    static uint32 const BattleShout[] = { 6673, 5242, 6192, 11549, 11550, 11551, 25289, 0 };
    static uint32 const DemoShout[] = { 1160, 6190, 11554, 11555, 11556, 0 };
    static uint32 const Hamstring[] = { 1715, 7372, 7373, 0 };
    static uint32 const ThunderClap[] = { 6343, 8198, 8204, 8205, 11580, 11581, 0 };
    static uint32 const SweepingStrikes[] = { 12292, 0 };
    static uint32 const MockingBlow[] = { 694, 7400, 7402, 20559, 20560, 0 };
    static uint32 const ConcussionBlow[] = { 12809, 0 };

    CreaturePersonaWarriorSpells s;
    s.battleStance = PickRank(BattleStance, level);
    s.defensiveStance = PickRank(DefensiveStance, level);
    s.berserkerStance = PickRank(BerserkerStance, level);
    s.charge = pick(Charge);
    s.intercept = pick(Intercept);
    s.overpower = pick(Overpower);
    s.heroicStrike = pick(HeroicStrike);
    s.cleave = pick(Cleave);
    s.execute = pick(Execute);
    s.mortalStrike = pick(MortalStrike);
    s.bloodthirst = pick(Bloodthirst);
    s.bloodrage = PickRank(Bloodrage, level);
    s.berserkerRage = pick(BerserkerRage);
    s.recklessness = pick(Recklessness);
    s.retaliation = pick(Retaliation);
    s.deathWish = pick(DeathWish);
    s.intimidatingShout = pick(IntimidatingShout);
    s.pummel = pick(Pummel);
    s.rend = pick(Rend);
    s.disarm = pick(Disarm);
    s.whirlwind = pick(Whirlwind);
    s.battleShout = pick(BattleShout);
    s.demoShout = pick(DemoShout);
    s.hamstring = pick(Hamstring);
    s.thunderClap = pick(ThunderClap);
    s.sweepingStrikes = pick(SweepingStrikes);
    s.mockingBlow = pick(MockingBlow);
    s.concussionBlow = pick(ConcussionBlow);
    return s;
}

namespace
{
uint32 const STANCE_LOCK_MS = 8000;
}

CreaturePersonaWarrior::CreaturePersonaWarrior(Creature* owner, CreaturePersonaWarriorSpells const& spells)
    : CreaturePersona(owner), m_spells(spells)
{
    EnsureRagePool();
}

SpellEntry const* CreaturePersonaWarrior::StanceSpell(ShapeshiftForm form) const
{
    switch (form)
    {
        case FORM_BATTLESTANCE: return m_spells.battleStance;
        case FORM_DEFENSIVESTANCE: return m_spells.defensiveStance;
        case FORM_BERSERKERSTANCE: return m_spells.berserkerStance;
        default: return nullptr;
    }
}

bool CreaturePersonaWarrior::SwitchToStance(ShapeshiftForm form, bool urgent)
{
    if (m_owner->GetShapeshiftForm() == form)
        return false;
    if (!urgent && m_stanceLockMs > 0)
        return false;
    SpellEntry const* st = StanceSpell(form);
    if (!st)
        return false;
    if (!Cast(m_owner, st))
        return false;
    m_stanceLockMs = STANCE_LOCK_MS;
    return true;
}

bool CreaturePersonaWarrior::Cast(Unit* target, SpellEntry const* spell)
{
    return TryCast(target, spell);
}

void CreaturePersonaWarrior::OnEnterCombat()
{
    CreaturePersona::OnEnterCombat();
    m_stanceLockMs = 0;
    if (m_owner->GetShapeshiftForm() == FORM_NONE && m_spells.battleStance)
        TryCast(m_owner, m_spells.battleStance);
}

ShapeshiftForm CreaturePersonaWarrior::ChooseStance(Unit* victim) const
{
    float const hp = m_owner->GetHealthPercent();
    ShapeshiftForm const form = m_owner->GetShapeshiftForm();

    // Hysteresis: enter defensive <25%, leave only when >=50%
    if (m_spells.defensiveStance)
    {
        if (hp < 25.0f)
            return FORM_DEFENSIVESTANCE;
        if (form == FORM_DEFENSIVESTANCE && hp < 50.0f)
            return FORM_DEFENSIVESTANCE;
    }

    // Interrupt needs Berserker
    if (m_spells.pummel && victim->IsNonMeleeSpellCasted(false, false, true))
        return FORM_BERSERKERSTANCE;

    bool const inMelee = m_owner->CanReachWithMeleeAutoAttack(victim);
    if (!inMelee)
    {
        // Prefer Charge (Battle); only Intercept if Charge unavailable
        if (m_spells.charge && m_owner->IsSpellReady(m_spells.charge))
            return FORM_BATTLESTANCE;
        if (m_spells.intercept && m_owner->IsSpellReady(m_spells.intercept))
            return FORM_BERSERKERSTANCE;
        return FORM_BATTLESTANCE;
    }

    // AoE: Whirlwind in Berserker
    if (m_spells.whirlwind && m_owner->GetAttackers().size() > 1 && m_owner->IsSpellReady(m_spells.whirlwind))
        return FORM_BERSERKERSTANCE;

    return FORM_BATTLESTANCE;
}

void CreaturePersonaWarrior::OnUpdate(uint32 diff)
{
    if (m_stanceLockMs > diff)
        m_stanceLockMs -= diff;
    else
        m_stanceLockMs = 0;
}

void CreaturePersonaWarrior::UpdateCombat()
{
    Unit* victim = m_owner->GetVictim();
    if (!victim)
        return;

    ShapeshiftForm const form = m_owner->GetShapeshiftForm();
    ShapeshiftForm const desired = ChooseStance(victim);
    bool const urgent = (desired == FORM_BERSERKERSTANCE && victim->IsNonMeleeSpellCasted(false, false, true))
        || (desired == FORM_DEFENSIVESTANCE && m_owner->GetHealthPercent() < 20.0f);

    if (form == FORM_NONE || form != desired)
    {
        if (SwitchToStance(desired == FORM_NONE ? FORM_BATTLESTANCE : desired, urgent || form == FORM_NONE))
            return;
    }

    ShapeshiftForm const cur = m_owner->GetShapeshiftForm();

    if (m_owner->GetPower(POWER_RAGE) < 100 && m_spells.bloodrage && Cast(m_owner, m_spells.bloodrage))
        return;

    // Skills: only use what the current stance allows — no mid-rotation stance flips
    if (cur == FORM_BERSERKERSTANCE && m_spells.pummel &&
        victim->IsNonMeleeSpellCasted(false, false, true) && Cast(victim, m_spells.pummel))
        return;

    if (m_spells.execute && victim->GetHealthPercent() < 20.0f && cur != FORM_DEFENSIVESTANCE &&
        Cast(victim, m_spells.execute))
        return;

    if (!m_owner->CanReachWithMeleeAutoAttack(victim))
    {
        if (cur == FORM_BATTLESTANCE && m_spells.charge && Cast(victim, m_spells.charge))
            return;
        if (cur == FORM_BERSERKERSTANCE && m_spells.intercept && Cast(victim, m_spells.intercept))
            return;
    }

    if (m_spells.overpower && cur == FORM_BATTLESTANCE &&
        m_owner->HasReactiveTimer(REACTIVE_OVERPOWER) &&
        m_owner->GetReactiveTarget(REACTIVE_OVERPOWER) == victim->GetObjectGuid() &&
        Cast(victim, m_spells.overpower))
    {
        m_owner->ClearReactiveTimer(REACTIVE_OVERPOWER);
        return;
    }

    if (m_spells.mortalStrike && Cast(victim, m_spells.mortalStrike))
        return;

    if (m_spells.bloodthirst && Cast(victim, m_spells.bloodthirst))
        return;

    if (cur == FORM_BERSERKERSTANCE && m_spells.whirlwind && m_owner->GetAttackers().size() > 1 &&
        Cast(victim, m_spells.whirlwind))
        return;

    if (m_spells.concussionBlow &&
        (victim->IsNonMeleeSpellCasted() || m_owner->GetHealthPercent() < 50.0f) &&
        Cast(victim, m_spells.concussionBlow))
        return;

    if (m_spells.intimidatingShout && m_owner->GetHealthPercent() < 30.0f &&
        m_owner->GetAttackers().size() > 1 && Cast(victim, m_spells.intimidatingShout))
        return;

    if (m_spells.disarm && cur != FORM_BERSERKERSTANCE && Cast(victim, m_spells.disarm))
        return;

    if (m_spells.hamstring && cur != FORM_DEFENSIVESTANCE &&
        !victim->HasUnitState(UNIT_STATE_ROOT) &&
        !victim->HasAuraType(SPELL_AURA_MOD_DECREASE_SPEED) &&
        Cast(victim, m_spells.hamstring))
        return;

    if (m_spells.rend && cur != FORM_BERSERKERSTANCE && !victim->HasAura(m_spells.rend->Id) &&
        Cast(victim, m_spells.rend))
        return;

    if (m_spells.demoShout && !victim->HasAura(m_spells.demoShout->Id) && Cast(victim, m_spells.demoShout))
        return;

    if (m_spells.battleShout && !m_owner->HasAura(m_spells.battleShout->Id) && Cast(m_owner, m_spells.battleShout))
        return;

    if (m_spells.thunderClap && cur != FORM_BERSERKERSTANCE && Cast(victim, m_spells.thunderClap))
        return;

    if (m_spells.cleave && m_owner->GetAttackers().size() > 1 && Cast(victim, m_spells.cleave))
        return;

    // dump excess rage only; classic stores rage*10
    if (m_spells.heroicStrike && m_owner->GetPower(POWER_RAGE) > 350)
        Cast(victim, m_spells.heroicStrike);
}
