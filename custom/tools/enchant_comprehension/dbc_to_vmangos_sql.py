#!/usr/bin/env python3
"""Convert Zero out Spell/SLA DBC deltas into vmangos spell_template / skill_line_ability SQL."""
from __future__ import annotations

import struct
import sys
from pathlib import Path

from dbcutil import DBC

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(r"C:\Users\Administrator\Documents\mangos\tools\enchant_comprehension\out")
VM_DBC = ROOT / "data" / "5875" / "dbc"
SQL_DIR = ROOT / "core" / "sql" / "custom" / "enchant_comprehension"
BUILD = 5875
LO, HI = 35000, 56000


def u32(v: int) -> int:
    return v & 0xFFFFFFFF


def i32(v: int) -> int:
    v = u32(v)
    return v - 0x100000000 if v >= 0x80000000 else v


def f32(v: int) -> float:
    return struct.unpack("<f", struct.pack("<I", u32(v)))[0]


def esc(s: str) -> str:
    return s.replace("\\", "\\\\").replace("'", "\\'")


def spell_row_sql(dbc: DBC, r: list[int]) -> str:
    def S(off: int) -> str:
        return esc(dbc.get_string(off))

    sid = r[0]
    # DBC indices per classic SpellEntry (Zero DBCStructure comments)
    vals = {
        "entry": sid,
        "build": BUILD,
        "school": r[1],
        "category": r[2],
        "castUI": r[3],
        "dispel": r[4],
        "mechanic": r[5],
        "attributes": r[6],
        "attributesEx": r[7],
        "attributesEx2": r[8],
        "attributesEx3": r[9],
        "attributesEx4": r[10],
        "stances": r[11],
        "stancesNot": r[12],
        "targets": r[13],
        "targetCreatureType": r[14],
        "requiresSpellFocus": r[15],
        "casterAuraState": r[16],
        "targetAuraState": r[17],
        "castingTimeIndex": r[18],
        "recoveryTime": r[19],
        "categoryRecoveryTime": r[20],
        "interruptFlags": r[21],
        "auraInterruptFlags": r[22],
        "channelInterruptFlags": r[23],
        "procFlags": r[24],
        "procChance": r[25],
        "procCharges": r[26],
        "maxLevel": r[27],
        "baseLevel": r[28],
        "spellLevel": r[29],
        "durationIndex": r[30],
        "powerType": r[31],
        "manaCost": r[32],
        "manCostPerLevel": r[33],
        "manaPerSecond": r[34],
        "manaPerSecondPerLevel": r[35],
        "rangeIndex": r[36],
        "speed": f32(r[37]),
        "modelNextSpell": r[38],
        "stackAmount": r[39],
        "totem1": r[40],
        "totem2": r[41],
        "reagent1": i32(r[42]),
        "reagent2": i32(r[43]),
        "reagent3": i32(r[44]),
        "reagent4": i32(r[45]),
        "reagent5": i32(r[46]),
        "reagent6": i32(r[47]),
        "reagent7": i32(r[48]),
        "reagent8": i32(r[49]),
        "reagentCount1": r[50],
        "reagentCount2": r[51],
        "reagentCount3": r[52],
        "reagentCount4": r[53],
        "reagentCount5": r[54],
        "reagentCount6": r[55],
        "reagentCount7": r[56],
        "reagentCount8": r[57],
        "equippedItemClass": i32(r[58]),
        "equippedItemSubClassMask": i32(r[59]),
        "equippedItemInventoryTypeMask": i32(r[60]),
        "effect1": r[61],
        "effect2": r[62],
        "effect3": r[63],
        "effectDieSides1": i32(r[64]),
        "effectDieSides2": i32(r[65]),
        "effectDieSides3": i32(r[66]),
        "effectBaseDice1": r[67],
        "effectBaseDice2": r[68],
        "effectBaseDice3": r[69],
        "effectDicePerLevel1": f32(r[70]),
        "effectDicePerLevel2": f32(r[71]),
        "effectDicePerLevel3": f32(r[72]),
        "effectRealPointsPerLevel1": f32(r[73]),
        "effectRealPointsPerLevel2": f32(r[74]),
        "effectRealPointsPerLevel3": f32(r[75]),
        "effectBasePoints1": i32(r[76]),
        "effectBasePoints2": i32(r[77]),
        "effectBasePoints3": i32(r[78]),
        "effectBonusCoefficient1": -1.0,
        "effectBonusCoefficient2": -1.0,
        "effectBonusCoefficient3": -1.0,
        "effectMechanic1": r[79],
        "effectMechanic2": r[80],
        "effectMechanic3": r[81],
        "effectImplicitTargetA1": r[82],
        "effectImplicitTargetA2": r[83],
        "effectImplicitTargetA3": r[84],
        "effectImplicitTargetB1": r[85],
        "effectImplicitTargetB2": r[86],
        "effectImplicitTargetB3": r[87],
        "effectRadiusIndex1": r[88],
        "effectRadiusIndex2": r[89],
        "effectRadiusIndex3": r[90],
        "effectApplyAuraName1": r[91],
        "effectApplyAuraName2": r[92],
        "effectApplyAuraName3": r[93],
        "effectAmplitude1": r[94],
        "effectAmplitude2": r[95],
        "effectAmplitude3": r[96],
        "effectMultipleValue1": f32(r[97]),
        "effectMultipleValue2": f32(r[98]),
        "effectMultipleValue3": f32(r[99]),
        "effectChainTarget1": r[100],
        "effectChainTarget2": r[101],
        "effectChainTarget3": r[102],
        "effectItemType1": r[103],
        "effectItemType2": r[104],
        "effectItemType3": r[105],
        "effectMiscValue1": i32(r[106]),
        "effectMiscValue2": i32(r[107]),
        "effectMiscValue3": i32(r[108]),
        "effectTriggerSpell1": r[109],
        "effectTriggerSpell2": r[110],
        "effectTriggerSpell3": r[111],
        "effectPointsPerComboPoint1": f32(r[112]),
        "effectPointsPerComboPoint2": f32(r[113]),
        "effectPointsPerComboPoint3": f32(r[114]),
        "spellVisual1": r[115],
        "spellVisual2": r[116],
        "spellIconId": r[117],
        "activeIconId": r[118],
        "spellPriority": r[119],
        "name": S(r[120]),
        "nameFlags": r[128],
        "nameSubtext": S(r[129]),
        "nameSubtextFlags": r[137],
        "description": S(r[138]),
        "descriptionFlags": r[146],
        "auraDescription": S(r[147]),
        "auraDescriptionFlags": r[155],
        "manaCostPercentage": r[156],
        "startRecoveryCategory": r[157],
        "startRecoveryTime": r[158],
        "minTargetLevel": 0,
        "maxTargetLevel": r[159],
        "spellFamilyName": r[160],
        "spellFamilyFlags": (u32(r[162]) << 32) | u32(r[161]),
        "maxAffectedTargets": r[163],
        "dmgClass": r[164],
        "preventionType": r[165],
        "stanceBarOrder": i32(r[166]),
        "dmgMultiplier1": f32(r[167]),
        "dmgMultiplier2": f32(r[168]),
        "dmgMultiplier3": f32(r[169]),
        "minFactionId": r[170],
        "minReputation": r[171],
        "requiredAuraVision": r[172],
        "customFlags": 0,
        "script_name": "",
    }
    cols = ", ".join(f"`{k}`" for k in vals)
    parts = []
    for v in vals.values():
        if isinstance(v, str):
            parts.append(f"'{v}'")
        elif isinstance(v, float):
            parts.append(repr(v))
        else:
            parts.append(str(int(v)))
    return f"INSERT INTO `spell_template` ({cols}) VALUES ({', '.join(parts)});"


