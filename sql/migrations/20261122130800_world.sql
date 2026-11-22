DROP PROCEDURE IF EXISTS add_migration;
DELIMITER ??
CREATE PROCEDURE `add_migration`()
BEGIN
DECLARE v INT DEFAULT 1;
SET v = (SELECT COUNT(*) FROM `migrations` WHERE `id`='20261122130800');
IF v = 0 THEN
INSERT INTO `migrations` VALUES ('20261122130800');
-- Add your query below.


CREATE TABLE IF NOT EXISTS `creature_persona_map` (
  `entry` mediumint(8) unsigned NOT NULL,
  `persona_class` tinyint(3) unsigned NOT NULL DEFAULT '0' COMMENT 'CLASS_* ; 0=none',
  `persona_spec` tinyint(3) unsigned NOT NULL DEFAULT '0' COMMENT 'PersonaSpec; 0=randomizable',
  `override` tinyint(1) unsigned NOT NULL DEFAULT '0' COMMENT '1=hand edit, generator skips',
  `comment` varchar(255) NOT NULL DEFAULT '',
  PRIMARY KEY (`entry`)
) ENGINE=MyISAM DEFAULT CHARSET=utf8 ROW_FORMAT=DYNAMIC COMMENT='CreaturePersona class mapping';


-- End of migration.
END IF;
END??
DELIMITER ;
CALL add_migration();
DROP PROCEDURE IF EXISTS add_migration;
