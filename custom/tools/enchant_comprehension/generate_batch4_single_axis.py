#!/usr/bin/env python3
"""Batch 4: A-family pure passive on-equip → single-axis enchant_line (ranks 0..3)."""
from __future__ import annotations

import argparse
import shutil
import struct
import subprocess
import sys
from collections import Counter, defaultdict
from pathlib import Path

from dbcutil import DBC
from generate import (
    DEFAULT_DBC,
    ENCHANTMENT_CAN_SOULBOUND,
    F_EFFECT0,
    F_ID,
    F_MISC0,
    F_NAME0,
    F_REAGENT0,
    F_REAGENTC0,
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
    clone_u32_list,
    load_blacklist,
    BLACKLIST,
    mysql_query,
    spell_rejected,
)

DIR_MAIN = 0
ROMAN = ("", "I", "II", "III")  # rank0 unlabeled
SCALE = ((5, 4), (3, 2), (2, 1))  # ranks 1..3
ITEM_ENCHANTMENT_EQUIP_SPELL = 3

FORMULA_BASE = 52000
AURA_CLONE_BASE = 54000
ENCHANT_BASE = 36000
SPELL_LO, SPELL_HI = 52000, 60000
ENCH_LO, ENCH_HI = 36000, 40000
LINE_ID_BASE = 300

F_EQ_CLASS, F_EQ_SUB, F_EQ_INV = 58, 59, 60
F_DICE0, F_BASE0 = 67, 76
F_AURA0, F_AURA_PERIOD0, F_TRIGGER0 = 91, 94, 109
F_RANK0, F_DESC0, F_TIP0, F_NAME4 = 129, 138, 147, 124
SPELL_EFFECT_APPLY_AURA = 6
B_AURAS = {3, 8, 23, 42, 43}


def u32_from_i32(v: int) -> int:
    return struct.unpack("<I", struct.pack("<i", int(v)))[0]


def i32_from_u32(v: int) -> int:
    return struct.unpack("<i", struct.pack("<I", v & 0xFFFFFFFF))[0]


