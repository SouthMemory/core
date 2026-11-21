#!/usr/bin/env python3
"""Batch 3: on-equip PROC → EQUIP_SPELL enchants (shell aura), not weapon COMBAT_SPELL."""
from __future__ import annotations

import argparse
import shutil
import struct
import subprocess
import sys
from collections import Counter
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
    E_VISUAL,
    clone_u32_list,
    mysql_query,
    spell_rejected,
)

DIR_BASE, DIR_CHANCE, DIR_POWER, DIR_TIME = 0, 1, 2, 3
ROMAN = ("I", "II", "III")
SCALE = ((5, 4), (3, 2), (2, 1))
# Flat per-swing chance for 迅疾 (PPM deltas are too subtle vs base ~0.6ppm/~2%).
CHANCE_RANKS = (8.0, 12.0, 16.0)
ITEM_ENCHANTMENT_EQUIP_SPELL = 3

FORMULA_BASE = 45000
SHELL_CLONE_BASE = 48000  # shell clones for chance/power/time
PAYLOAD_CLONE_BASE = 49000
ENCHANT_BASE = 34000
SPELL_LO, SPELL_HI = 45000, 52000
ENCH_LO, ENCH_HI = 34000, 36000
LINE_ID_BASE = 200

F_EQ_CLASS, F_EQ_SUB, F_EQ_INV = 58, 59, 60
F_DIE0, F_DICE0, F_BASE0 = 64, 67, 76
F_DURATION, F_AURA0, F_AURA_PERIOD0, F_TRIGGER0 = 30, 91, 94, 109
F_PROC_CHANCE = 25
F_RANK0, F_DESC0, F_TIP0, F_NAME4 = 129, 138, 147, 124
SPELL_EFFECT_APPLY_AURA = 6
AURA_PROC_TRIGGER_SPELL = 42


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


def primary_eff(sp: list[int]) -> int | None:
    for e in range(3):
        if sp[F_EFFECT0 + e] and simple_value(sp, e):
            return e
    for e in range(3):
        if sp[F_EFFECT0 + e]:
            return e
    return None


def spell_label(spell_dbc: DBC, sp: list[int]) -> str:
    for off in (sp[F_NAME4], sp[F_NAME0]):
        name = spell_dbc.get_string(off)
        if name:
            return name
    return f"特效{sp[F_ID]}"


def dur_ms(durations: dict[int, list[int]], idx: int) -> int:
    if not idx or idx not in durations:
        return 0
    return i32_from_u32(durations[idx][1])


