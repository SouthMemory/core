CREATE TABLE IF NOT EXISTS `enchant_comprehension_variant` (
  `source_spell` INT UNSIGNED NOT NULL,
  `direction` TINYINT UNSIGNED NOT NULL,
  `rank` TINYINT UNSIGNED NOT NULL,
  `enchant_id` INT UNSIGNED NOT NULL,
  `formula_spell` INT UNSIGNED NOT NULL,
  `proc_spell` INT UNSIGNED NOT NULL,
  `chance_pct` INT UNSIGNED NOT NULL DEFAULT 0,
  `icd_ms` INT UNSIGNED NOT NULL DEFAULT 0,
  PRIMARY KEY (`source_spell`,`direction`,`rank`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8;
DELETE FROM `enchant_comprehension_variant` WHERE `source_spell`=9632;
INSERT INTO `enchant_comprehension_variant` (`source_spell`,`direction`,`rank`,`enchant_id`,`formula_spell`,`proc_spell`,`chance_pct`,`icd_ms`) VALUES
(9632,1,1,30220,35260,9632,0,0),
(9632,1,2,30221,35261,9632,8,0),
(9632,1,3,30222,35262,9632,12,0),
(9632,1,4,30223,35263,9632,16,0),
(9632,2,1,30224,35264,9632,0,0),
(9632,2,2,30225,35265,35230,0,0),
(9632,2,3,30226,35266,35231,0,0),
(9632,2,4,30227,35267,35232,0,0),
(9632,3,1,30228,35268,9632,0,0),
(9632,3,2,30229,35269,35240,0,0),
(9632,3,3,30230,35270,35241,0,0),
(9632,3,4,30231,35271,35242,0,0);
DELETE FROM `enchant_comprehension_map` WHERE `source_spell`=9632;
DELETE FROM `enchant_upgrade_override` WHERE `chain_id` IN (2010,2011,2012);
INSERT INTO `enchant_upgrade_override` (`spell_id`,`mode`,`chain_id`,`rank`) VALUES
(35260,1,2010,0),
(35261,1,2010,1),
(35262,1,2010,2),
(35263,1,2010,3),
(35264,1,2011,0),
(35265,1,2011,1),
(35266,1,2011,2),
(35267,1,2011,3),
(35268,1,2012,0),
(35269,1,2012,1),
(35270,1,2012,2),
(35271,1,2012,3);
