#!/usr/bin/env python3
"""Generate enchant-comprehension DBC rows + SQL map from chance-on-hit item spells."""
from __future__ import annotations

import argparse
import csv
import struct
import subprocess
import sys
from pathlib import Path

from dbcutil import DBC

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DBC = ROOT / "server_install" / "tools" / "extracted_data" / "dbc"
OUT = Path(__file__).resolve().parent / "out"
BLACKLIST = Path(__file__).resolve().parent / "blacklist.txt"

ENCHANT_ID_BASE = 30000
# Classic client sends learned spells as uint16 — keep IDs < 65536.
SPELL_ID_BASE = 35000
SPELL_ID_LEGACY_BASE = 90000  # old overflow range; strip on regenerate
TEMPLATE_SPELL = 7788  # Enchant Weapon - Minor Striking
REAGENT_ITEM = 16204
REAGENT_COUNT = 2
SKILL_ENCHANTING = 333
SPELL_EFFECT_ENCHANT_ITEM = 53
SPELL_EFFECT_APPLY_AURA = 6
SPELL_EFFECT_LEARN_SPELL = 36
SPELL_EFFECT_SUMMON = 28
SPELL_EFFECT_SUMMON_MOUNT = 76  # if present
ITEM_ENCHANTMENT_COMBAT_SPELL = 1
ENCHANTMENT_CAN_SOULBOUND = 0x01
# Spell.dbc field indices (uint32 view)
F_ID = 0
F_REAGENT0 = 42
F_REAGENTC0 = 50
F_EQ_CLASS = 58
F_EQ_SUB = 59
F_EQ_INV = 60
F_EFFECT0 = 61
F_MISC0 = 106
F_NAME0 = 120
F_NAME4 = 124  # zhCN in this extract
# SpellItemEnchantment
E_ID = 0
E_EFF0 = 1
E_PTS0 = 4
E_ARG0 = 10
E_NAME0 = 13
E_NAME4 = 17
E_VISUAL = 22
E_FLAGS = 23
# SkillLineAbility
S_ID = 0
S_SKILL = 1
S_SPELL = 2
S_MIN = 7
S_TRIV_HIGH = 10
S_TRIV_LOW = 11


def load_blacklist(path: Path) -> set[int]:
    out = set()
    if not path.exists():
        return out
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.split("#", 1)[0].strip()
        if line.isdigit():
            out.add(int(line))
    return out


def mysql_query(sql: str, password: str, db: str = "mangos0") -> list[tuple]:
    cmd = [
        r"C:\Program Files\MySQL\MySQL Server 5.7\bin\mysql.exe",
        "-uroot",
        f"-p{password}",
        "-N",
        "-B",
        db,
        "-e",
        sql,
    ]
    p = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if p.returncode != 0:
        raise RuntimeError(p.stderr or p.stdout)
    rows = []
    for line in p.stdout.splitlines():
        if not line.strip():
            continue
        parts = line.split("\t")
        rows.append(tuple(parts))
    return rows


def fetch_chance_on_hit(password: str) -> dict[int, dict]:
    """spellid -> {items: [(entry,name)], count}"""
    sql = """
SELECT entry, name, spellid_1, spelltrigger_1, spellid_2, spelltrigger_2,
       spellid_3, spelltrigger_3, spellid_4, spelltrigger_4, spellid_5, spelltrigger_5
FROM item_template
WHERE (spellid_1>0 AND spelltrigger_1=2)
   OR (spellid_2>0 AND spelltrigger_2=2)
   OR (spellid_3>0 AND spelltrigger_3=2)
   OR (spellid_4>0 AND spelltrigger_4=2)
   OR (spellid_5>0 AND spelltrigger_5=2)
"""
    by_spell: dict[int, dict] = {}
    for row in mysql_query(sql, password):
        entry = int(row[0])
        name = row[1]
        pairs = [
            (int(row[2]), int(row[3])),
            (int(row[4]), int(row[5])),
            (int(row[6]), int(row[7])),
            (int(row[8]), int(row[9])),
            (int(row[10]), int(row[11])),
        ]
        # first chance-on-hit only (matches server runtime rule)
        sid = 0
        for spell, trig in pairs:
            if spell > 0 and trig == 2:
                sid = spell
                break
        if not sid:
            continue
        rec = by_spell.setdefault(sid, {"items": [], "count": 0})
        rec["count"] += 1
        if len(rec["items"]) < 5:
            rec["items"].append((entry, name))
    return by_spell


