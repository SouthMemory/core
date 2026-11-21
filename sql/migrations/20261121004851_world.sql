DROP PROCEDURE IF EXISTS add_migration;
DELIMITER ??
CREATE PROCEDURE `add_migration`()
BEGIN
DECLARE v INT DEFAULT 1;
SET v = (SELECT COUNT(*) FROM `migrations` WHERE `id`='20261121004851');
IF v = 0 THEN
INSERT INTO `migrations` VALUES ('20261121004851');
-- Add your query below.


-- Whirlwind (1680): self-range AoE with EquippedItemClass=weapon, but rangeIndex!=combat.
-- Without SPELL_CUSTOM_TRIGGER_WEAPON_PROCS it never calls CastItemCombatSpell.
INSERT INTO `spell_mod` (`Id`, `Custom`, `Comment`) VALUES
(1680, 8192, 'Whirlwind - trigger weapon enchants / on-hit item effects')
ON DUPLICATE KEY UPDATE `Custom`=VALUES(`Custom`), `Comment`=VALUES(`Comment`);


-- End of migration.
END IF;
END??
DELIMITER ;
CALL add_migration();
DROP PROCEDURE IF EXISTS add_migration;
