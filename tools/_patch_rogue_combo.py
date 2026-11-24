from pathlib import Path

ROOT = Path(r"C:\Users\Administrator\Documents\vmangos\core\src\game")


def patch_effects():
    p = ROOT / "Spells" / "SpellEffects.cpp"
    c = p.read_text(encoding="utf-8")
    if "CreaturePersona.h" not in c:
        c = c.replace('#include "Creature.h"', '#include "Creature.h"\n#include "CreaturePersona.h"')
    start = c.find("void Spell::EffectAddComboPoints")
    if start < 0:
        raise SystemExit("EffectAddComboPoints not found")
    end = c.find("\nvoid Spell::EffectCreateHouse", start)
    if end < 0:
        raise SystemExit("EffectCreateHouse not found")
    new = """void Spell::EffectAddComboPoints(SpellEffectIndex /*effIdx*/)
{
    if (!unitTarget)
        return;

    if (damage <= 0)
        return;

    if (m_caster->GetTypeId() == TYPEID_PLAYER)
    {
        ((Player*)m_caster)->AddComboPoints(unitTarget, damage);
        ((Player*)m_caster)->SetUInt64Value(PLAYER_FIELD_COMBO_TARGET, unitTarget->GetGUID());
        return;
    }

    if (Creature* crea = m_caster->ToCreature())
        if (CreaturePersona* persona = crea->GetPersona())
            persona->AddComboPoints(int8(damage));
}

"""
    c = c[:start] + new + c[end + 1 :]
    p.write_text(c, encoding="utf-8")
    print("SpellEffects OK")


def patch_spell_finish():
    p = ROOT / "Spells" / "Spell.cpp"
    c = p.read_text(encoding="utf-8")
    if "CreaturePersona.h" not in c:
        # insert after Creature-less includes — after Player.h
        c = c.replace('#include "Player.h"', '#include "Player.h"\n#include "Creature.h"\n#include "CreaturePersona.h"')
    old = """    // Clear combo at finish state
    if (m_caster->IsPlayer() && m_spellInfo->NeedsComboPoints())
    {
        // Not drop combopoints if negative spell and if any miss on enemy exist
        bool needDrop = true;
        if (!m_spellInfo->IsPositiveSpell())
        {
            for (const auto& ihit : m_UniqueTargetInfo)
            {
                if (ihit.deleted)
                    continue;

                if (ihit.missCondition != SPELL_MISS_NONE && ihit.targetGUID != m_caster->GetObjectGuid())
                {
                    needDrop = false;
                    break;
                }
            }
        }
        if (needDrop)
            ((Player*)m_caster)->ClearComboPoints();
    }"""
    new = """    // Clear combo at finish state
    if (m_spellInfo->NeedsComboPoints())
    {
        // Not drop combopoints if negative spell and if any miss on enemy exist
        bool needDrop = true;
        if (!m_spellInfo->IsPositiveSpell())
        {
            for (const auto& ihit : m_UniqueTargetInfo)
            {
                if (ihit.deleted)
                    continue;

                if (ihit.missCondition != SPELL_MISS_NONE && ihit.targetGUID != m_caster->GetObjectGuid())
                {
                    needDrop = false;
                    break;
                }
            }
        }
        if (needDrop)
        {
            if (m_caster->IsPlayer())
                ((Player*)m_caster)->ClearComboPoints();
            else if (Creature* crea = m_caster->ToCreature())
                if (CreaturePersona* persona = crea->GetPersona())
                    persona->ClearComboPoints();
        }
    }"""
    if old not in c:
        raise SystemExit("finish combo block not found")
    c = c.replace(old, new)

    old_chk = """    if (m_casterUnit->IsPlayer() && m_spellInfo->NeedsComboPoints() && Spells::IsExplicitlySelectedUnitTarget(m_spellInfo->EffectImplicitTargetA[0]) &&
       (!m_targets.getUnitTarget() || m_targets.getUnitTarget()->GetObjectGuid() != ((Player*)m_casterUnit)->GetComboTargetGuid()))
        // warrior not have real combo-points at client side but use this way for mark allow Overpower use
        return m_casterUnit->GetClass() == CLASS_WARRIOR ? SPELL_FAILED_BAD_TARGETS : SPELL_FAILED_NO_COMBO_POINTS;"""
    new_chk = """    if (m_casterUnit->IsPlayer() && m_spellInfo->NeedsComboPoints() && Spells::IsExplicitlySelectedUnitTarget(m_spellInfo->EffectImplicitTargetA[0]) &&
       (!m_targets.getUnitTarget() || m_targets.getUnitTarget()->GetObjectGuid() != ((Player*)m_casterUnit)->GetComboTargetGuid()))
        // warrior not have real combo-points at client side but use this way for mark allow Overpower use
        return m_casterUnit->GetClass() == CLASS_WARRIOR ? SPELL_FAILED_BAD_TARGETS : SPELL_FAILED_NO_COMBO_POINTS;

    if (!m_casterUnit->IsPlayer() && m_spellInfo->NeedsComboPoints())
    {
        if (Creature const* crea = m_casterUnit->ToCreature())
            if (CreaturePersona const* persona = crea->GetPersona())
                if (persona->GetComboPoints() == 0)
                    return SPELL_FAILED_NO_COMBO_POINTS;
    }"""
    if old_chk not in c:
        raise SystemExit("CheckPower combo block not found")
    c = c.replace(old_chk, new_chk)
    p.write_text(c, encoding="utf-8")
    print("Spell.cpp OK")


