import pympq
from pathlib import Path

src = Path(__file__).resolve().parent / "out"
out = src / "patch-zhCN-ZZ.mpq"
if out.exists():
    out.unlink()
mpq = pympq.create_archive(str(out), [pympq.MPQ_CREATE_ARCHIVE_V1, pympq.MPQ_CREATE_LISTFILE], 16)
for name in ("Spell.dbc", "SpellItemEnchantment.dbc", "SkillLineAbility.dbc"):
    mpq.add_file(str(src / name), "DBFilesClient\\" + name, [pympq.MPQ_FILE_REPLACEEXISTING])
mpq.compact()
mpq.close()
print(out, out.stat().st_size)
