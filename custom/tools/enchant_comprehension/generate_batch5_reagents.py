#!/usr/bin/env python3
"""Batch 5: assign DE+craft reagents to all comprehension formulas; gap-fill Whirlwind 9632."""
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
    F_EFFECT0,
    F_ID,
    F_MISC0,
    F_NAME0,
    F_REAGENT0,
    F_REAGENTC0,
    OUT,
    ROOT,
    TEMPLATE_SPELL,
    ITEM_ENCHANTMENT_COMBAT_SPELL,
    SPELL_EFFECT_ENCHANT_ITEM,
    SKILL_ENCHANTING,
    S_ID,
    S_MIN,
    S_SKILL,
    S_SPELL,
    S_TRIV_HIGH,
    S_TRIV_LOW,
    E_ARG0,
    E_EFF0,
    E_FLAGS,
    E_ID,
    E_NAME0,
    E_PTS0,
    clone_u32_list,
    mysql_query,
)
from generate_batch2_weapon_procs import (
    CHANCE_RANKS,
    DIR_BASE,
    DIR_CHANCE,
    DIR_POWER,
    DIR_TIME,
    ROMAN,
    SCALE,
    WEAPON_INV,
    add_enchant as b2_add_enchant,
    add_formula as b2_add_formula,
    add_sla as b2_add_sla,
    dur_ms,
    period_ranks,
    pick_durations,
    primary_eff,
    scale,
    simple_value,
    spell_label,
    u32_from_i32,
    i32_from_u32,
)

# Batch5 dedicated IDs for whirlwind gap (avoid prior ranges)
WW_LINE = 179
WW_FORMULA_BASE = 55400
WW_PROC_BASE = 55500
WW_ENCHANT_BASE = 38000
WW_SPELL_LO, WW_SPELL_HI = 55400, 55600
WW_ENCH_LO, WW_ENCH_HI = 38000, 38100
WW_SOURCE = 9632

F_EQ_CLASS, F_EQ_SUB, F_EQ_INV = 58, 59, 60
F_DICE0, F_BASE0 = 67, 76
F_DURATION, F_AURA_PERIOD0 = 30, 94
F_RANK0, F_DESC0, F_TIP0, F_NAME4 = 129, 138, 147, 124
F_ITEMTYPE0 = 103
SPELL_EFFECT_CREATE_ITEM = 24
SPELL_EFFECT_APPLY_AURA = 6

# Prefer classic enchanting trade goods when present in DE loot
ENCHANT_MATS = {
    10940, 11083, 11137, 11176, 16204,  # dust
    10938, 10939, 11134, 11135, 11174, 11175, 16202, 16203,  # essence
    10978, 11084, 11138, 11139, 11177, 11178, 14343, 14344,  # shards
    20725,  # nexus
}

# Upgrade cost vs rank0 reagent counts (never cheaper than base).
RANK_MULT = {0: 1.0, 1: 1.25, 2: 1.5, 3: 2.0}
FALLBACK_DE = 16204  # Illusion Dust
FALLBACK_CRAFT = 11137  # Vision Dust


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


def client_data_dir() -> Path | None:
    for c in (ROOT / "wow_cn_1.12" / "Data", Path.home() / "Downloads" / "Download" / "wow_cn_1.12" / "Data"):
        if c.is_dir():
            return c
    return None


def set_reagents(sp: list[int], mats: list[tuple[int, int]]) -> None:
    for i in range(8):
        sp[F_REAGENT0 + i] = 0
        sp[F_REAGENTC0 + i] = 0
    for i, (item, cnt) in enumerate(mats[:8]):
        sp[F_REAGENT0 + i] = item
        sp[F_REAGENTC0 + i] = cnt


