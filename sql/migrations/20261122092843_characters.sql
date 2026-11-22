DROP PROCEDURE IF EXISTS add_migration;
DELIMITER ??
CREATE PROCEDURE `add_migration`()
BEGIN
DECLARE v INT DEFAULT 1;
SET v = (SELECT COUNT(*) FROM `migrations` WHERE `id`='20261122092843');
IF v = 0 THEN
INSERT INTO `migrations` VALUES ('20261122092843');
-- Add your query below.


CREATE TABLE IF NOT EXISTS `character_partybot_hire` (
  `id` INT(10) UNSIGNED NOT NULL AUTO_INCREMENT,
  `owner_guid` INT(10) UNSIGNED NOT NULL,
  `role` TINYINT(3) UNSIGNED NOT NULL DEFAULT 0,
  `class` TINYINT(3) UNSIGNED NOT NULL DEFAULT 0,
  `race` TINYINT(3) UNSIGNED NOT NULL DEFAULT 0,
  `expire_time` INT(10) UNSIGNED NOT NULL DEFAULT 0,
  `status` TINYINT(3) UNSIGNED NOT NULL DEFAULT 0 COMMENT '0=active 1=voided',
  `bot_guid` INT(10) UNSIGNED NOT NULL DEFAULT 0,
  PRIMARY KEY (`id`),
  KEY `idx_owner_status` (`owner_guid`,`status`),
  KEY `idx_expire` (`expire_time`)
) ENGINE=MyISAM DEFAULT CHARSET=utf8;


-- End of migration.
END IF;
END??
DELIMITER ;
CALL add_migration();
DROP PROCEDURE IF EXISTS add_migration;
