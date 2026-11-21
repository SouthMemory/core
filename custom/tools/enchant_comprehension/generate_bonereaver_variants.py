#!/usr/bin/env python3
"""Prototype: Bonereaver's Edge (21153) — 3 directions × 3 ranks."""
from __future__ import annotations

import argparse
import struct
import subprocess
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
)

SOURCE_SPELL = 21153
# avoid colliding with base comprehension 30000-30177 / 35000-35177
ENCHANT_BASE = 30200
PROC_BASE = 35200  # magnitude clones only
FORMULA_BASE = 35210
UPGRADE_CHAIN_BASE = 2001

# Field indices (Spell.dbc)
F_BASE_DICE0 = 67
F_BASE_POINTS0 = 76

DIR_CHANCE, DIR_ICD, DIR_POWER = 1, 2, 3
DIR_NAMES = {
    DIR_CHANCE: "迅疾",
    DIR_ICD: "连贯",
    DIR_POWER: "强效",
}
# chance flat % per swing; icd ms after proc; power = armor reduction (positive)
CHANCE_RANKS = (8, 12, 16)
ICD_RANKS = (40000, 25000, 12000)
POWER_RANKS = (875, 1050, 1400)  # CalculateSimpleValue magnitude


def u32_from_i32(v: int) -> int:
    return struct.unpack("<I", struct.pack("<i", v))[0]


def i32_from_u32(v: int) -> int:
    return struct.unpack("<i", struct.pack("<I", v & 0xFFFFFFFF))[0]


def mysql_exec(sql: str, password: str, db: str = "mangos0") -> None:
    cmd = [
        r"C:\Program Files\MySQL\MySQL Server 5.7\bin\mysql.exe",
        "-uroot",
        f"-p{password}",
        db,
        "-e",
        sql,
    ]
    p = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if p.returncode != 0:
        raise RuntimeError(p.stderr or p.stdout)


def strip_ids(spell: DBC, ench: DBC, sla: DBC) -> None:
    spell.records = [
        r
        for r in spell.records
        if not (PROC_BASE <= r[0] < PROC_BASE + 20 or FORMULA_BASE <= r[0] < FORMULA_BASE + 20)
    ]
    ench.records = [r for r in ench.records if not (ENCHANT_BASE <= r[0] < ENCHANT_BASE + 20)]
    sla.records = [
        r
        for r in sla.records
        if not (PROC_BASE <= r[S_SPELL] < PROC_BASE + 20 or FORMULA_BASE <= r[S_SPELL] < FORMULA_BASE + 20)
    ]


def add_formula(spell_dbc: DBC, template: list[int], formula_id: int, ench_id: int, name: str) -> list[int]:
    formula = clone_u32_list(template)
    formula[F_ID] = formula_id
    for i in range(8):
        formula[F_REAGENT0 + i] = 0
        formula[F_REAGENTC0 + i] = 0
    formula[F_REAGENT0] = REAGENT_ITEM
    formula[F_REAGENTC0] = REAGENT_COUNT
    formula[F_EQ_CLASS] = 2
    formula[F_EQ_SUB] = template[F_EQ_SUB]
    formula[F_EQ_INV] = 0
    formula[F_EFFECT0] = SPELL_EFFECT_ENCHANT_ITEM
    formula[F_EFFECT0 + 1] = 0
    formula[F_EFFECT0 + 2] = 0
    formula[F_MISC0] = ench_id
    formula[F_MISC0 + 1] = 0
    formula[F_MISC0 + 2] = 0
    off = spell_dbc.add_string(name)
    for loc in range(8):
        formula[F_NAME0 + loc] = off
    spell_dbc.records.append(formula)
    return formula