def pick_durations(durations: dict[int, list[int]], base_ms: int) -> list[int] | None:
    if base_ms <= 0 or base_ms > 120000:
        return None
    catalog = sorted(
        ((dur_ms(durations, did), did) for did in durations if 0 < dur_ms(durations, did) <= 120000),
        key=lambda x: x[0],
    )
    out: list[int] = []
    for t in (base_ms * 5 // 4, base_ms * 3 // 2, base_ms * 2):
        hit = next((did for ms, did in catalog if ms >= t), None)
        if hit is None or dur_ms(durations, hit) <= base_ms:
            return None
        out.append(hit)
    return out


def period_ranks(base: int) -> list[int] | None:
    if base <= 0:
        return None
    ranks = [max(500, scale(base, 5, 6)), max(500, scale(base, 2, 3)), max(500, scale(base, 1, 2))]
    if ranks[0] >= base or ranks[2] >= ranks[0]:
        return None
    return ranks


def client_data_dir() -> Path | None:
    for c in (ROOT / "wow_cn_1.12" / "Data", Path.home() / "Downloads" / "Download" / "wow_cn_1.12" / "Data"):
        if c.is_dir():
            return c
    return None


def add_enchant(ench_dbc: DBC, ench_id: int, shell_spell: int, name: str) -> None:
    ench = [0] * ench_dbc.field_count
    ench[E_ID] = ench_id
    ench[E_EFF0] = ITEM_ENCHANTMENT_EQUIP_SPELL
    ench[E_PTS0] = 0
    ench[E_ARG0] = shell_spell
    off = ench_dbc.add_string(name)
    for loc in range(8):
        ench[E_NAME0 + loc] = off
    ench[E_VISUAL] = 0
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


def fetch_sources(password: str, spells: dict[int, list[int]], spell_dbc: DBC) -> list[dict]:
    # ignore prior batch3 rows so re-runs can replace them
    covered = {
        int(r[0])
        for r in mysql_query(
            f"SELECT base_spell FROM enchant_line WHERE base_spell<>0 AND line_id<{LINE_ID_BASE}",
            password,
        )
    }
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

    proc_rows = {
        int(r[0]): {
            "SchoolMask": int(r[1]),
            "SpellFamilyName": int(r[2]),
            "SpellFamilyMask0": int(r[3]),
            "SpellFamilyMask1": int(r[4]),
            "SpellFamilyMask2": int(r[5]),
            "procFlags": int(r[6]),
            "procEx": int(r[7]),
            "ppmRate": float(r[8]),
            "CustomChance": float(r[9]),
            "Cooldown": int(r[10]),
        }
        for r in mysql_query(
            "SELECT entry, SchoolMask, SpellFamilyName, SpellFamilyMask0, SpellFamilyMask1, SpellFamilyMask2, "
            "procFlags, procEx, ppmRate, CustomChance, Cooldown FROM spell_proc_event",
            password,
        )
    }

    out: list[dict] = []
    for sid, meta in sorted(by.items()):
        if sid in covered or sid not in spells:
            continue
        if spell_rejected(spell_dbc, sid):
            continue
        sp = spells[sid]
        payload = 0
        for e in range(3):
            if (
                sp[F_EFFECT0 + e] == SPELL_EFFECT_APPLY_AURA
                and sp[F_AURA0 + e] == AURA_PROC_TRIGGER_SPELL
                and sp[F_TRIGGER0 + e]
            ):
                payload = sp[F_TRIGGER0 + e]
                break
        if not payload or payload not in spells or spell_rejected(spell_dbc, payload):
            continue
        inv_mask = 0
        for inv in meta["inv"]:
            if 0 <= inv < 32:
                inv_mask |= 1 << inv
        if not inv_mask:
            continue
        out.append(
            {
                "shell": sid,
                "payload": payload,
                "eq_class": meta["class"].most_common(1)[0][0],
                "eq_inv": inv_mask,
                "items": meta["items"],
                "proc": proc_rows.get(sid),
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
    durations = DBC(args.dbc / "SpellDuration.dbc").by_id()
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
    proc_sql_rows: list[str] = []
    summary: list[str] = []
    next_formula = FORMULA_BASE
    next_shell = SHELL_CLONE_BASE
    next_payload = PAYLOAD_CLONE_BASE
    next_ench = ENCHANT_BASE

    def clone_spell(src: list[int], sid: int, name: str) -> list[int]:
        sp = clone_u32_list(src)
        sp[F_ID] = sid
        set_name(spell_dbc, sp, name)
        spell_dbc.records.append(sp)
        return sp

    def copy_proc(src_entry: dict | None, new_id: int, ppm: float | None = None, chance: float | None = None) -> None:
        if not src_entry:
            return
        e = dict(src_entry)
        if ppm is not None:
            e["ppmRate"] = ppm
        if chance is not None:
            e["CustomChance"] = chance
        proc_sql_rows.append(
            f"({new_id},{e['SchoolMask']},{e['SpellFamilyName']},{e['SpellFamilyMask0']},"
            f"{e['SpellFamilyMask1']},{e['SpellFamilyMask2']},{e['procFlags']},{e['procEx']},"
            f"{e['ppmRate']},{e['CustomChance']},{e['Cooldown']})"
        )

    def emit(
        line_id: int,
        direction: int,
        rank: int,
        formula_id: int,
        ench_id: int,
        shell_spell: int,
        label: str,
        desc: str,
        eq_class: int,
        eq_inv: int,
    ) -> None:
        nonlocal next_sla
        if max(formula_id, ench_id, shell_spell) >= 65536:
            raise RuntimeError("id overflow")
        add_enchant(ench_dbc, ench_id, shell_spell, label)
        add_formula(spell_dbc, formula_tmpl, formula_id, ench_id, f"附魔 - {label}", desc, eq_class, eq_inv)
        next_sla = add_sla(sla_dbc, sla_tmpl, next_sla, formula_id)
        rank_rows.append(
            {
                "line_id": line_id,
                "direction": direction,
                "rank": rank,
                "formula_spell": formula_id,
                "enchant_id": ench_id,
                "proc_spell": shell_spell,
                "chance_pct": 0,
                "icd_ms": 0,
            }
        )

    for i, src in enumerate(sources):
        line_id = LINE_ID_BASE + i
        shell_id, payload_id = src["shell"], src["payload"]
        shell, payload = spells[shell_id], spells[payload_id]
        name = spell_label(spell_dbc, shell)
        eq_class, eq_inv = src["eq_class"], src["eq_inv"]
        pe = primary_eff(payload)
        raw_mag = simple_value(payload, pe) if pe is not None else 0
        if pe is not None and payload[F_EFFECT0 + pe] and raw_mag == 0:
            has_power, base_mag = True, 1
        elif pe is not None and raw_mag:
            has_power, base_mag = True, raw_mag
        else:
            has_power, base_mag = False, 0

        period = next((int(payload[F_AURA_PERIOD0 + e]) for e in range(3) if payload[F_AURA_PERIOD0 + e]), 0)
        base_ms = dur_ms(durations, payload[F_DURATION])
        p_ranks = period_ranks(period)
        d_ranks = None if p_ranks else pick_durations(durations, base_ms)
        time_mode = "period" if p_ranks else ("duration" if d_ranks else None)

        base_formula, base_ench = next_formula, next_ench
        next_formula += 1
        next_ench += 1
        line_rows.append((line_id, shell_id, base_ench, eq_inv, eq_class, 0, eq_inv, 1))
        emit(
            line_id, DIR_BASE, 0, base_formula, base_ench, shell_id, name,
            f"永久附魔装备，使其获得{name}（与原装 on-equip 相同的触发光环）。",
            eq_class, eq_inv,
        )

        base_ppm = src["proc"]["ppmRate"] if src["proc"] else 0.0
        cd = src["proc"]["Cooldown"] if src["proc"] else 3

        for r, flat in enumerate(CHANCE_RANKS):
            sid = next_shell
            next_shell += 1
            clone = clone_spell(shell, sid, f"{name}（迅疾{ROMAN[r]}）")
            # Proc code: customChance used only if set; ppmRate overrides it when nonzero.
            # Use flat CustomChance and force ppmRate=0 so 迅疾 is clearly stronger than base PPM.
            clone[F_PROC_CHANCE] = int(flat)
            if src["proc"]:
                copy_proc(src["proc"], sid, ppm=0.0, chance=flat)
            else:
                proc_sql_rows.append(f"({sid},0,0,0,0,0,0,0,0,{flat},{cd})")
            fid, eid = next_formula, next_ench
            next_formula += 1
            next_ench += 1
            emit(
                line_id, DIR_CHANCE, r + 1, fid, eid, sid,
                f"{name}：迅疾{ROMAN[r]}",
                f"永久附魔装备，获得约{int(flat)}%触发率的{name}。",
                eq_class, eq_inv,
            )

        if has_power and pe is not None:
            for r, (num, den) in enumerate(SCALE):
                pid = next_payload
                next_payload += 1
                power = clone_spell(payload, pid, f"{name}（强效载荷{ROMAN[r]}）")
                new_mag = scale(abs(base_mag), num, den)
                if base_mag < 0:
                    new_mag = -new_mag
                power[F_BASE0 + pe] = u32_from_i32(new_mag - int(power[F_DICE0 + pe]))
                sid = next_shell
                next_shell += 1
                sh = clone_spell(shell, sid, f"{name}（强效{ROMAN[r]}）")
                for e in range(3):
                    if sh[F_EFFECT0 + e] == SPELL_EFFECT_APPLY_AURA and sh[F_AURA0 + e] == AURA_PROC_TRIGGER_SPELL:
                        sh[F_TRIGGER0 + e] = pid
                        break
                copy_proc(src["proc"], sid)
                if not src["proc"]:
                    proc_sql_rows.append(f"({sid},0,0,0,0,0,0,0,0.6,0,3)")
                fid, eid = next_formula, next_ench
                next_formula += 1
                next_ench += 1
                emit(
                    line_id, DIR_POWER, r + 1, fid, eid, sid,
                    f"{name}：强效{ROMAN[r]}",
                    f"永久附魔装备，获得强化效果的{name}。",
                    eq_class, eq_inv,
                )

        if time_mode == "period" and p_ranks:
            for r, per in enumerate(p_ranks):
                pid = next_payload
                next_payload += 1
                timed = clone_spell(payload, pid, f"{name}（急促载荷{ROMAN[r]}）")
                for e in range(3):
                    if timed[F_AURA_PERIOD0 + e]:
                        timed[F_AURA_PERIOD0 + e] = per
                        break
                sid = next_shell
                next_shell += 1
                sh = clone_spell(shell, sid, f"{name}（急促{ROMAN[r]}）")
                for e in range(3):
                    if sh[F_AURA0 + e] == AURA_PROC_TRIGGER_SPELL:
                        sh[F_TRIGGER0 + e] = pid
                        break
                copy_proc(src["proc"], sid)
                fid, eid = next_formula, next_ench
                next_formula += 1
                next_ench += 1
                emit(
                    line_id, DIR_TIME, r + 1, fid, eid, sid,
                    f"{name}：急促{ROMAN[r]}",
                    f"永久附魔装备，获得急促周期的{name}。",
                    eq_class, eq_inv,
                )
        elif time_mode == "duration" and d_ranks:
            for r, did in enumerate(d_ranks):
                pid = next_payload
                next_payload += 1
                timed = clone_spell(payload, pid, f"{name}（延展载荷{ROMAN[r]}）")
                timed[F_DURATION] = did
                sid = next_shell
                next_shell += 1
                sh = clone_spell(shell, sid, f"{name}（延展{ROMAN[r]}）")
                for e in range(3):
                    if sh[F_AURA0 + e] == AURA_PROC_TRIGGER_SPELL:
                        sh[F_TRIGGER0 + e] = pid
                        break
                copy_proc(src["proc"], sid)
                fid, eid = next_formula, next_ench
                next_formula += 1
                next_ench += 1
                emit(
                    line_id, DIR_TIME, r + 1, fid, eid, sid,
                    f"{name}：延展{ROMAN[r]}",
                    f"永久附魔装备，获得更长持续的{name}。",
                    eq_class, eq_inv,
                )

        dirs = ["迅疾"]
        if has_power:
            dirs.append("强效")
        if time_mode == "period":
            dirs.append("急促")
        elif time_mode == "duration":
            dirs.append("延展")
        sample = src["items"][0][0] if src["items"] else 0
        summary.append(
            f"line={line_id} shell={shell_id} payload={payload_id} {name} "
            f"class={eq_class} inv={eq_inv} dirs={'+'.join(dirs)} sample={sample} baseF={base_formula} "
            f"base_ppm={base_ppm}"
        )

    if next_formula >= SPELL_HI or next_shell >= SPELL_HI or next_payload >= SPELL_HI or next_ench >= ENCH_HI:
        raise RuntimeError(f"id overflow f={next_formula} s={next_shell} p={next_payload} e={next_ench}")
    for r in ench_dbc.records:
        if ours_ench(r[0]) and ((r[E_FLAGS] & ENCHANTMENT_CAN_SOULBOUND) or r[E_EFF0] != ITEM_ENCHANTMENT_EQUIP_SPELL):
            raise RuntimeError(f"bad enchant {r[0]} eff={r[E_EFF0]} flags={r[E_FLAGS]}")

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

    # wipe previous batch3 clone proc rows in our id ranges
    sql = [
        "-- Batch3 on-equip PROC as EQUIP_SPELL",
        "START TRANSACTION;",
        f"DELETE FROM `spell_proc_event` WHERE `entry`>={SHELL_CLONE_BASE} AND `entry`<{SPELL_HI};",
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
    ]
    if proc_sql_rows:
        sql.append(
            "INSERT INTO `spell_proc_event` "
            "(`entry`,`SchoolMask`,`SpellFamilyName`,`SpellFamilyMask0`,`SpellFamilyMask1`,`SpellFamilyMask2`,"
            "`procFlags`,`procEx`,`ppmRate`,`CustomChance`,`Cooldown`) VALUES"
        )
        sql.append(",\n".join(proc_sql_rows) + ";")
    sql.append("COMMIT;")
    sql_path = args.out / "batch3_equip_procs.sql"
    sql_path.write_text("\n".join(sql) + "\n", encoding="utf-8")
    (args.out / "batch3_equip_procs.txt").write_text("\n".join(summary) + "\n", encoding="utf-8")
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

    # sanity: HOJ base enchant must be EQUIP_SPELL -> 15600
    ench = ench_dbc.by_id()
    for r in rank_rows:
        if r["line_id"] == next(x[0] for x in line_rows if x[1] == 15600) and r["direction"] == 0:
            e = ench[r["enchant_id"]]
            if e[E_EFF0] != ITEM_ENCHANTMENT_EQUIP_SPELL or e[E_ARG0] != 15600:
                raise RuntimeError(f"HOJ base enchant broken {e[E_EFF0]} {e[E_ARG0]}")
            print(f"HOJ base enchant {r['enchant_id']} EQUIP_SPELL -> 15600 OK")
            break

    print(
        f"lines={len(line_rows)} ranks={len(rank_rows)} proc_rows={len(proc_sql_rows)} "
        f"ids f<{next_formula} shell<{next_shell} payload<{next_payload} e<{next_ench} -> {args.out}"
    )


if __name__ == "__main__":
    main()
