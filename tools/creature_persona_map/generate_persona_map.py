#!/usr/bin/env python3
"""Generate creature_persona_map rows (override=0) from world DB.

Mirrors C++ CreaturePersonaMapping rule priority (name > spells > equip > unit_class).
Does not UPDATE rows with override=1.

Usage:
  python generate_persona_map.py --host 127.0.0.1 --user mangos --password mangos --database mangos
  python generate_persona_map.py ... --apply   # write to DB
  python generate_persona_map.py ... --sql out.sql
"""
from __future__ import annotations

import argparse
import re
import sys
from collections import defaultdict

try:
    import MySQLdb
except ImportError:
    import pymysql as MySQLdb  # type: ignore

CLASS_WARRIOR, CLASS_PALADIN, CLASS_HUNTER = 1, 2, 3
CLASS_ROGUE, CLASS_PRIEST, CLASS_SHAMAN = 4, 5, 7
CLASS_MAGE, CLASS_WARLOCK, CLASS_DRUID = 8, 9, 11

SPEC_NONE = 0
SPEC_WARRIOR_PROT = 3
SPEC_SHAMAN_ENH = 17  # keep in sync with PersonaSpec in CreaturePersonaMapping.h
# NONE=0 ... SHAMAN_ELE=16, ENH=17, RESTO=18

TIE = [
    CLASS_WARLOCK, CLASS_SHAMAN, CLASS_PRIEST, CLASS_MAGE, CLASS_HUNTER,
    CLASS_ROGUE, CLASS_PALADIN, CLASS_WARRIOR, CLASS_DRUID,
]

NAME_RULES = [
    (CLASS_WARLOCK, 10, r"warlock|necromancer|necrolyte|shadowmage"),
    (CLASS_SHAMAN, 10, r"shaman|witch doctor|geomancer|earthcaller|windtalker|spiritchaser|oracle|seer|tidecaller|wave rider"),
    (CLASS_PRIEST, 10, r"priest|preserver|cleric|chaplain|appraiser"),
    (CLASS_MAGE, 10, r"mage|sorcerer|wizard|arcanist"),
    (CLASS_HUNTER, 10, r"hunter|cannoneer|archer|marksman|scout|outrunner|pathfinder"),
    (CLASS_ROGUE, 10, r"rogue|assassin|cutthroat|bandit"),
    (CLASS_PALADIN, 10, r"paladin|templar|crusader|knight of"),
    (CLASS_WARRIOR, 10, r"warrior|grunt|gladiator|champion|defender|guardsman|footman|executioner|battleguard|mauler|enforcer"),
    (CLASS_DRUID, 10, r"druid|keeper of the grove|dryad|cenarion"),
]

SPELL_RULES = [
    (CLASS_WARLOCK, 3, r"shadow bolt|corruption|immolate|curse of|summon succubus|summon voidwalker|death & decay|banish|drain life|bone armor|shadow barrier|shadow shock"),
    (CLASS_SHAMAN, 3, r"lightning bolt|chain lightning|healing wave|lightning shield|totem|bloodlust|frost shock|earth shock|flame shock|searing totem|healing ward|gust of wind"),
    (CLASS_PRIEST, 3, r"holy smite|lesser heal|\bheal\b|renew|power word|mind blast|shadow word|cure disease|flash heal|holy fire"),
    (CLASS_MAGE, 3, r"fireball|frostbolt|flamestrike|blizzard|arcane explosion|fire blast|cone of cold|frost armor|ice armor|polymorph|scorch"),
    (CLASS_HUNTER, 3, r"\bshoot\b|aimed shot|multi-shot|serpent sting|arcane shot|concussive shot|auto shot"),
    (CLASS_ROGUE, 3, r"backstab|sinister strike|eviscerate|garrote|cheap shot|kidney shot|dual wield"),
    (CLASS_PALADIN, 3, r"holy light|flash of light|judgement|seal of|divine shield|hammer of justice|consecration"),
    (CLASS_WARRIOR, 3, r"heroic strike|\brend\b|thunder ?clap|battle shout|demoralizing shout|shield block|shield slam|revenge|\bexecute\b|overpower|battle stance|defensive stance|berserker stance|\bcleave\b|mortal strike|bloodthirst|whirlwind|\bdisarm\b|hamstring|\bcharge\b|improved blocking"),
    (CLASS_DRUID, 3, r"\bwrath\b|moonfire|rejuvenation|regrowth|starfire|entangling roots|bear form|cat form|healing touch|mark of the wild"),
]

GOLD = {
    1397: CLASS_SHAMAN,
    3382: CLASS_HUNTER,
    7337: CLASS_WARLOCK,
    7026: CLASS_MAGE,
    2324: CLASS_SHAMAN,
}


def score_text(text: str, rules) -> dict:
    t = (text or "").lower()
    sc = defaultdict(int)
    for cls, w, pat in rules:
        if re.search(pat, t, re.I):
            sc[cls] += w
    return sc


def winner(sc: dict) -> int:
    best_c, best_s = 0, 0
    for cls in TIE:
        s = sc.get(cls, 0)
        if s > best_s:
            best_s, best_c = s, cls
    return best_c if best_s > 0 else 0