def patch_spellcaster():
    p = ROOT / "Objects" / "SpellCaster.cpp"
    c = p.read_text(encoding="utf-8")
    if "CreaturePersona.h" not in c:
        c = c.replace('#include "CreatureAI.h"', '#include "CreatureAI.h"\n#include "Creature.h"\n#include "CreaturePersona.h"')
    old = """    uint8 comboPoints = pPlayer ? pPlayer->GetComboPoints() : 0;"""
    new = """    uint8 comboPoints = pPlayer ? pPlayer->GetComboPoints() : 0;
    if (!comboPoints)
        if (Creature const* crea = ToCreature())
            if (CreaturePersona const* persona = crea->GetPersona())
                comboPoints = persona->GetComboPoints();"""
    if old not in c:
        raise SystemExit("SpellCaster combo line not found")
    if "persona->GetComboPoints()" in c:
        print("SpellCaster already OK")
        return
    c = c.replace(old, new, 1)
    p.write_text(c, encoding="utf-8")
    print("SpellCaster OK")


def patch_spellentry():
    p = ROOT / "Spells" / "SpellEntry.cpp"
    c = p.read_text(encoding="utf-8")
    if "CreaturePersona.h" not in c:
        # find a suitable include
        for marker in ('#include "Player.h"', '#include "Unit.h"', '#include "SpellEntry.h"'):
            if marker in c:
                c = c.replace(marker, marker + '\n#include "Creature.h"\n#include "CreaturePersona.h"', 1)
                break
    old = """        if (duration != maxduration)
            if (Player const* pPlayer = caster->ToPlayer())
                duration += int32((maxduration - duration) * pPlayer->GetComboPoints() / 5);"""
    new = """        if (duration != maxduration)
        {
            uint8 cp = 0;
            if (Player const* pPlayer = caster->ToPlayer())
                cp = pPlayer->GetComboPoints();
            else if (Creature const* crea = caster->ToCreature())
                if (CreaturePersona const* persona = crea->GetPersona())
                    cp = persona->GetComboPoints();
            if (cp)
                duration += int32((maxduration - duration) * cp / 5);
        }"""
    if old not in c:
        raise SystemExit("SpellEntry duration block not found")
    c = c.replace(old, new)
    p.write_text(c, encoding="utf-8")
    print("SpellEntry OK")


if __name__ == "__main__":
    patch_effects()
    patch_spell_finish()
    patch_spellcaster()
    patch_spellentry()
