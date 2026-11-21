DROP PROCEDURE IF EXISTS add_migration;
DELIMITER ??
CREATE PROCEDURE `add_migration`()
BEGIN
DECLARE v INT DEFAULT 1;
SET v = (SELECT COUNT(*) FROM `migrations` WHERE `id`='20261121005800');
IF v = 0 THEN
INSERT INTO `migrations` VALUES ('20261121005800');
-- Add your query below.


-- Whirlwind (1680): remove 4-target AoE cap (0 = unlimited).
INSERT INTO `spell_mod` (`Id`, `MaxAffectedTargets`, `Comment`) VALUES
(1680, 0, 'Whirlwind - unlimited AoE targets')
ON DUPLICATE KEY UPDATE
  `MaxAffectedTargets`=VALUES(`MaxAffectedTargets`),
  `Comment`=CONCAT(IFNULL(`Comment`, ''), ' | unlimited AoE targets');


-- End of migration.
END IF;
END??
DELIMITER ;
CALL add_migration();
DROP PROCEDURE IF EXISTS add_migration;