def load_samples(password: str) -> dict[int, dict]:
    """base_spell -> {entry, ilvl, inv, class, deid} highest ilvl sample."""
    sql = """
SELECT entry, name, class, InventoryType, ItemLevel, DisenchantID,
 spellid_1, spelltrigger_1, spellid_2, spelltrigger_2,
 spellid_3, spelltrigger_3, spellid_4, spelltrigger_4,
 spellid_5, spelltrigger_5
FROM item_template
WHERE DisenchantID<>0 OR
 (spellid_1>0) OR (spellid_2>0) OR (spellid_3>0) OR (spellid_4>0) OR (spellid_5>0)
"""
    best: dict[int, dict] = {}
    for row in mysql_query(sql, password):
        entry = int(row[0])
        iclass, inv, ilvl, deid = int(row[2]), int(row[3]), int(row[4]), int(row[5])
        pairs = [
            (int(row[6]), int(row[7])),
            (int(row[8]), int(row[9])),
            (int(row[10]), int(row[11])),
            (int(row[12]), int(row[13])),
            (int(row[14]), int(row[15])),
        ]
        for sid, trig in pairs:
            if not sid or trig not in (1, 2):
                continue
            cur = best.get(sid)
            if not cur or ilvl > cur["ilvl"] or (ilvl == cur["ilvl"] and entry > cur["entry"]):
                best[sid] = {"entry": entry, "ilvl": ilvl, "inv": inv, "class": iclass, "deid": deid}
    return best


def load_de_loot(password: str) -> dict[int, list[tuple[int, float]]]:
    out: dict[int, list[tuple[int, float]]] = defaultdict(list)
    for row in mysql_query(
        "SELECT entry, item, ChanceOrQuestChance, mincountOrRef FROM disenchant_loot_template WHERE mincountOrRef>0",
        password,
    ):
        out[int(row[0])].append((int(row[1]), abs(float(row[2]))))
    return out


def load_craft_index(spell_dbc: DBC, password: str) -> dict[int, list[tuple[int, int, int, int]]]:
    """inv -> list of (ilvl, crafted_item, reagent_item, reagent_count) preferring trade goods."""
    items = {
        int(r[0]): (int(r[1]), int(r[2]), int(r[3]), int(r[4]))
        for r in mysql_query("SELECT entry, class, InventoryType, ItemLevel, Quality FROM item_template", password)
    }
    trade = {
        int(r[0])
        for r in mysql_query(
            "SELECT entry FROM item_template WHERE class=7 AND stackable>1 AND Quality BETWEEN 1 AND 3",
            password,
        )
    }
    by_inv: dict[int, list[tuple[int, int, int, int]]] = defaultdict(list)
    for r in spell_dbc.records:
        for e in range(3):
            if r[F_EFFECT0 + e] != SPELL_EFFECT_CREATE_ITEM:
                continue
            crafted = r[F_ITEMTYPE0 + e] or r[F_MISC0 + e]
            if not crafted or crafted not in items:
                break
            mats = [(r[F_REAGENT0 + i], r[F_REAGENTC0 + i]) for i in range(8) if r[F_REAGENT0 + i]]
            pick = next((m for m in mats if m[0] in trade), None)
            if not pick:
                break
            _iclass, inv, ilvl, _q = items[crafted]
            by_inv[inv].append((ilvl, crafted, pick[0], max(1, pick[1])))
            break
    for inv in by_inv:
        by_inv[inv].sort(key=lambda x: x[0])
    return by_inv


def pick_de_mat(deid: int, de_loot: dict[int, list[tuple[int, float]]]) -> int:
    rows = de_loot.get(deid) or []
    if not rows:
        return FALLBACK_DE
    preferred = [it for it, _ in rows if it in ENCHANT_MATS]
    if preferred:
        # highest chance among preferred
        scored = [(ch, it) for it, ch in rows if it in ENCHANT_MATS]
        scored.sort(reverse=True)
        return scored[0][1]
    rows = sorted(rows, key=lambda x: -x[1])
    return rows[0][0]


def pick_craft_mat(ilvl: int, inv: int, craft_by_inv: dict[int, list[tuple[int, int, int, int]]]) -> int:
    pool = craft_by_inv.get(inv) or []
    if not pool:
        # any inv near ilvl
        pool = [x for xs in craft_by_inv.values() for x in xs]
    if not pool:
        return FALLBACK_CRAFT
    near = [x for x in pool if abs(x[0] - ilvl) <= 20]
    use = near or pool
    # closest ilvl
    use.sort(key=lambda x: (abs(x[0] - ilvl), -x[0]))
    return use[0][2]


def read_reagents(sp: list[int]) -> list[tuple[int, int]]:
    return [(sp[F_REAGENT0 + i], sp[F_REAGENTC0 + i]) for i in range(8) if sp[F_REAGENT0 + i]]