def merge(*dicts):
    out = defaultdict(int)
    for d in dicts:
        for k, v in d.items():
            out[k] += v
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=3306)
    ap.add_argument("--user", default="mangos")
    ap.add_argument("--password", default="mangos")
    ap.add_argument("--database", default="mangos")
    ap.add_argument("--patch", type=int, default=10)
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--sql", default="")
    args = ap.parse_args()

    db = MySQLdb.connect(host=args.host, port=args.port, user=args.user,
                         passwd=args.password, db=args.database, charset="utf8")
    cur = db.cursor()

    cur.execute(
        """
        SELECT entry, name, unit_class, level_min, spell_list_id, equipment_id
        FROM creature_template t1
        WHERE type=7 AND civilian=0
          AND patch=(SELECT MAX(patch) FROM creature_template t2
                     WHERE t2.entry=t1.entry AND t2.patch<=%s)
        """,
        (args.patch,),
    )
    templates = cur.fetchall()

    # spell names by list
    cur.execute("SELECT entry, spellId_1, spellId_2, spellId_3, spellId_4, spellId_5, spellId_6, spellId_7, spellId_8 FROM creature_spells")
    lists = {r[0]: [x for x in r[1:] if x] for r in cur.fetchall()}

    cur.execute("SELECT entry, name FROM spell_template WHERE build=(SELECT MAX(build) FROM spell_template s2 WHERE s2.entry=spell_template.entry)")
    spell_names = {r[0]: r[1] for r in cur.fetchall()}

    cur.execute(
        f"""
        SELECT entry, item1, item2, item3 FROM creature_equip_template
        WHERE {args.patch} BETWEEN patch_min AND patch_max
        """
    )
    # first row wins per entry
    equips = {}
    for entry, i1, i2, i3 in cur.fetchall():
        equips.setdefault(entry, (i1, i2, i3))

    cur.execute(
        """
        SELECT entry, class, subclass, inventory_type FROM item_template t1
        WHERE patch=(SELECT MAX(patch) FROM item_template t2 WHERE t2.entry=t1.entry AND t2.patch<=%s)
        """,
        (args.patch,),
    )
    items = {r[0]: r[1:] for r in cur.fetchall()}

    cur.execute("SELECT class, level, mana FROM creature_classlevelstats")
    cls_mana = {(r[0], r[1]): r[2] for r in cur.fetchall()}

    rows = []
    for entry, name, unit_class, level_min, spell_list_id, equipment_id in templates:
        name_sc = score_text(name, NAME_RULES)
        spell_sc = defaultdict(int)
        for sid in lists.get(spell_list_id or 0, []):
            spell_sc = merge(spell_sc, score_text(spell_names.get(sid, ""), SPELL_RULES))

        equip_sc = defaultdict(int)
        eq = equips.get(equipment_id or 0)
        dagger = staff = shield = ranged = dual = False
        if eq:
            slots = []
            for iid in eq:
                if not iid or iid not in items:
                    continue
                iclass, sub, inv = items[iid]
                if inv == 14:
                    shield = True
                if iclass != 2:
                    continue
                if inv in (15, 25, 26):
                    ranged = True
                if sub == 15:
                    dagger = True
                    slots.append("d")
                if sub == 10:
                    staff = True
            if slots.count("d") >= 2:
                dual = True
        if ranged:
            equip_sc[CLASS_HUNTER] += 5
        if dual:
            equip_sc[CLASS_ROGUE] += 5
        elif dagger and not staff:
            equip_sc[CLASS_ROGUE] += 2
        if shield:
            equip_sc[CLASS_WARRIOR] += 3
        if staff:
            for c in (CLASS_MAGE, CLASS_PRIEST, CLASS_SHAMAN, CLASS_WARLOCK):
                equip_sc[c] += 1

        cls = winner(name_sc) or winner(spell_sc) or winner(equip_sc)
        if not cls:
            if unit_class == CLASS_WARRIOR:
                cls = CLASS_WARRIOR
            elif unit_class == CLASS_MAGE:
                cls = CLASS_MAGE
            elif unit_class == CLASS_PALADIN:
                cls = CLASS_SHAMAN
            elif unit_class == CLASS_ROGUE:
                cls = CLASS_ROGUE

        if not cls:
            continue

        spec = SPEC_NONE
        mana = cls_mana.get((unit_class, level_min), 0)
        if cls == CLASS_SHAMAN and mana <= 0 and not staff and not ranged:
            spec = SPEC_SHAMAN_ENH
        elif cls == CLASS_WARRIOR and shield:
            spec = SPEC_WARRIOR_PROT

        rows.append((entry, cls, spec, name))

    print(f"generated {len(rows)} mappings")
    for ge, want in GOLD.items():
        hit = next((r for r in rows if r[0] == ge), None)
        got = hit[1] if hit else None
        ok = "OK" if got == want else "FAIL"
        print(f"  gold {ge}: want={want} got={got} [{ok}]")

    if args.sql:
        with open(args.sql, "w", encoding="utf-8") as f:
            f.write("-- generated by generate_persona_map.py; skips override=1 on apply\n")
            for entry, cls, spec, name in rows:
                safe = name.replace("'", "''")
                f.write(
                    f"INSERT INTO creature_persona_map (entry,persona_class,persona_spec,override,comment) "
                    f"VALUES ({entry},{cls},{spec},0,'{safe}') "
                    f"ON DUPLICATE KEY UPDATE "
                    f"persona_class=IF(override=1,persona_class,VALUES(persona_class)), "
                    f"persona_spec=IF(override=1,persona_spec,VALUES(persona_spec)), "
                    f"comment=IF(override=1,comment,VALUES(comment));\n"
                )
        print(f"wrote {args.sql}")

    if args.apply:
        for entry, cls, spec, name in rows:
            cur.execute(
                """
                INSERT INTO creature_persona_map (entry, persona_class, persona_spec, override, comment)
                VALUES (%s,%s,%s,0,%s)
                ON DUPLICATE KEY UPDATE
                  persona_class=IF(override=1, persona_class, VALUES(persona_class)),
                  persona_spec=IF(override=1, persona_spec, VALUES(persona_spec)),
                  comment=IF(override=1, comment, VALUES(comment))
                """,
                (entry, cls, spec, name[:255]),
            )
        db.commit()
        print("applied to DB")

    db.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
