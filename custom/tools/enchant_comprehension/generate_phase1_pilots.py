#!/usr/bin/env python3
"""Phase-1 pilots: Crusader 3-dir + Bonereaver migrated to enchant_line."""
from __future__ import annotations

import argparse
import shutil
import struct
import subprocess
import sys
from pathlib import Path

from dbcutil import DBC
from generate import (
    DEFAULT_DBC,
    ENCHANTMENT_CAN_SOULBOUND,
    F_EFFECT0,
    F_EQ_CLASS,
    F_EQ_INV,
    F_EQ_SUB,
    F_ID,
    F_MISC0,
    F_NAME0,
    F_REAGENT0,
    F_REAGENTC0,
    ITEM_ENCHANTMENT_COMBAT_SPELL,
    OUT,
    REAGENT_COUNT,
    REAGENT_ITEM,
    ROOT,
    S_ID,
    S_MIN,
    S_SKILL,
    S_SPELL,
    S_TRIV_HIGH,
    S_TRIV_LOW,
    SKILL_ENCHANTING,
    SPELL_EFFECT_ENCHANT_ITEM,
    TEMPLATE_SPELL,
    E_ARG0,
    E_EFF0,
    E_FLAGS,
    E_ID,
    E_NAME0,
    E_PTS0,
    E_VISUAL,
    clone_u32_list,
    mysql_query,
)

CRUSADER_FORMULA = 20034
CRUSADER_ENCHANT = 1900
BONEREAVER_SPELL = 21153
LINE_CRUSADER = 1
LINE_BONEREAVER = 2

DIR_BASE, DIR_CHANCE, DIR_POWER, DIR_TIME = 0, 1, 2, 3
DIR_LABEL = {DIR_CHANCE: "迅疾", DIR_POWER: "强效", DIR_TIME: "延展"}
ROMAN = ("I", "II", "III")
# 1.25 / 1.5 / 2.0
SCALE = ((5, 4), (3, 2), (2, 1))
CHANCE_RANKS = (8, 12, 16)
# SpellDuration.dbc ids: 20s, 25s, 30s and 12s, 15s, 20s
CRUSADER_DUR = (18, 63, 9)
BONEREAVER_DUR = (29, 8, 18)

# formulas 35300-35329, proc clones 35340-35351, enchants 30300-30329
SPELL_LO, SPELL_HI = 35300, 35360
ENCH_LO, ENCH_HI = 30300, 30340
F_DIE0 = 64
F_DICE0 = 67
F_BASE0 = 76
F_DURATION = 30
F_RANK0 = 129
F_DESC0 = 138  # 8 locales; zhCN is 142
F_TIP0 = 147  # 8 locales; zhCN is 151

# class 2, subclass unlocked (0 = any). Inv: 1h / 2h / main / off.
WEAPON_INV = (1 << 13) | (1 << 17) | (1 << 21) | (1 << 22)


def u32_from_i32(v: int) -> int:
    return struct.unpack("<I", struct.pack("<i", int(v)))[0]


def i32_from_u32(v: int) -> int:
    return struct.unpack("<i", struct.pack("<I", v & 0xFFFFFFFF))[0]


