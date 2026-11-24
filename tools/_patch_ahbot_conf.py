from pathlib import Path

NEW_COMMENT = """###################################################################################################################
# AUCTION HOUSE BOT
#
#    AHBot.Enable
#        Enable AH bot.
#        Scans item_template into quality x class pools (no grey; NO_BIND + BoE only) and refills by quotas.
#        Default: 0 - off
#                 1 - on
#
#    AHBot.ah.fid
#        Faction template ID for which auction house to fill.
#        Default: 120 - Neutral (Booty Bay, Gadgetzan and Everlook)
#                  55 - Alliance (Ironforge, Stormwind and Teldrassil)
#                  29 - Horde (Orgrimmar, Thunderbluff and Undercity)
#
#    AHBot.itemcount
#        Max listings in that auction house (includes player listings).
#        Default: 10000
#
#    AHBot.Amount.* / AHBot.Priority.* / AHBot.PriceRatio.*
#        Per-quality listing targets (scaled to itemcount), item-class weights, sell price multipliers (%).
#
###################################################################################################################
"""

def replace_block(path: Path, enable: int, fid: int, itemcount: int):
    text = path.read_text(encoding="utf-8", errors="ignore")
    start = text.find("###################################################################################################################\n# AUCTION HOUSE BOT")
    if start < 0:
        start = text.find("# AUCTION HOUSE BOT")
        if start < 0:
            raise SystemExit(f"AHBot block not found in {path}")
        # rewind to previous separator if present
        sep = text.rfind("###################################################################################################################", 0, start)
        if sep >= 0:
            start = sep
    end = text.find("###################################################################################################################\n# PLAYER BOTS", start)
    if end < 0:
        end = text.find("# PLAYER BOTS", start)
        if end < 0:
            raise SystemExit(f"PLAYER BOTS marker not found in {path}")
    body = NEW_COMMENT + f"""
AHBot.Enable = {enable}
AHBot.ah.fid = {fid}
AHBot.itemcount = {itemcount}

AHBot.Amount.White = 2500
AHBot.Amount.Green = 3500
AHBot.Amount.Blue = 2500
AHBot.Amount.Purple = 1200
AHBot.Amount.Orange = 300
AHBot.Amount.Yellow = 0

AHBot.Priority.TradeGoods = 25
AHBot.Priority.Armor = 20
AHBot.Priority.Weapon = 15
AHBot.Priority.Consumable = 15
AHBot.Priority.Recipe = 10
AHBot.Priority.Reagent = 5
AHBot.Priority.Projectile = 5
AHBot.Priority.Container = 3
AHBot.Priority.Quiver = 2

AHBot.PriceRatio.White = 100
AHBot.PriceRatio.Green = 150
AHBot.PriceRatio.Blue = 200
AHBot.PriceRatio.Purple = 350
AHBot.PriceRatio.Orange = 500
AHBot.PriceRatio.Yellow = 600

"""
    path.write_text(text[:start] + body + text[end:], encoding="utf-8")
    print("patched", path)

if __name__ == "__main__":
    replace_block(Path(r"C:\Users\Administrator\Documents\vmangos\install\mangosd.conf"), 1, 55, 10000)
    replace_block(Path(r"C:\Users\Administrator\Documents\vmangos\core\src\mangosd\mangosd.conf.dist.in"), 0, 120, 10000)
    dist = Path(r"C:\Users\Administrator\Documents\vmangos\install\mangosd.conf.dist")
    if dist.exists():
        replace_block(dist, 0, 120, 10000)