def add_enchant(ench_dbc: DBC, ench_id: int, proc_spell: int, chance_pct: int, name: str) -> None:
    ench = [0] * ench_dbc.field_count
    ench[E_ID] = ench_id
    ench[E_EFF0] = ITEM_ENCHANTMENT_COMBAT_SPELL
    ench[E_PTS0] = chance_pct  # 0 => weapon default chance
    ench[E_ARG0] = proc_spell
    off = ench_dbc.add_string(name)
    for loc in range(8):
        ench[E_NAME0 + loc] = off
    ench[E_VISUAL] = 0
    ench[E_FLAGS] = ENCHANTMENT_CAN_SOULBOUND
    ench_dbc.records.append(ench)


def add_sla(sla_dbc: DBC, template: list[int], next_id: int, spell_id: int) -> int:
    sla = clone_u32_list(template)
    sla[S_ID] = next_id
    sla[S_SKILL] = SKILL_ENCHANTING
    sla[S_SPELL] = spell_id
    sla[S_MIN] = 1
    sla[S_TRIV_HIGH] = 1
    sla[S_TRIV_LOW] = 1
    sla_dbc.records.append(sla)
    return next_id + 1


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
    template = spell_dbc.by_id()[TEMPLATE_SPELL]
    src = spell_dbc.by_id()[SOURCE_SPELL]
    sla_template = next(r for r in sla_dbc.records if r[S_SPELL] == TEMPLATE_SPELL and r[S_SKILL] == SKILL_ENCHANTING)
    next_sla = sla_dbc.max_id() + 1
    strip_ids(spell_dbc, ench_dbc, sla_dbc)

    rows = []  # dicts for SQL
    formulas_by_dir: dict[int, list[int]] = {DIR_CHANCE: [], DIR_ICD: [], DIR_POWER: []}

    # --- magnitude proc clones ---
    power_procs = []
    for i, armor in enumerate(POWER_RANKS):
        pid = PROC_BASE + i
        sp = clone_u32_list(src)
        sp[F_ID] = pid
        # CalculateSimpleValue = BasePoints + BaseDice; BaseDice stays 1
        sp[F_BASE_POINTS0] = u32_from_i32(-(armor) - i32_from_u32(sp[F_BASE_DICE0]))
        pname = f"削骨之刃（强效{'I'*(i+1)}）"
        poff = spell_dbc.add_string(pname)
        for loc in range(8):
            sp[F_NAME0 + loc] = poff
        spell_dbc.records.append(sp)
        power_procs.append(pid)

    def emit(direction: int, rank: int, ench_id: int, formula_id: int, proc_spell: int, chance: int, icd: int, label: str):
        add_enchant(ench_dbc, ench_id, proc_spell, chance, label)
        add_formula(spell_dbc, template, formula_id, ench_id, f"附魔武器 - {label}")
        nonlocal next_sla
        next_sla = add_sla(sla_dbc, sla_template, next_sla, formula_id)
        formulas_by_dir[direction].append(formula_id)
        rows.append(
            {
                "source_spell": SOURCE_SPELL,
                "direction": direction,
                "rank": rank,
                "enchant_id": ench_id,
                "formula_spell": formula_id,
                "proc_spell": proc_spell,
                "chance_pct": chance,
                "icd_ms": icd,
            }
        )

    # chance direction
    for i, pct in enumerate(CHANCE_RANKS):
        emit(DIR_CHANCE, i + 1, ENCHANT_BASE + i, FORMULA_BASE + i, SOURCE_SPELL, pct, 0, f"削骨之刃：迅疾{'I'*(i+1)}")
    # icd direction
    for i, icd in enumerate(ICD_RANKS):
        emit(DIR_ICD, i + 1, ENCHANT_BASE + 3 + i, FORMULA_BASE + 3 + i, SOURCE_SPELL, 0, icd, f"削骨之刃：连贯{'I'*(i+1)}")
    # power direction
    for i, _armor in enumerate(POWER_RANKS):
        emit(
            DIR_POWER,
            i + 1,
            ENCHANT_BASE + 6 + i,
            FORMULA_BASE + 6 + i,
            power_procs[i],
            0,
            0,
            f"削骨之刃：强效{'I'*(i+1)}",
        )

    spell_dbc.records.sort(key=lambda r: r[0])
    ench_dbc.records.sort(key=lambda r: r[0])
    sla_dbc.records.sort(key=lambda r: r[0])
    for name, db in (("Spell.dbc", spell_dbc), ("SpellItemEnchantment.dbc", ench_dbc), ("SkillLineAbility.dbc", sla_dbc)):
        db.save(args.out / name)
        if args.apply_dbc:
            (args.dbc / name).write_bytes((args.out / name).read_bytes())

    sql_path = args.out / "bonereaver_variants.sql"
    lines = [
        "-- Bonereaver 21153 variants: 3 directions x 3 ranks",
        "CREATE TABLE IF NOT EXISTS `enchant_comprehension_variant` (",
        "  `source_spell` INT UNSIGNED NOT NULL,",
        "  `direction` TINYINT UNSIGNED NOT NULL COMMENT '1=chance 2=icd 3=power',",
        "  `rank` TINYINT UNSIGNED NOT NULL,",
        "  `enchant_id` INT UNSIGNED NOT NULL,",
        "  `formula_spell` INT UNSIGNED NOT NULL,",
        "  `proc_spell` INT UNSIGNED NOT NULL,",
        "  `chance_pct` INT UNSIGNED NOT NULL DEFAULT 0,",
        "  `icd_ms` INT UNSIGNED NOT NULL DEFAULT 0,",
        "  PRIMARY KEY (`source_spell`,`direction`,`rank`),",
        "  KEY `idx_formula` (`formula_spell`),",
        "  KEY `idx_enchant` (`enchant_id`)",
        ") ENGINE=InnoDB DEFAULT CHARSET=utf8;",
        f"DELETE FROM `enchant_comprehension_variant` WHERE `source_spell`={SOURCE_SPELL};",
        "INSERT INTO `enchant_comprehension_variant` "
        "(`source_spell`,`direction`,`rank`,`enchant_id`,`formula_spell`,`proc_spell`,`chance_pct`,`icd_ms`) VALUES",
    ]
    vals = [
        f"({r['source_spell']},{r['direction']},{r['rank']},{r['enchant_id']},"
        f"{r['formula_spell']},{r['proc_spell']},{r['chance_pct']},{r['icd_ms']})"
        for r in rows
    ]
    lines.append(",\n".join(vals) + ";")
    # remove plain map entry so disenchant uses variants only
    lines.append(f"DELETE FROM `enchant_comprehension_map` WHERE `source_spell`={SOURCE_SPELL};")
    # upgrade chains via force override
    lines.append(
        f"DELETE FROM `enchant_upgrade_override` WHERE `chain_id` IN "
        f"({UPGRADE_CHAIN_BASE},{UPGRADE_CHAIN_BASE+1},{UPGRADE_CHAIN_BASE+2});"
    )
    ov = []
    for d, formulas in formulas_by_dir.items():
        chain = UPGRADE_CHAIN_BASE + (d - 1)
        for rank0, fid in enumerate(formulas):
            ov.append(f"({fid},1,{chain},{rank0})")
    lines.append(
        "INSERT INTO `enchant_upgrade_override` (`spell_id`,`mode`,`chain_id`,`rank`) VALUES\n"
        + ",\n".join(ov)
        + ";"
    )
    sql_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    summary = args.out / "bonereaver_variants.txt"
    summary.write_text(
        "\n".join(
            f"dir={r['direction']} rank={r['rank']} ench={r['enchant_id']} "
            f"formula={r['formula_spell']} proc={r['proc_spell']} "
            f"chance={r['chance_pct']} icd={r['icd_ms']}"
            for r in rows
        )
        + "\n",
        encoding="utf-8",
    )

    if args.apply_sql:
        mysql_exec(sql_path.read_text(encoding="utf-8"), args.password)

    print(f"Wrote {len(rows)} variants -> {args.out}")
    if args.apply_dbc:
        print(f"Applied DBC -> {args.dbc}")
    if args.apply_sql:
        print("Applied SQL")


if __name__ == "__main__":
    main()