def scale(v: int, num: int, den: int) -> int:
    return (v * num + den // 2) // den


def mysql_exec(sql: str, password: str, db: str = "mangos0") -> None:
    cmd = [
        r"C:\Program Files\MySQL\MySQL Server 5.7\bin\mysql.exe",
        "-uroot",
        f"-p{password}",
        "--default-character-set=utf8",
        db,
        "-e",
        sql,
    ]
    p = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if p.returncode != 0:
        raise RuntimeError(p.stderr or p.stdout)


def set_name(spell_dbc: DBC, sp: list[int], name: str) -> None:
    off = spell_dbc.add_string(name)
    for loc in range(8):
        sp[F_NAME0 + loc] = off
    for loc in range(8):
        sp[F_RANK0 + loc] = 0


def set_loc_text(spell_dbc: DBC, sp: list[int], base: int, text: str, only_existing: bool) -> None:
    """Point locales at a new string. Never rewrites bytes already in the string block."""
    if only_existing and not any(sp[base + loc] for loc in range(8)):
        return
    off = spell_dbc.add_string(text)
    for loc in range(8):
        if not only_existing or sp[base + loc]:
            sp[base + loc] = off


def simple_value(sp: list[int], eff: int) -> int:
    return i32_from_u32(sp[F_BASE0 + eff]) + int(sp[F_DICE0 + eff])


def effect_range(sp: list[int], eff: int) -> tuple[int, int]:
    base = i32_from_u32(sp[F_BASE0 + eff])
    dice = int(sp[F_DICE0 + eff])
    sides = int(sp[F_DIE0 + eff])
    if sides <= 1:
        return (base + dice, base + dice)
    lo, hi = (sides, dice) if dice >= sides else (dice, sides)
    return (base + lo, base + hi)


def client_data_dir() -> Path | None:
    cands = [
        ROOT / "wow_cn_1.12" / "Data",
        Path.home() / "Downloads" / "Download" / "wow_cn_1.12" / "Data",
    ]
    for c in cands:
        if c.is_dir():
            return c
    return None


def add_enchant(ench_dbc: DBC, ench_id: int, proc_spell: int, chance: int, name: str, visual: int) -> None:
    ench = [0] * ench_dbc.field_count
    ench[E_ID] = ench_id
    ench[E_EFF0] = ITEM_ENCHANTMENT_COMBAT_SPELL
    ench[E_PTS0] = chance
    ench[E_ARG0] = proc_spell
    off = ench_dbc.add_string(name)
    for loc in range(8):
        ench[E_NAME0 + loc] = off
    ench[E_VISUAL] = visual
    ench[E_FLAGS] = 0
    if ench[E_FLAGS] & ENCHANTMENT_CAN_SOULBOUND:
        raise RuntimeError(f"enchant {ench_id} soulbound")
    ench_dbc.records.append(ench)


def add_formula(spell_dbc: DBC, template: list[int], formula_id: int, ench_id: int, name: str, desc: str) -> None:
    formula = clone_u32_list(template)
    formula[F_ID] = formula_id
    for i in range(8):
        formula[F_REAGENT0 + i] = 0
        formula[F_REAGENTC0 + i] = 0
    formula[F_REAGENT0] = REAGENT_ITEM
    formula[F_REAGENTC0] = REAGENT_COUNT
    formula[F_EQ_CLASS] = 2
    formula[F_EQ_SUB] = 0
    formula[F_EQ_INV] = WEAPON_INV
    formula[F_EFFECT0] = SPELL_EFFECT_ENCHANT_ITEM
    formula[F_EFFECT0 + 1] = 0
    formula[F_EFFECT0 + 2] = 0
    formula[F_MISC0] = ench_id
    formula[F_MISC0 + 1] = 0
    formula[F_MISC0 + 2] = 0
    set_name(spell_dbc, formula, name)
    set_loc_text(spell_dbc, formula, F_DESC0, desc, only_existing=False)
    set_loc_text(spell_dbc, formula, F_TIP0, desc, only_existing=True)
    spell_dbc.records.append(formula)


def add_sla(sla_dbc: DBC, template: list[int], next_id: int, spell_id: int, trivial: tuple[int, int]) -> int:
    sla = clone_u32_list(template)
    sla[S_ID] = next_id
    sla[S_SKILL] = SKILL_ENCHANTING
    sla[S_SPELL] = spell_id
    sla[S_MIN] = 1
    sla[S_TRIV_HIGH] = trivial[0]
    sla[S_TRIV_LOW] = trivial[1]
    sla_dbc.records.append(sla)
    return next_id + 1


def ours_spell(sid: int) -> bool:
    return SPELL_LO <= sid < SPELL_HI


def ours_ench(eid: int) -> bool:
    return ENCH_LO <= eid < ENCH_HI


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dbc", type=Path, default=DEFAULT_DBC)
    ap.add_argument("--out", type=Path, default=OUT)
    ap.add_argument("--password", default="deepwise")
    ap.add_argument("--apply-dbc", action="store_true")
    ap.add_argument("--apply-sql", action="store_true")
    args = ap.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)

    spell_dbc = DBC(args.dbc / "Spell.dbc")
    ench_dbc = DBC(args.dbc / "SpellItemEnchantment.dbc")
    sla_dbc = DBC(args.dbc / "SkillLineAbility.dbc")
    dur_dbc = DBC(args.dbc / "SpellDuration.dbc")
    spells = spell_dbc.by_id()
    enchants = ench_dbc.by_id()
    durations = dur_dbc.by_id()

    formula_tmpl = spells[TEMPLATE_SPELL]
    crusader_formula = spells[CRUSADER_FORMULA]
    crusader_ench = enchants[CRUSADER_ENCHANT]
    proc_id = crusader_ench[E_ARG0]
    if crusader_formula[F_MISC0] != CRUSADER_ENCHANT or proc_id == 0:
        raise SystemExit(f"crusader link broken formula misc={crusader_formula[F_MISC0]} proc={proc_id}")
    proc_src = spells[proc_id]
    bone_src = spells[BONEREAVER_SPELL]
    sla_crus = next(r for r in sla_dbc.records if r[S_SPELL] == CRUSADER_FORMULA and r[S_SKILL] == SKILL_ENCHANTING)
    sla_tmpl = next(r for r in sla_dbc.records if r[S_SPELL] == TEMPLATE_SPELL and r[S_SKILL] == SKILL_ENCHANTING)
    crus_trivial = (sla_crus[S_TRIV_HIGH], sla_crus[S_TRIV_LOW])

    str_base = simple_value(proc_src, 0)
    heal_lo, heal_hi = effect_range(proc_src, 1)
    armor_base = -simple_value(bone_src, 0)
    if str_base <= 0 or heal_lo <= 0 or armor_base <= 0:
        raise SystemExit(f"bad base magnitudes str={str_base} heal={heal_lo}-{heal_hi} armor={armor_base}")

    def dur_ms(idx: int) -> int:
        return i32_from_u32(durations[idx][1])

    base_crus_ms = dur_ms(proc_src[F_DURATION])
    base_bone_ms = dur_ms(bone_src[F_DURATION])
    for idx in CRUSADER_DUR:
        if dur_ms(idx) <= base_crus_ms:
            raise SystemExit(f"crusader duration {idx}={dur_ms(idx)} not above {base_crus_ms}")
    for idx in BONEREAVER_DUR:
        if dur_ms(idx) <= base_bone_ms:
            raise SystemExit(f"bonereaver duration {idx}={dur_ms(idx)} not above {base_bone_ms}")

    spell_dbc.records = [r for r in spell_dbc.records if not ours_spell(r[0])]
    ench_dbc.records = [r for r in ench_dbc.records if not ours_ench(r[0])]
    sla_dbc.records = [r for r in sla_dbc.records if not ours_spell(r[S_SPELL])]
    next_sla = sla_dbc.max_id() + 1

    rows: list[dict] = []

    def emit(
        line_id: int,
        direction: int,
        rank: int,
        ench_id: int,
        formula_id: int,
        proc_spell: int,
        chance: int,
        label: str,
        desc: str,
        formula_template: list[int],
        sla_template: list[int],
        trivial: tuple[int, int],
        visual: int,
        make_dbc: bool,
    ) -> None:
        nonlocal next_sla
        if formula_id >= 65536 or proc_spell >= 65536 or ench_id >= 65536:
            raise RuntimeError(f"id overflow formula={formula_id} proc={proc_spell} ench={ench_id}")
        if make_dbc:
            add_enchant(ench_dbc, ench_id, proc_spell, chance, label, visual)
            add_formula(spell_dbc, formula_template, formula_id, ench_id, f"附魔武器 - {label}", desc)
            next_sla = add_sla(sla_dbc, sla_template, next_sla, formula_id, trivial)
        rows.append(
            {
                "line_id": line_id,
                "direction": direction,
                "rank": rank,
                "formula_spell": formula_id,
                "enchant_id": ench_id,
                "proc_spell": proc_spell,
                "chance_pct": chance,
                "icd_ms": 0,
            }
        )

    def clone_proc(src: list[int], sid: int, name: str) -> list[int]:
        sp = clone_u32_list(src)
        sp[F_ID] = sid
        set_name(spell_dbc, sp, name)
        spell_dbc.records.append(sp)
        return sp

    # --- Crusader: rank 0 is vanilla; dirs 1..3 x ranks 1..3 ---
    rows.append(
        {
            "line_id": LINE_CRUSADER,
            "direction": DIR_BASE,
            "rank": 0,
            "formula_spell": CRUSADER_FORMULA,
            "enchant_id": CRUSADER_ENCHANT,
            "proc_spell": proc_id,
            "chance_pct": 0,
            "icd_ms": 0,
        }
    )
    frozen_desc = {
        CRUSADER_FORMULA: (
            crusader_formula[F_DESC0 + 4],
            spell_dbc.get_string(crusader_formula[F_DESC0 + 4]),
        ),
        TEMPLATE_SPELL: (
            formula_tmpl[F_DESC0 + 4],
            spell_dbc.get_string(formula_tmpl[F_DESC0 + 4]),
        ),
    }

    def crus_desc(kind: str, proc: int, chance: int = 0) -> str:
        if kind == "chance":
            return (
                f"永久附魔一件武器，使其有{chance}%的几率在攻击时触发十字军："
                f"回复${proc}s2点生命值，力量提高${proc}s1点，持续${proc}d。"
            )
        title = "强化十字军" if kind == "power" else "延展十字军"
        return (
            f"永久附魔一件武器，使其在攻击时触发{title}："
            f"回复${proc}s2点生命值，力量提高${proc}s1点，持续${proc}d。"
        )

    def bone_desc(kind: str, proc: int, chance: int = 0) -> str:
        if kind == "chance":
            return (
                f"永久附魔一件武器，使其有{chance}%的几率在攻击时触发削骨之刃："
                f"忽略目标${proc}s1点护甲，持续${proc}d。"
            )
        title = {"base": "削骨之刃", "power": "强化削骨之刃", "time": "延展削骨之刃"}[kind]
        return (
            f"永久附魔一件武器，使其在攻击时触发{title}："
            f"忽略目标${proc}s1点护甲，持续${proc}d。"
        )

    crus_visual = crusader_ench[E_VISUAL]
    for i, (num, den) in enumerate(SCALE):
        power = clone_proc(proc_src, 35340 + i, f"神圣力量（强效{ROMAN[i]}）")
        power[F_BASE0] = u32_from_i32(scale(str_base, num, den) - int(power[F_DICE0]))
        lo = scale(heal_lo, num, den)
        hi = scale(heal_hi, num, den)
        dice = int(power[F_DICE0 + 1])
        power[F_BASE0 + 1] = u32_from_i32(lo - dice)
        power[F_DIE0 + 1] = hi - lo + dice
        timed = clone_proc(proc_src, 35343 + i, f"神圣力量（延展{ROMAN[i]}）")
        timed[F_DURATION] = CRUSADER_DUR[i]

    for i, chance in enumerate(CHANCE_RANKS):
        emit(
            LINE_CRUSADER, DIR_CHANCE, i + 1, 30300 + i, 35300 + i, proc_id, chance,
            f"十字军：迅疾{ROMAN[i]}", crus_desc("chance", proc_id, chance),
            crusader_formula, sla_crus, crus_trivial, crus_visual, True,
        )
    for i in range(3):
        emit(
            LINE_CRUSADER, DIR_POWER, i + 1, 30303 + i, 35303 + i, 35340 + i, 0,
            f"十字军：强效{ROMAN[i]}", crus_desc("power", 35340 + i),
            crusader_formula, sla_crus, crus_trivial, crus_visual, True,
        )
    for i in range(3):
        emit(
            LINE_CRUSADER, DIR_TIME, i + 1, 30306 + i, 35306 + i, 35343 + i, 0,
            f"十字军：延展{ROMAN[i]}", crus_desc("time", 35343 + i),
            crusader_formula, sla_crus, crus_trivial, crus_visual, True,
        )

    # --- Bonereaver: rank 0 is a new base formula; same three directions ---
    bone_visual = 0
    emit(
        LINE_BONEREAVER, DIR_BASE, 0, 30320, 35320, BONEREAVER_SPELL, 0,
        "削骨之刃", bone_desc("base", BONEREAVER_SPELL),
        formula_tmpl, sla_tmpl, (1, 1), bone_visual, True,
    )
    for i, (num, den) in enumerate(SCALE):
        power = clone_proc(bone_src, 35346 + i, f"削骨之刃（强效{ROMAN[i]}）")
        armor = scale(armor_base, num, den)
        power[F_BASE0] = u32_from_i32(-armor - int(power[F_DICE0]))
        timed = clone_proc(bone_src, 35349 + i, f"削骨之刃（延展{ROMAN[i]}）")
        timed[F_DURATION] = BONEREAVER_DUR[i]
    for i, chance in enumerate(CHANCE_RANKS):
        emit(
            LINE_BONEREAVER, DIR_CHANCE, i + 1, 30321 + i, 35321 + i, BONEREAVER_SPELL, chance,
            f"削骨之刃：迅疾{ROMAN[i]}", bone_desc("chance", BONEREAVER_SPELL, chance),
            formula_tmpl, sla_tmpl, (1, 1), bone_visual, True,
        )
    for i in range(3):
        emit(
            LINE_BONEREAVER, DIR_POWER, i + 1, 30324 + i, 35324 + i, 35346 + i, 0,
            f"削骨之刃：强效{ROMAN[i]}", bone_desc("power", 35346 + i),
            formula_tmpl, sla_tmpl, (1, 1), bone_visual, True,
        )
    for i in range(3):
        emit(
            LINE_BONEREAVER, DIR_TIME, i + 1, 30327 + i, 35327 + i, 35349 + i, 0,
            f"削骨之刃：延展{ROMAN[i]}", bone_desc("time", 35349 + i),
            formula_tmpl, sla_tmpl, (1, 1), bone_visual, True,
        )

    by_spell = spell_dbc.by_id()
    for i, (num, den) in enumerate(SCALE):
        sp = by_spell[35340 + i]
        if simple_value(sp, 0) != scale(str_base, num, den):
            raise RuntimeError(f"crusader str clone {sp[0]} -> {simple_value(sp, 0)}")
        lo, hi = effect_range(sp, 1)
        if (lo, hi) != (scale(heal_lo, num, den), scale(heal_hi, num, den)):
            raise RuntimeError(f"crusader heal clone {sp[0]} -> {lo}-{hi}")
        if by_spell[35343 + i][F_DURATION] != CRUSADER_DUR[i]:
            raise RuntimeError("crusader duration clone mismatch")
        if simple_value(by_spell[35346 + i], 0) != -scale(armor_base, num, den):
            raise RuntimeError("bonereaver armor clone mismatch")
        if by_spell[35349 + i][F_DURATION] != BONEREAVER_DUR[i]:
            raise RuntimeError("bonereaver duration clone mismatch")
    for r in ench_dbc.records:
        if ours_ench(r[0]) and (r[E_FLAGS] & ENCHANTMENT_CAN_SOULBOUND):
            raise RuntimeError(f"soulbound enchant {r[0]}")
    tmpl_offs = {off for off, _ in frozen_desc.values()}
    for sid, (off, text) in frozen_desc.items():
        live = spell_dbc.by_id()[sid]
        if live[F_DESC0 + 4] != off or spell_dbc.get_string(off) != text:
            raise RuntimeError(f"template {sid} description mutated")
    for sp in spell_dbc.records:
        if sp[F_EFFECT0] != SPELL_EFFECT_ENCHANT_ITEM or not ours_spell(sp[0]):
            continue
        desc_off = sp[F_DESC0 + 4]
        desc = spell_dbc.get_string(desc_off)
        if desc_off in tmpl_offs or not desc:
            raise RuntimeError(f"formula {sp[0]} still uses template description")
        if "伤害+1" in desc:
            raise RuntimeError(f"formula {sp[0]} still says 伤害+1")
        if sp[0] not in range(35300, 35303) and "$20007" in desc:
            raise RuntimeError(f"formula {sp[0]} hardcodes $20007")
    print("35303", spell_dbc.get_string(by_spell[35303][F_DESC0 + 4]))
    print("35320", spell_dbc.get_string(by_spell[35320][F_DESC0 + 4]))

    spell_dbc.records.sort(key=lambda r: r[0])
    ench_dbc.records.sort(key=lambda r: r[0])
    sla_dbc.records.sort(key=lambda r: r[0])
    for name, db in (
        ("Spell.dbc", spell_dbc),
        ("SpellItemEnchantment.dbc", ench_dbc),
        ("SkillLineAbility.dbc", sla_dbc),
    ):
        db.save(args.out / name)
        if args.apply_dbc:
            (args.dbc / name).write_bytes((args.out / name).read_bytes())

    lines = [
        "-- Phase-1 pilots: crusader line 1, bonereaver line 2",
        "-- dir 0 = shared base, 1 = 迅疾, 2 = 强效, 3 = 延展",
        "START TRANSACTION;",
        f"DELETE FROM `enchant_line_rank` WHERE `line_id` IN ({LINE_CRUSADER},{LINE_BONEREAVER});",
        f"DELETE FROM `enchant_line` WHERE `line_id` IN ({LINE_CRUSADER},{LINE_BONEREAVER});",
        "INSERT INTO `enchant_line` "
        "(`line_id`,`base_spell`,`base_enchant_id`,`slot_mask`,`eq_class`,`eq_subclass`,`eq_inv`,`axis_kind`) VALUES",
        f"({LINE_CRUSADER},{CRUSADER_FORMULA},{CRUSADER_ENCHANT},{WEAPON_INV},2,0,{WEAPON_INV},1),",
        f"({LINE_BONEREAVER},{BONEREAVER_SPELL},30320,{WEAPON_INV},2,0,{WEAPON_INV},1);",
        "INSERT INTO `enchant_line_rank` "
        "(`line_id`,`direction`,`rank`,`formula_spell`,`enchant_id`,`proc_spell`,`chance_pct`,`icd_ms`) VALUES",
    ]
    vals = [
        f"({r['line_id']},{r['direction']},{r['rank']},{r['formula_spell']},"
        f"{r['enchant_id']},{r['proc_spell']},{r['chance_pct']},{r['icd_ms']})"
        for r in rows
    ]
    lines.append(",\n".join(vals) + ";")
    lines.append("COMMIT;")
    sql_path = args.out / "phase1_pilots.sql"
    sql_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    (args.out / "phase1_pilots.txt").write_text(
        "\n".join(
            f"line={r['line_id']} dir={r['direction']} rank={r['rank']} ench={r['enchant_id']} "
            f"formula={r['formula_spell']} proc={r['proc_spell']} chance={r['chance_pct']} icd={r['icd_ms']}"
            for r in rows
        )
        + "\n",
        encoding="utf-8",
    )

    if args.apply_sql:
        mysql_exec(sql_path.read_text(encoding="utf-8"), args.password)
        check = mysql_query(
            "SELECT line_id, base_spell, base_enchant_id, axis_kind FROM enchant_line ORDER BY line_id;"
            "SELECT line_id, direction, GROUP_CONCAT(CONCAT(rank,':',formula_spell) ORDER BY rank) "
            "FROM enchant_line_rank GROUP BY line_id, direction ORDER BY line_id, direction;",
            args.password,
        )
        print("SQL check:")
        for row in check:
            print("\t".join(row))

    subprocess.run([sys.executable, str(Path(__file__).with_name("_make_patch.py"))], check=True)
    zz = args.out / "patch-zhCN-ZZ.mpq"
    p3 = args.out / "patch-3.MPQ"
    shutil.copy2(zz, p3)
    print(
        f"pilots={len(rows)} proc={proc_id} str={str_base} heal={heal_lo}-{heal_hi} "
        f"armor={armor_base} crus_ms={base_crus_ms} bone_ms={base_bone_ms} -> {args.out}"
    )
    print(f"patch {p3}")
    if args.apply_dbc:
        dest_dir = client_data_dir()
        if dest_dir:
            copied = dest_dir / "patch-3.MPQ"
            try:
                shutil.copy2(p3, copied)
                print(f"copied {copied}")
            except PermissionError:
                print(f"client patch locked, left {p3} (close WoW and copy over {copied})")
    if args.apply_dbc:
        print(f"Applied DBC -> {args.dbc}")
    if args.apply_sql:
        print("Applied SQL")


if __name__ == "__main__":
    main()
