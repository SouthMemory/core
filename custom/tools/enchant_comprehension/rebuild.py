#!/usr/bin/env python3
"""Pack current out/*.dbc into patch and optionally refresh reagents.

Usage:
  python rebuild.py --password deepwise
  python rebuild.py --password deepwise --reagents --apply
"""
from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

from generate import DEFAULT_DBC, OUT, ROOT


def client_data_dir() -> Path | None:
    for c in (ROOT / "wow_cn_1.12" / "Data", Path.home() / "Downloads" / "Download" / "wow_cn_1.12" / "Data"):
        if c.is_dir():
            return c
    return None


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--password", default="deepwise")
    ap.add_argument("--reagents", action="store_true", help="re-run batch5 reagent assignment")
    ap.add_argument("--apply", action="store_true", help="write server DataDir DBC + client patch-3.MPQ")
    ap.add_argument("--out", type=Path, default=OUT)
    ap.add_argument("--dbc", type=Path, default=DEFAULT_DBC)
    args = ap.parse_args()
    here = Path(__file__).resolve().parent

    if args.reagents:
        cmd = [sys.executable, str(here / "generate_batch5_reagents.py"),
               "--password", args.password, "--skip-ww"]
        if args.apply:
            cmd.append("--apply-dbc")
        subprocess.run(cmd, check=True)
        return

    for name in ("Spell.dbc", "SpellItemEnchantment.dbc", "SkillLineAbility.dbc"):
        src = args.out / name
        if not src.is_file():
            raise FileNotFoundError(src)
        if args.apply:
            (args.dbc / name).write_bytes(src.read_bytes())

    subprocess.run([sys.executable, str(here / "_make_patch.py")], check=True)
    zz = args.out / "patch-zhCN-ZZ.mpq"
    p3 = args.out / "patch-3.MPQ"
    shutil.copy2(zz, p3)
    if args.apply:
        dest = client_data_dir()
        if dest:
            try:
                shutil.copy2(p3, dest / "patch-3.MPQ")
                print(f"copied {dest / 'patch-3.MPQ'}")
            except PermissionError:
                print(f"client patch locked; left {p3}")
    print(f"ok {p3}")


if __name__ == "__main__":
    main()