def main() -> int:
    SQL_DIR.mkdir(parents=True, exist_ok=True)
    spell_out, spell_vm = DBC(OUT / "Spell.dbc"), DBC(VM_DBC / "Spell.dbc")
    so, sv = spell_out.by_id(), spell_vm.by_id()
    only = sorted(i for i in (set(so) - set(sv)) if LO <= i <= HI)
    if not only:
        print("no custom spells", file=sys.stderr)
        return 1

    # Abort if any target ID already exists in DB (conflict => stop).
    import subprocess

    mysql = [
        r"C:\Program Files\MySQL\MySQL Server 5.7\bin\mysql.exe",
        "-umangos", "-pmangos", "-N", "-B", "mangos",
    ]

    def mysql_set(sql: str) -> set[int]:
        p = subprocess.run(mysql + ["-e", sql], capture_output=True, text=True, encoding="utf-8", errors="replace")
        if p.returncode != 0:
            raise SystemExit(p.stderr or p.stdout)
        return {int(x) for x in p.stdout.split() if x.strip().isdigit()}

    existing_spells = mysql_set(
        f"SELECT entry FROM spell_template WHERE entry BETWEEN {LO} AND {HI} AND build={BUILD}"
    )
    collide = sorted(set(only) & existing_spells)
    if collide:
        print(f"FAIL: spell_template already has {len(collide)} IDs in range, e.g. {collide[:10]}", file=sys.stderr)
        return 1

    spell_sql = SQL_DIR / "03_spell_template_custom.sql"
    with spell_sql.open("w", encoding="utf-8", newline="\n") as f:
        f.write("-- generated by dbc_to_vmangos_sql.py (INSERT, no REPLACE)\n")
        for sid in only:
            # spell_row_sql uses REPLACE historically; rewrite to INSERT
            line = spell_row_sql(spell_out, so[sid]).replace("REPLACE INTO", "INSERT INTO", 1)
            f.write(line + "\n")
    print(f"wrote {spell_sql} rows={len(only)}")

    # SLA: rows whose spell_id is custom (field 2)
    sla_out, sla_vm = DBC(OUT / "SkillLineAbility.dbc"), DBC(VM_DBC / "SkillLineAbility.dbc")
    vm_ids = set(sla_vm.by_id())
    db_sla_ids = mysql_set(f"SELECT id FROM skill_line_ability WHERE build={BUILD}")
    sla_sql = SQL_DIR / "04_skill_line_ability_custom.sql"
    n = 0
    with sla_sql.open("w", encoding="utf-8", newline="\n") as f:
        f.write("-- generated by dbc_to_vmangos_sql.py (INSERT, no REPLACE)\n")
        f.write(
            "INSERT INTO `skill_line_ability` "
            "(`id`,`build`,`skill_id`,`spell_id`,`race_mask`,`class_mask`,`req_skill_value`,"
            "`superseded_by_spell`,`learn_on_get_skill`,`max_value`,`min_value`,`req_train_points`) VALUES\n"
        )
        rows = []
        for r in sla_out.records:
            rid, skill, spell = r[0], r[1], r[2]
            if spell < LO or spell > HI:
                continue
            if rid in vm_ids or rid in db_sla_ids:
                print(f"FAIL: SLA id {rid} already used", file=sys.stderr)
                return 1
            race, cls = r[3], r[4]
            req_skill, superseded, learn_on, mx, mn = r[7], r[8], r[9], r[10], r[11]
            req_train = r[14] if len(r) > 14 else 0
            rows.append(
                f"({rid},{BUILD},{skill},{spell},{race},{cls},{req_skill},"
                f"{superseded},{learn_on},{mx},{mn},{req_train})"
            )
        if not rows:
            print("no SLA rows", file=sys.stderr)
            return 1
        f.write(",\n".join(rows) + ";\n")
        n = len(rows)
    print(f"wrote {sla_sql} rows={n}")

    opt = SQL_DIR / "05_spell_proc_event_optional.sql"
    opt.write_text(
        "-- optional: no Zero spell_proc_event export in this pass; fill if迅疾档需 customChance\n",
        encoding="utf-8",
    )
    print(f"wrote {opt}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