def scale(v: int, num: int, den: int) -> int:
    return (v * num + den // 2) // den


def rank_mag(base: int, rank: int) -> int:
    if rank <= 0:
        return base
    scaled = scale(abs(base), *SCALE[rank - 1])
    if scaled <= abs(base):
        scaled = abs(base) + rank
    return scaled if base >= 0 else -scaled


def mysql_exec(sql: str, password: str, db: str = "mangos0") -> None:
    cmd = [
        r"C:\Program Files\MySQL\MySQL Server 5.7\bin\mysql.exe",
        "-uroot",
        f"-p{password}",
        "--default-character-set=utf8",
        db,
    ]
    p = subprocess.run(cmd, input=sql, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if p.returncode != 0:
        raise RuntimeError(p.stderr or p.stdout)


def set_name(spell_dbc: DBC, sp: list[int], name: str) -> None:
    off = spell_dbc.add_string(name)
    for loc in range(8):
        sp[F_NAME0 + loc] = off
    for loc in range(8):
        sp[F_RANK0 + loc] = 0


def set_loc_text(spell_dbc: DBC, sp: list[int], base: int, text: str) -> None:
    off = spell_dbc.add_string(text)
    for loc in range(8):
        sp[base + loc] = off


def simple_value(sp: list[int], eff: int) -> int:
    return i32_from_u32(sp[F_BASE0 + eff]) + int(sp[F_DICE0 + eff])


def spell_label(spell_dbc: DBC, sp: list[int]) -> str:
    for off in (sp[F_NAME4], sp[F_NAME0]):
        name = spell_dbc.get_string(off)
        if name:
            return name
    return f"特效{sp[F_ID]}"


def client_data_dir() -> Path | None:
    for c in (ROOT / "wow_cn_1.12" / "Data", Path.home() / "Downloads" / "Download" / "wow_cn_1.12" / "Data"):
        if c.is_dir():
            return c
    return None


def add_enchant(ench_dbc: DBC, ench_id: int, aura_spell: int, name: str) -> None:
    ench = [0] * ench_dbc.field_count
    ench[E_ID] = ench_id
    ench[E_EFF0] = ITEM_ENCHANTMENT_EQUIP_SPELL
    ench[E_PTS0] = 0
    ench[E_ARG0] = aura_spell
    off = ench_dbc.add_string(name)
    for loc in range(8):
        ench[E_NAME0 + loc] = off
    ench[E_FLAGS] = 0
    ench_dbc.records.append(ench)


def add_formula(
    spell_dbc: DBC,
    template: list[int],
    formula_id: int,
    ench_id: int,
    name: str,
    desc: str,
    eq_class: int,
    eq_inv: int,
) -> None:
    formula = clone_u32_list(template)
    formula[F_ID] = formula_id
    for i in range(8):
        formula[F_REAGENT0 + i] = 0
        formula[F_REAGENTC0 + i] = 0
    formula[F_REAGENT0] = REAGENT_ITEM
    formula[F_REAGENTC0] = REAGENT_COUNT
    formula[F_EQ_CLASS] = eq_class
    formula[F_EQ_SUB] = 0
    formula[F_EQ_INV] = eq_inv
    formula[F_EFFECT0] = SPELL_EFFECT_ENCHANT_ITEM
    formula[F_EFFECT0 + 1] = 0
    formula[F_EFFECT0 + 2] = 0
    formula[F_MISC0] = ench_id
    formula[F_MISC0 + 1] = 0
    formula[F_MISC0 + 2] = 0
    set_name(spell_dbc, formula, name)
    set_loc_text(spell_dbc, formula, F_DESC0, desc)
    if any(template[F_TIP0 + loc] for loc in range(8)):
        set_loc_text(spell_dbc, formula, F_TIP0, desc)
    spell_dbc.records.append(formula)


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


def ours_spell(sid: int) -> bool:
    return SPELL_LO <= sid < SPELL_HI


def ours_ench(eid: int) -> bool:
    return ENCH_LO <= eid < ENCH_HI


def is_b_family(sp: list[int]) -> bool:
    for e in range(3):
        if sp[F_EFFECT0 + e] != SPELL_EFFECT_APPLY_AURA:
            continue
        if sp[F_AURA0 + e] in B_AURAS or sp[F_TRIGGER0 + e] or sp[F_AURA_PERIOD0 + e]:
            return True
    return False


def fetch_sources(password: str, spells: dict[int, list[int]], spell_dbc: DBC) -> list[dict]:
    covered = {
        int(r[0])
        for r in mysql_query(
            f"SELECT base_spell FROM enchant_line WHERE base_spell<>0 AND line_id<{LINE_ID_BASE}",
            password,
        )
    }
    blacklist = load_blacklist(BLACKLIST)
    sql = """
SELECT entry, name, class, InventoryType,
 spellid_1, spelltrigger_1, spellid_2, spelltrigger_2,
 spellid_3, spelltrigger_3, spellid_4, spelltrigger_4,
 spellid_5, spelltrigger_5
FROM item_template
WHERE (spellid_1>0 AND spelltrigger_1=1) OR (spellid_2>0 AND spelltrigger_2=1)
   OR (spellid_3>0 AND spelltrigger_3=1) OR (spellid_4>0 AND spelltrigger_4=1)
   OR (spellid_5>0 AND spelltrigger_5=1)
"""
    by: dict[int, dict] = {}
    for row in mysql_query(sql, password):
        pairs = [
            (int(row[4]), int(row[5])),
            (int(row[6]), int(row[7])),
            (int(row[8]), int(row[9])),
            (int(row[10]), int(row[11])),
            (int(row[12]), int(row[13])),
        ]
        sid = next((sp for sp, tr in pairs if sp and tr == 1), 0)
        if not sid:
            continue
        rec = by.setdefault(sid, {"class": Counter(), "inv": Counter(), "items": []})
        rec["class"][int(row[2])] += 1
        rec["inv"][int(row[3])] += 1
        if len(rec["items"]) < 3:
            rec["items"].append((int(row[0]), row[1]))

    out: list[dict] = []
    for sid, meta in sorted(by.items()):
        if sid in covered or sid in blacklist or sid not in spells:
            continue
        if spell_rejected(spell_dbc, sid):
            continue
        sp = spells[sid]
        if is_b_family(sp):
            continue
        mags = []
        for e in range(3):
            if sp[F_EFFECT0 + e] == SPELL_EFFECT_APPLY_AURA and simple_value(sp, e):
                mags.append((e, simple_value(sp, e)))
        if not mags:
            continue
        inv_mask = 0
        for inv in meta["inv"]:
            if 0 <= inv < 32:
                inv_mask |= 1 << inv
        if not inv_mask:
            continue
        out.append(
            {
                "aura": sid,
                "mags": mags,
                "eq_class": meta["class"].most_common(1)[0][0],
                "eq_inv": inv_mask,
                "items": meta["items"],
            }
        )
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dbc", type=Path, default=DEFAULT_DBC)
    ap.add_argument("--out", type=Path, default=OUT)
    ap.add_argument("--password", default="deepwise")
    ap.add_argument("--apply-dbc", action="store_true")
    ap.add_argument("--apply-sql", action="store_true")
    ap.add_argument("--limit", type=int, default=0)
    args = ap.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)

    spell_dbc = DBC(args.dbc / "Spell.dbc")
    ench_dbc = DBC(args.dbc / "SpellItemEnchantment.dbc")
    sla_dbc = DBC(args.dbc / "SkillLineAbility.dbc")
    spells = spell_dbc.by_id()
    formula_tmpl = spells[TEMPLATE_SPELL]
    sla_tmpl = next(r for r in sla_dbc.records if r[S_SPELL] == TEMPLATE_SPELL and r[S_SKILL] == SKILL_ENCHANTING)

    sources = fetch_sources(args.password, spells, spell_dbc)
    if args.limit:
        sources = sources[: args.limit]

    spell_dbc.records = [r for r in spell_dbc.records if not ours_spell(r[0])]
    ench_dbc.records = [r for r in ench_dbc.records if not ours_ench(r[0])]
    sla_dbc.records = [r for r in sla_dbc.records if not ours_spell(r[S_SPELL])]
    next_sla = sla_dbc.max_id() + 1
    spells = spell_dbc.by_id()

    line_rows: list[tuple] = []
    rank_rows: list[dict] = []
    summary: list[str] = []
    next_formula, next_aura, next_ench = FORMULA_BASE, AURA_CLONE_BASE, ENCHANT_BASE

    def clone_aura(src: list[int], sid: int, name: str, rank: int) -> list[int]:
        sp = clone_u32_list(src)
        sp[F_ID] = sid
        set_name(spell_dbc, sp, name)
        for e, base in ((e, simple_value(src, e)) for e in range(3) if src[F_EFFECT0 + e] == SPELL_EFFECT_APPLY_AURA and simple_value(src, e)):
            new_mag = rank_mag(base, rank)
            sp[F_BASE0 + e] = u32_from_i32(new_mag - int(sp[F_DICE0 + e]))
        spell_dbc.records.append(sp)
        return sp

    def emit(line_id, rank, formula_id, ench_id, aura_id, label, desc, eq_class, eq_inv):
        nonlocal next_sla
        if max(formula_id, ench_id, aura_id) >= 65536:
            raise RuntimeError("id overflow")
        add_enchant(ench_dbc, ench_id, aura_id, label)
        add_formula(spell_dbc, formula_tmpl, formula_id, ench_id, f"附魔 - {label}", desc, eq_class, eq_inv)
        next_sla = add_sla(sla_dbc, sla_tmpl, next_sla, formula_id)
        rank_rows.append(
            {
                "line_id": line_id,
                "direction": DIR_MAIN,
                "rank": rank,
                "formula_spell": formula_id,
                "enchant_id": ench_id,
                "proc_spell": aura_id,
                "chance_pct": 0,
                "icd_ms": 0,
            }
        )

    for i, src in enumerate(sources):
        line_id = LINE_ID_BASE + i
        aura_id = src["aura"]
        aura = spells[aura_id]
        name = spell_label(spell_dbc, aura)
        eq_class, eq_inv = src["eq_class"], src["eq_inv"]
        base_formula, base_ench = next_formula, next_ench
        next_formula += 1
        next_ench += 1
        line_rows.append((line_id, aura_id, base_ench, eq_inv, eq_class, 0, eq_inv, 0))  # axis_kind=0
        emit(
            line_id, 0, base_formula, base_ench, aura_id, name,
            f"永久附魔装备，获得{name}（原版数值）。",
            eq_class, eq_inv,
        )
        for rank in (1, 2, 3):
            sid = next_aura
            next_aura += 1
            clone_aura(aura, sid, f"{name}（强化{ROMAN[rank]}）", rank)
            fid, eid = next_formula, next_ench
            next_formula += 1
            next_ench += 1
            emit(
                line_id, rank, fid, eid, sid, f"{name}：强化{ROMAN[rank]}",
                f"永久附魔装备，获得强化后的{name}。",
                eq_class, eq_inv,
            )
        sample = src["items"][0][0] if src["items"] else 0
        m0 = src["mags"][0][1]
        summary.append(
            f"line={line_id} aura={aura_id} {name} class={eq_class} inv={eq_inv} "
            f"mag0={m0}->{rank_mag(m0,3)} sample={sample} baseF={base_formula}"
        )

    if next_formula >= SPELL_HI or next_aura >= SPELL_HI or next_ench >= ENCH_HI:
        raise RuntimeError(f"id overflow f={next_formula} a={next_aura} e={next_ench}")
    for r in ench_dbc.records:
        if ours_ench(r[0]) and ((r[E_FLAGS] & ENCHANTMENT_CAN_SOULBOUND) or r[E_EFF0] != ITEM_ENCHANTMENT_EQUIP_SPELL):
            raise RuntimeError(f"bad enchant {r[0]}")

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

    sql = [
        "-- Batch4 A-family single-axis",
        "START TRANSACTION;",
        f"DELETE FROM `enchant_line_rank` WHERE `line_id`>={LINE_ID_BASE};",
        f"DELETE FROM `enchant_line` WHERE `line_id`>={LINE_ID_BASE};",
        "INSERT INTO `enchant_line` "
        "(`line_id`,`base_spell`,`base_enchant_id`,`slot_mask`,`eq_class`,`eq_subclass`,`eq_inv`,`axis_kind`) VALUES",
        ",\n".join(f"({a},{b},{c},{d},{e},{f},{g},{h})" for a, b, c, d, e, f, g, h in line_rows) + ";",
        "INSERT INTO `enchant_line_rank` "
        "(`line_id`,`direction`,`rank`,`formula_spell`,`enchant_id`,`proc_spell`,`chance_pct`,`icd_ms`) VALUES",
        ",\n".join(
            f"({r['line_id']},{r['direction']},{r['rank']},{r['formula_spell']},"
            f"{r['enchant_id']},{r['proc_spell']},{r['chance_pct']},{r['icd_ms']})"
            for r in rank_rows
        )
        + ";",
        "COMMIT;",
    ]
    sql_path = args.out / "batch4_single_axis.sql"
    sql_path.write_text("\n".join(sql) + "\n", encoding="utf-8")
    (args.out / "batch4_single_axis.txt").write_text("\n".join(summary) + "\n", encoding="utf-8")
    if args.apply_sql:
        mysql_exec(sql_path.read_text(encoding="utf-8"), args.password)

    subprocess.run([sys.executable, str(Path(__file__).with_name("_make_patch.py"))], check=True)
    zz = args.out / "patch-zhCN-ZZ.mpq"
    p3 = args.out / "patch-3.MPQ"
    shutil.copy2(zz, p3)
    if args.apply_dbc:
        dest = client_data_dir()
        if dest:
            try:
                shutil.copy2(p3, dest / "patch-3.MPQ")
                print(f"copied {dest / 'patch-3.MPQ'}")
            except PermissionError:
                print(f"client patch locked; left {p3}")

    print(f"lines={len(line_rows)} ranks={len(rank_rows)} ids f<{next_formula} a<{next_aura} e<{next_ench} -> {args.out}")


if __name__ == "__main__":
    main()
