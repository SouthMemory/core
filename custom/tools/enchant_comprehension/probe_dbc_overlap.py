#!/usr/bin/env python3
"""Probe Zero out/ DBC vs vmangos DataDir + spell_template ID overlap."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from dbcutil import DBC

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(r"C:\Users\Administrator\Documents\mangos\tools\enchant_comprehension\out")
VM_DBC = ROOT / "data" / "5875" / "dbc"
MYSQL = r"C:\Program Files\MySQL\MySQL Server 5.7\bin\mysql.exe"
LO, HI = 35000, 56000


def mysql_ids(sql: str) -> set[int]:
    p = subprocess.run(
        [MYSQL, "-umangos", "-pmangos", "-N", "-B", "-e", sql],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
    )
    if p.returncode != 0:
        raise SystemExit(p.stderr or p.stdout)
    return {int(x) for x in p.stdout.split() if x.strip().isdigit()}


def main() -> int:
    spell_out, spell_vm = DBC(OUT / "Spell.dbc"), DBC(VM_DBC / "Spell.dbc")
    ench_out, ench_vm = DBC(OUT / "SpellItemEnchantment.dbc"), DBC(VM_DBC / "SpellItemEnchantment.dbc")
    sla_out, sla_vm = DBC(OUT / "SkillLineAbility.dbc"), DBC(VM_DBC / "SkillLineAbility.dbc")

    so, sv = spell_out.by_id(), spell_vm.by_id()
    only_out = set(so) - set(sv)
    custom = {i for i in only_out if LO <= i <= HI}
    db_hits = mysql_ids(
        f"SELECT DISTINCT entry FROM mangos.spell_template WHERE entry BETWEEN {LO} AND {HI}"
    )
    overlap = sorted(custom & db_hits)

    eo, ev = ench_out.by_id(), ench_vm.by_id()
    ench_new = set(eo) - set(ev)
    sla_o, sla_v = sla_out.by_id(), sla_vm.by_id()
    sla_new = set(sla_o) - set(sla_v)

    print(f"Spell only_out={len(only_out)} custom[{LO}-{HI}]={len(custom)}")
    print(f"spell_template overlap in custom range: {len(overlap)}")
    print(f"SpellItemEnchantment max out={max(eo)} vm={max(ev)} new={len(ench_new)} ge30000={sum(1 for i in ench_new if i>=30000)}")
    print(f"SkillLineAbility max out={max(sla_o)} vm={max(sla_v)} new_ids={len(sla_new)}")
    if overlap:
        print("FAIL overlap sample:", overlap[:20])
        return 1
    print("OK: no spell_template overlap in custom range")
    return 0


if __name__ == "__main__":
    sys.exit(main())
