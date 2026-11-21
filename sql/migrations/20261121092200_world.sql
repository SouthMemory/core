DROP PROCEDURE IF EXISTS add_migration;
DELIMITER ??
CREATE PROCEDURE `add_migration`()
BEGIN
DECLARE v INT DEFAULT 1;
SET v = (SELECT COUNT(*) FROM `migrations` WHERE `id`='20261121092200');
IF v = 0 THEN
INSERT INTO `migrations` VALUES ('20261121092200');
-- Add your query below.


-- Whirlwind (1680): restore DBC default MaxAffectedTargets=4 (-1 = do not override).
UPDATE `spell_mod`
SET `MaxAffectedTargets`=-1,
    `Comment`='Whirlwind - trigger weapon enchants / on-hit item effects'
WHERE `Id`=1680;


-- End of migration.
END IF;
END??
DELIMITER ;
CALL add_migration();
DROP PROCEDURE IF EXISTS add_migration;