def spell_rejected(spell_dbc: DBC, spell_id: int) -> str | None:
    by = spell_dbc.by_id()
    sp = by.get(spell_id)
    if not sp:
        return "missing_spell"
    # reject learn-spell / summon oriented
    for i in range(3):
        eff = sp[F_EFFECT0 + i]
        if eff in (SPELL_EFFECT_LEARN_SPELL, SPELL_EFFECT_SUMMON):
            return f"bad_effect_{eff}"
    # must have at least one effect
    if not any(sp[F_EFFECT0 + i] for i in range(3)):
        return "no_effect"
    return None


def clone_u32_list(src: list[int]) -> list[int]:
    return list(src)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dbc", type=Path, default=DEFAULT_DBC)
    ap.add_argument("--out", type=Path, default=OUT)
    ap.add_argument("--password", default="deepwise")
    ap.add_argument("--apply-dbc", action="store_true", help="Also write DBC into --dbc path")
    args = ap.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)

    blacklist = load_blacklist(BLACKLIST)
    hits = fetch_chance_on_hit(args.password)

    spell_dbc = DBC(args.dbc / "Spell.dbc")
    ench_dbc = DBC(args.dbc / "SpellItemEnchantment.dbc")
    sla_dbc = DBC(args.dbc / "SkillLineAbility.dbc")

    template = spell_dbc.by_id().get(TEMPLATE_SPELL)
    if not template:
        raise SystemExit(f"template spell {TEMPLATE_SPELL} missing")
    sla_template = None
    for r in sla_dbc.records:
        if r[S_SPELL] == TEMPLATE_SPELL and r[S_SKILL] == SKILL_ENCHANTING:
            sla_template = r
            break
    if not sla_template:
        raise SystemExit("SkillLineAbility template missing")

    candidates = []
    for sid in sorted(hits.keys()):
        if sid in blacklist:
            continue
        reason = spell_rejected(spell_dbc, sid)
        if reason:
            continue
        sp = spell_dbc.by_id()[sid]
        name = spell_dbc.get_string(sp[F_NAME4]) or spell_dbc.get_string(sp[F_NAME0]) or f"Spell {sid}"
        candidates.append((sid, name, hits[sid]))

    # assign IDs
    rows_map = []
    csv_rows = []
    next_ench = ENCHANT_ID_BASE
    next_spell = SPELL_ID_BASE
    next_sla = sla_dbc.max_id() + 1

    # remove previously generated rows if re-run on already patched DBC
    def _our_spell(sid: int) -> bool:
        return (SPELL_ID_BASE <= sid < SPELL_ID_BASE + 1000) or (
            SPELL_ID_LEGACY_BASE <= sid < SPELL_ID_LEGACY_BASE + 1000
        )

    spell_dbc.records = [r for r in spell_dbc.records if not _our_spell(r[0])]
    ench_dbc.records = [r for r in ench_dbc.records if not (ENCHANT_ID_BASE <= r[0] < ENCHANT_ID_BASE + 1000)]
    sla_dbc.records = [r for r in sla_dbc.records if not _our_spell(r[S_SPELL])]

    for sid, name, meta in candidates:
        ench_id = next_ench
        formula_id = next_spell
        next_ench += 1
        next_spell += 1

        # --- SpellItemEnchantment row ---
        ench = [0] * ench_dbc.field_count
        ench[E_ID] = ench_id
        ench[E_EFF0] = ITEM_ENCHANTMENT_COMBAT_SPELL
        ench[E_PTS0] = 0
        ench[E_ARG0] = sid
        name_off = ench_dbc.add_string(name)
        for loc in range(8):
            ench[E_NAME0 + loc] = name_off
        ench[E_VISUAL] = 0
        ench[E_FLAGS] = ENCHANTMENT_CAN_SOULBOUND
        ench_dbc.records.append(ench)

        # --- Formula Spell (clone 7788) ---
        formula = clone_u32_list(template)
        formula[F_ID] = formula_id
        # clear reagents then set phantom dust
        for i in range(8):
            formula[F_REAGENT0 + i] = 0
            formula[F_REAGENTC0 + i] = 0
        formula[F_REAGENT0] = REAGENT_ITEM
        formula[F_REAGENTC0] = REAGENT_COUNT
        formula[F_EQ_CLASS] = 2  # weapon
        formula[F_EQ_SUB] = template[F_EQ_SUB]  # keep weapon subclass mask
        formula[F_EQ_INV] = 0
        formula[F_EFFECT0] = SPELL_EFFECT_ENCHANT_ITEM
        formula[F_EFFECT0 + 1] = 0
        formula[F_EFFECT0 + 2] = 0
        formula[F_MISC0] = ench_id
        formula[F_MISC0 + 1] = 0
        formula[F_MISC0 + 2] = 0
        fname = f"附魔武器 - {name}"
        foff = spell_dbc.add_string(fname)
        for loc in range(8):
            formula[F_NAME0 + loc] = foff
        spell_dbc.records.append(formula)

        # --- SkillLineAbility ---
        sla = clone_u32_list(sla_template)
        sla[S_ID] = next_sla
        next_sla += 1
        sla[S_SKILL] = SKILL_ENCHANTING
        sla[S_SPELL] = formula_id
        sla[S_MIN] = 1
        sla[S_TRIV_HIGH] = 1
        sla[S_TRIV_LOW] = 1
        sla_dbc.records.append(sla)

        rows_map.append((sid, ench_id, formula_id, name))
        sample = "; ".join(f"{e}:{n}" for e, n in meta["items"])
        csv_rows.append(
            {
                "source_spell": sid,
                "spell_name": name,
                "enchant_id": ench_id,
                "formula_spell": formula_id,
                "item_count": meta["count"],
                "sample_items": sample,
            }
        )

    # sort DBC by id for cleanliness
    spell_dbc.records.sort(key=lambda r: r[0])
    ench_dbc.records.sort(key=lambda r: r[0])
    sla_dbc.records.sort(key=lambda r: r[0])

    spell_dbc.save(args.out / "Spell.dbc")
    ench_dbc.save(args.out / "SpellItemEnchantment.dbc")
    sla_dbc.save(args.out / "SkillLineAbility.dbc")

    with (args.out / "candidates.csv").open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(
            f,
            fieldnames=[
                "source_spell",
                "spell_name",
                "enchant_id",
                "formula_spell",
                "item_count",
                "sample_items",
            ],
        )
        w.writeheader()
        w.writerows(csv_rows)

    readme = args.out / "CLIENT_PATCH.txt"
    readme.write_text(
        "Formula spell IDs start at 35000 (must be <65536; classic learn packet is uint16).\n"
        "Prefer patch-zhCN-ZZ.mpq so it loads AFTER patch-zhCN-Z.mpq.\n"
        "Copy Spell.dbc / SpellItemEnchantment.dbc / SkillLineAbility.dbc into server DataDir/dbc.\n"
        f"Generated {len(rows_map)} comprehension recipes.\n",
        encoding="utf-8",
    )

    if args.apply_dbc:
        for name in ("Spell.dbc", "SpellItemEnchantment.dbc", "SkillLineAbility.dbc"):
            (args.dbc / name).write_bytes((args.out / name).read_bytes())

    print(f"Generated {len(rows_map)} recipes -> {args.out}")
    if args.apply_dbc:
        print(f"Applied DBC into {args.dbc}")


if __name__ == "__main__":
    main()
