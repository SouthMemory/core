#!/usr/bin/env python3
"""Batch 2: weapon chance-on-hit map → multi-dir enchant_line (迅疾+强效+时间)."""
from __future__ import annotations

import argparse
import csv
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

DIR_BASE, DIR_CHANCE, DIR_POWER, DIR_TIME = 0, 1, 2, 3
ROMAN = ("I", "II", "III")
SCALE = ((5, 4), (3, 2), (2, 1))  # 1.25 / 1.5 / 2.0
CHANCE_RANKS = (8, 12, 16)
WEAPON_INV = (1 << 13) | (1 << 17) | (1 << 21) | (1 << 22)

# keep clear of phase1 35300-35360 / 30300-30340 and base map 35000/30000
FORMULA_BASE = 36000
PROC_BASE = 40000
ENCHANT_BASE = 31000
SPELL_LO, SPELL_HI = 36000, 45000
ENCH_LO, ENCH_HI = 31000, 34000
LINE_ID_BASE = 3

F_DIE0 = 64
F_DICE0 = 67
F_BASE0 = 76
F_DURATION = 30
F_AURA_PERIOD0 = 94
F_RANK0 = 129
F_DESC0 = 138
F_TIP0 = 147
F_NAME4 = 124


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
    p = subprocess.run(
        cmd,
        input=sql,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
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
    return None


def client_data_dir() -> Path | None:
    for c in (ROOT / "wow_cn_1.12" / "Data", Path.home() / "Downloads" / "Download" / "wow_cn_1.12" / "Data"):
        if c.is_dir():
            return c
    return None


def dur_ms(durations: dict[int, list[int]], idx: int) -> int:
    if not idx or idx not in durations:
        return 0
    return i32_from_u32(durations[idx][1])


def pick_durations(durations: dict[int, list[int]], base_ms: int) -> list[int] | None:
    if base_ms <= 0:
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


def spell_label(spell_dbc: DBC, sp: list[int]) -> str:
    for off in (sp[F_NAME4], sp[F_NAME0]):
        name = spell_dbc.get_string(off)
        if name:
            return name
    return f"特效{sp[F_ID]}"


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


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dbc", type=Path, default=DEFAULT_DBC)
    ap.add_argument("--out", type=Path, default=OUT)
    ap.add_argument("--password", default="deepwise")
    ap.add_argument("--apply-dbc", action="store_true")
    ap.add_argument("--apply-sql", action="store_true")
    ap.add_argument("--limit", type=int, default=0, help="optional cap for dry runs")
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
    sla_tmpl = next(r for r in sla_dbc.records if r[S_SPELL] == TEMPLATE_SPELL and r[S_SKILL] == SKILL_ENCHANTING)

    covered = {int(r[0]) for r in mysql_query("SELECT base_spell FROM enchant_line WHERE base_spell<>0", args.password)}
    seed = args.out / "candidates.csv"
    if not seed.is_file():
        raise FileNotFoundError(f"missing seed {seed}; run generate.py first")
    sources: list[tuple[int, int, int]] = []
    with seed.open(encoding="utf-8-sig", newline="") as f:
        for row in csv.DictReader(f):
            sid, eid, fid = int(row["source_spell"]), int(row["enchant_id"]), int(row["formula_spell"])
            if sid in covered or sid not in spells or eid not in enchants or fid not in spells:
                continue
            sources.append((sid, eid, fid))
    sources.sort()
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
    next_formula = FORMULA_BASE
    next_proc = PROC_BASE
    next_ench = ENCHANT_BASE

    def clone_proc(src: list[int], sid: int, name: str) -> list[int]:
        sp = clone_u32_list(src)
        sp[F_ID] = sid
        set_name(spell_dbc, sp, name)
        spell_dbc.records.append(sp)
        return sp

    def emit_rank(
        line_id: int,
        direction: int,
        rank: int,
        formula_id: int,
        ench_id: int,
        proc_spell: int,
        chance: int,
        label: str,
        desc: str,
        visual: int,
        make_dbc: bool,
    ) -> None:
        nonlocal next_sla
        if max(formula_id, ench_id, proc_spell) >= 65536:
            raise RuntimeError("id overflow")
        if make_dbc:
            add_enchant(ench_dbc, ench_id, proc_spell, chance, label, visual)
            add_formula(spell_dbc, formula_tmpl, formula_id, ench_id, f"附魔武器 - {label}", desc)
            next_sla = add_sla(sla_dbc, sla_tmpl, next_sla, formula_id)
        rank_rows.append(
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

    for i, (src_spell, base_ench_id, base_formula) in enumerate(sources):
        line_id = LINE_ID_BASE + i
        src = spells[src_spell]
        base_ench = enchants[base_ench_id]
        visual = base_ench[E_VISUAL]
        name = spell_label(spell_dbc, src)
        pe = primary_eff(src)
        has_power = pe is not None
        period = int(src[F_AURA_PERIOD0])
        base_ms = dur_ms(durations, src[F_DURATION])
        p_ranks = period_ranks(period)
        d_ranks = pick_durations(durations, base_ms) if not p_ranks else None
        time_mode = "period" if p_ranks else ("duration" if d_ranks else None)
        axis_kind = 1

        line_rows.append((line_id, src_spell, base_ench_id, WEAPON_INV, 2, 0, WEAPON_INV, axis_kind))
        emit_rank(
            line_id, DIR_BASE, 0, base_formula, base_ench_id, src_spell, 0,
            name, f"永久附魔一件武器，使其在攻击时触发{name}。", visual, False,
        )

        def desc_chance(pct: int, proc: int) -> str:
            return f"永久附魔一件武器，使其有{pct}%的几率在攻击时触发{name}（${proc}）。"

        def desc_power(proc: int) -> str:
            return f"永久附魔一件武器，使其在攻击时触发强化{name}（${proc}）。"

        def desc_time(proc: int, kind: str) -> str:
            tag = "急促" if kind == "period" else "延展"
            return f"永久附魔一件武器，使其在攻击时触发{tag}{name}（${proc}）。"

        # 迅疾
        for r, chance in enumerate(CHANCE_RANKS):
            fid, eid = next_formula, next_ench
            next_formula += 1
            next_ench += 1
            emit_rank(
                line_id, DIR_CHANCE, r + 1, fid, eid, src_spell, chance,
                f"{name}：迅疾{ROMAN[r]}", desc_chance(chance, src_spell), visual, True,
            )

        # 强效
        if has_power:
            assert pe is not None
            base_mag = simple_value(src, pe)
            for r, (num, den) in enumerate(SCALE):
                pid = next_proc
                next_proc += 1
                power = clone_proc(src, pid, f"{name}（强效{ROMAN[r]}）")
                new_mag = scale(abs(base_mag), num, den)
                if base_mag < 0:
                    new_mag = -new_mag
                power[F_BASE0 + pe] = u32_from_i32(new_mag - int(power[F_DICE0 + pe]))
                fid, eid = next_formula, next_ench
                next_formula += 1
                next_ench += 1
                emit_rank(
                    line_id, DIR_POWER, r + 1, fid, eid, pid, 0,
                    f"{name}：强效{ROMAN[r]}", desc_power(pid), visual, True,
                )

        # 时间轴
        if time_mode == "period" and p_ranks:
            for r, per in enumerate(p_ranks):
                pid = next_proc
                next_proc += 1
                timed = clone_proc(src, pid, f"{name}（急促{ROMAN[r]}）")
                timed[F_AURA_PERIOD0] = per
                fid, eid = next_formula, next_ench
                next_formula += 1
                next_ench += 1
                emit_rank(
                    line_id, DIR_TIME, r + 1, fid, eid, pid, 0,
                    f"{name}：急促{ROMAN[r]}", desc_time(pid, "period"), visual, True,
                )
        elif time_mode == "duration" and d_ranks:
            for r, did in enumerate(d_ranks):
                pid = next_proc
                next_proc += 1
                timed = clone_proc(src, pid, f"{name}（延展{ROMAN[r]}）")
                timed[F_DURATION] = did
                fid, eid = next_formula, next_ench
                next_formula += 1
                next_ench += 1
                emit_rank(
                    line_id, DIR_TIME, r + 1, fid, eid, pid, 0,
                    f"{name}：延展{ROMAN[r]}", desc_time(pid, "duration"), visual, True,
                )

        dirs = ["迅疾"]
        if has_power:
            dirs.append("强效")
        if time_mode == "period":
            dirs.append("急促")
        elif time_mode == "duration":
            dirs.append("延展")
        summary.append(f"line={line_id} src={src_spell} {name} dirs={'+'.join(dirs)} baseF={base_formula}")

    if next_formula >= SPELL_HI or next_proc >= SPELL_HI or next_ench >= ENCH_HI:
        raise RuntimeError(f"id range overflow formula={next_formula} proc={next_proc} ench={next_ench}")

    for r in ench_dbc.records:
        if ours_ench(r[0]) and (r[E_FLAGS] & ENCHANTMENT_CAN_SOULBOUND):
            raise RuntimeError(f"soulbound enchant {r[0]}")

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

    line_ids = ",".join(str(x[0]) for x in line_rows) or "0"
    sql = [
        "-- Batch2 weapon chance-on-hit multi-dir lines",
        "START TRANSACTION;",
        f"DELETE FROM `enchant_line_rank` WHERE `line_id`>={LINE_ID_BASE};",
        f"DELETE FROM `enchant_line` WHERE `line_id`>={LINE_ID_BASE};",
        "INSERT INTO `enchant_line` "
        "(`line_id`,`base_spell`,`base_enchant_id`,`slot_mask`,`eq_class`,`eq_subclass`,`eq_inv`,`axis_kind`) VALUES",
    ]
    sql.append(
        ",\n".join(
            f"({lid},{bs},{be},{sm},{ec},{es},{ei},{ak})"
            for lid, bs, be, sm, ec, es, ei, ak in line_rows
        )
        + ";"
    )
    sql.append(
        "INSERT INTO `enchant_line_rank` "
        "(`line_id`,`direction`,`rank`,`formula_spell`,`enchant_id`,`proc_spell`,`chance_pct`,`icd_ms`) VALUES"
    )
    sql.append(
        ",\n".join(
            f"({r['line_id']},{r['direction']},{r['rank']},{r['formula_spell']},"
            f"{r['enchant_id']},{r['proc_spell']},{r['chance_pct']},{r['icd_ms']})"
            for r in rank_rows
        )
        + ";"
    )
    sql.append("COMMIT;")
    sql_path = args.out / "batch2_weapon_procs.sql"
    sql_path.write_text("\n".join(sql) + "\n", encoding="utf-8")
    (args.out / "batch2_weapon_procs.txt").write_text("\n".join(summary) + "\n", encoding="utf-8")

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

    n_time = sum(1 for s in summary if "急促" in s or "延展" in s)
    n_power = sum(1 for s in summary if "强效" in s)
    print(
        f"lines={len(line_rows)} ranks={len(rank_rows)} with_power={n_power} with_time={n_time} "
        f"ids formula<{next_formula} proc<{next_proc} ench<{next_ench} -> {args.out}"
    )


if __name__ == "__main__":
    main()