def scale_counts(base_counts: list[int], rank: int) -> list[int]:
    """Upgrade ranks: >= base, strictly increasing each rank (fixes ceil(1*x)=2 collapse)."""
    import math

    if rank <= 0:
        return [max(1, c) for c in base_counts]
    prev = [max(1, c) for c in base_counts]
    out = prev
    for r in (1, 2, 3):
        mult = RANK_MULT.get(r, 2.0)
        nxt = []
        for i, c in enumerate(base_counts):
            n = max(c, int(math.ceil(c * mult)))
            n = max(n, prev[i] + 1)  # at least +1 per rank
            nxt.append(n)
        prev = nxt
        if r == rank:
            out = nxt
    return out


def assign_reagents(password: str, spell_dbc: DBC) -> tuple[int, Path]:
    lines = mysql_query(
        "SELECT line_id, base_spell FROM enchant_line ORDER BY line_id",
        password,
    )
    ranks = mysql_query(
        "SELECT line_id, direction, rank, formula_spell FROM enchant_line_rank ORDER BY line_id, direction, rank",
        password,
    )
    samples = load_samples(password)
    de_loot = load_de_loot(password)
    craft_by_inv = load_craft_index(spell_dbc, password)
    spells = spell_dbc.by_id()

    ranks_by_line: dict[int, list[tuple[int, int, int]]] = defaultdict(list)
    for lid, _d, rank, fid in ranks:
        ranks_by_line[int(lid)].append((int(rank), int(fid), int(_d)))

    # line_id -> list[(item, base_count)] from rank0 (after ensuring rank0 has mats)
    line_base_reag: dict[int, list[tuple[int, int]]] = {}
    report = []
    for lid, base in lines:
        lid, base = int(lid), int(base)
        rank0 = next((fid for rank, fid, _d in ranks_by_line.get(lid, []) if rank == 0), 0)
        base_reag = read_reagents(spells[rank0]) if rank0 and rank0 in spells else []

        # Generated rank0 with no/bad reagents: seed DE+craft at (1,1)
        if rank0 and rank0 >= 35000 and len(base_reag) < 2:
            sample = samples.get(base)
            if sample and sample["deid"]:
                de = pick_de_mat(sample["deid"], de_loot)
                craft = pick_craft_mat(sample["ilvl"], sample["inv"], craft_by_inv)
                sample_item, ilvl = sample["entry"], sample["ilvl"]
            else:
                de, craft, sample_item, ilvl = FALLBACK_DE, FALLBACK_CRAFT, 0, 0
            if de == craft:
                craft = FALLBACK_CRAFT if de != FALLBACK_CRAFT else 11176
            set_reagents(spells[rank0], [(de, 1), (craft, 1)])
            base_reag = [(de, 1), (craft, 1)]
            report.append(
                f"line={lid} base={base} seed_rank0={rank0} sample={sample_item} ilvl={ilvl} "
                f"mats={de}x1+{craft}x1"
            )
        elif len(base_reag) >= 1:
            report.append(
                f"line={lid} base={base} inherit_rank0={rank0} "
                + "+".join(f"{i}x{c}" for i, c in base_reag)
            )
        else:
            # vanilla rank0 missing reagents — fall back kinds only
            de, craft = FALLBACK_DE, FALLBACK_CRAFT
            base_reag = [(de, 1), (craft, 1)]
            report.append(f"line={lid} base={base} fallback mats={de}x1+{craft}x1")

        line_base_reag[lid] = base_reag

    updated = 0
    for lid, _d, rank, fid in ranks:
        lid, rank, fid = int(lid), int(rank), int(fid)
        if fid < 35000:
            continue
        sp = spells.get(fid)
        if not sp:
            continue
        base_reag = line_base_reag[lid]
        kinds = [item for item, _c in base_reag]
        base_counts = [cnt for _i, cnt in base_reag]
        # If this formula IS the generated rank0, keep the seeded (1,1) / existing
        if rank == 0:
            set_reagents(sp, base_reag)
        else:
            counts = scale_counts(base_counts, rank)
            # pad/truncate to kinds length
            while len(counts) < len(kinds):
                counts.append(counts[-1] if counts else 1)
            set_reagents(sp, list(zip(kinds, counts)))
        updated += 1

    path = OUT / "batch5_reagents.txt"
    path.write_text("\n".join(report) + "\n", encoding="utf-8")
    return updated, path


def gap_whirlwind(password: str, spell_dbc: DBC, ench_dbc: DBC, sla_dbc: DBC) -> list[str]:
    """Add multi-dir line for 9632 if missing."""
    exists = mysql_query(f"SELECT line_id FROM enchant_line WHERE base_spell={WW_SOURCE}", password)
    if exists:
        return [f"whirlwind already line {exists[0][0]}"]

    spells = spell_dbc.by_id()
    if WW_SOURCE not in spells:
        return ["whirlwind source spell missing"]
    # strip prior WW gap ids
    spell_dbc.records = [r for r in spell_dbc.records if not (WW_SPELL_LO <= r[0] < WW_SPELL_HI)]
    ench_dbc.records = [r for r in ench_dbc.records if not (WW_ENCH_LO <= r[0] < WW_ENCH_HI)]
    sla_dbc.records = [r for r in sla_dbc.records if not (WW_SPELL_LO <= r[S_SPELL] < WW_SPELL_HI)]
    spells = spell_dbc.by_id()
    durations = DBC(DEFAULT_DBC / "SpellDuration.dbc").by_id()
    src = spells[WW_SOURCE]
    # triggered damage spell if any
    payload = src[109] if src[109] else WW_SOURCE
    if payload not in spells:
        payload = WW_SOURCE
    payload_sp = spells[payload]
    formula_tmpl = spells[TEMPLATE_SPELL]
    sla_tmpl = next(r for r in sla_dbc.records if r[S_SPELL] == TEMPLATE_SPELL and r[S_SKILL] == SKILL_ENCHANTING)
    next_sla = sla_dbc.max_id() + 1
    name = spell_label(spell_dbc, src)
    rows = []
    next_f, next_p, next_e = WW_FORMULA_BASE, WW_PROC_BASE, WW_ENCHANT_BASE

    def clone(src_sp, sid, nm):
        sp = clone_u32_list(src_sp)
        sp[F_ID] = sid
        off = spell_dbc.add_string(nm)
        for loc in range(8):
            sp[F_NAME0 + loc] = off
        for loc in range(8):
            sp[F_RANK0 + loc] = 0
        spell_dbc.records.append(sp)
        return sp

    def emit(direction, rank, fid, eid, proc, chance, label, desc):
        nonlocal next_sla
        b2_add_enchant(ench_dbc, eid, proc, chance, label, 0)
        b2_add_formula(spell_dbc, formula_tmpl, fid, eid, f"附魔武器 - {label}", desc)
        next_sla = b2_add_sla(sla_dbc, sla_tmpl, next_sla, fid)
        rows.append((direction, rank, fid, eid, proc, chance))

    # rank0 base: new formula pointing to combat enchant of source
    base_f, base_e = next_f, next_e
    next_f += 1
    next_e += 1
    emit(DIR_BASE, 0, base_f, base_e, WW_SOURCE, 0, name, f"永久附魔一件武器，使其在攻击时触发{name}。")

    for r, chance in enumerate(CHANCE_RANKS):
        fid, eid = next_f, next_e
        next_f += 1
        next_e += 1
        emit(DIR_CHANCE, r + 1, fid, eid, WW_SOURCE, chance, f"{name}：迅疾{ROMAN[r]}",
             f"永久附魔一件武器，使其有{chance}%的几率触发{name}。")

    pe = primary_eff(payload_sp)
    if pe is not None:
        base_mag = simple_value(payload_sp, pe) or 1
        for r, (num, den) in enumerate(SCALE):
            pid = next_p
            next_p += 1
            power = clone(payload_sp, pid, f"{name}（强效{ROMAN[r]}）")
            new_mag = scale(abs(base_mag), num, den)
            if base_mag < 0:
                new_mag = -new_mag
            power[F_BASE0 + pe] = u32_from_i32(new_mag - int(power[F_DICE0 + pe]))
            # if payload is shell with aura period, also clone source for combat
            combat = pid if payload == WW_SOURCE or payload_sp[F_EFFECT0] != SPELL_EFFECT_APPLY_AURA else pid
            # Whirlwind: source 9632 is periodic aura triggering 9633 — combat enchant should cast 9632 or use weapon percent
            # Keep combat arg as source clones for power on period aura
            if WW_SOURCE != payload:
                sh = clone(src, next_p, f"{name}（强效壳{ROMAN[r]}）")
                next_p += 1
                # retarget trigger if any
                if sh[109]:
                    sh[109] = pid
                combat = sh[F_ID]
            fid, eid = next_f, next_e
            next_f += 1
            next_e += 1
            emit(DIR_POWER, r + 1, fid, eid, combat, 0, f"{name}：强效{ROMAN[r]}",
                 f"永久附魔一件武器，触发强化{name}。")

    period = int(src[F_AURA_PERIOD0]) or int(payload_sp[F_AURA_PERIOD0])
    p_ranks = period_ranks(period)
    if p_ranks:
        for r, per in enumerate(p_ranks):
            sid = next_p
            next_p += 1
            timed = clone(src, sid, f"{name}（急促{ROMAN[r]}）")
            timed[F_AURA_PERIOD0] = per
            fid, eid = next_f, next_e
            next_f += 1
            next_e += 1
            emit(DIR_TIME, r + 1, fid, eid, sid, 0, f"{name}：急促{ROMAN[r]}",
                 f"永久附魔一件武器，触发急促{name}。")
    else:
        d_ranks = pick_durations(durations, dur_ms(durations, src[F_DURATION]))
        if d_ranks:
            for r, did in enumerate(d_ranks):
                sid = next_p
                next_p += 1
                timed = clone(src, sid, f"{name}（延展{ROMAN[r]}）")
                timed[F_DURATION] = did
                fid, eid = next_f, next_e
                next_f += 1
                next_e += 1
                emit(DIR_TIME, r + 1, fid, eid, sid, 0, f"{name}：延展{ROMAN[r]}",
                     f"永久附魔一件武器，触发延展{name}。")

    sql = [
        "START TRANSACTION;",
        f"DELETE FROM enchant_line_rank WHERE line_id={WW_LINE};",
        f"DELETE FROM enchant_line WHERE line_id={WW_LINE};",
        "INSERT INTO enchant_line (line_id,base_spell,base_enchant_id,slot_mask,eq_class,eq_subclass,eq_inv,axis_kind) VALUES "
        f"({WW_LINE},{WW_SOURCE},{base_e},{WEAPON_INV},2,0,{WEAPON_INV},1);",
        "INSERT INTO enchant_line_rank (line_id,direction,rank,formula_spell,enchant_id,proc_spell,chance_pct,icd_ms) VALUES "
        + ",\n".join(f"({WW_LINE},{d},{r},{f},{e},{p},{c},0)" for d, r, f, e, p, c in rows)
        + ";",
        "COMMIT;",
    ]
    mysql_exec("\n".join(sql), password)
    return [f"whirlwind line={WW_LINE} baseF={base_f} ranks={len(rows)}"]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dbc", type=Path, default=DEFAULT_DBC)
    ap.add_argument("--out", type=Path, default=OUT)
    ap.add_argument("--password", default="deepwise")
    ap.add_argument("--apply-dbc", action="store_true")
    ap.add_argument("--skip-ww", action="store_true")
    args = ap.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)

    spell_dbc = DBC(args.dbc / "Spell.dbc")
    ench_dbc = DBC(args.dbc / "SpellItemEnchantment.dbc")
    sla_dbc = DBC(args.dbc / "SkillLineAbility.dbc")

    notes = []
    if not args.skip_ww:
        notes.extend(gap_whirlwind(args.password, spell_dbc, ench_dbc, sla_dbc))

    updated, report = assign_reagents(args.password, spell_dbc)
    notes.append(f"reagents_updated={updated} report={report}")

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

    # spot-check HOJ / Blackhand reagents
    spells = spell_dbc.by_id()
    for sid in (45089, 52048, 35320):
        sp = spells.get(sid)
        if not sp:
            continue
        mats = [(sp[F_REAGENT0 + i], sp[F_REAGENTC0 + i]) for i in range(8) if sp[F_REAGENT0 + i]]
        print(f"formula {sid} reagents {mats}")
    print("; ".join(notes))


if __name__ == "__main__":
    main()
