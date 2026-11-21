-- Bonereaver 21153 variants: 3 directions x 3 ranks
CREATE TABLE IF NOT EXISTS `enchant_comprehension_variant` (
  `source_spell` INT UNSIGNED NOT NULL,
  `direction` TINYINT UNSIGNED NOT NULL COMMENT '1=chance 2=icd 3=power',
  `rank` TINYINT UNSIGNED NOT NULL,
  `enchant_id` INT UNSIGNED NOT NULL,
  `formula_spell` INT UNSIGNED NOT NULL,
  `proc_spell` INT UNSIGNED NOT NULL,
  `chance_pct` INT UNSIGNED NOT NULL DEFAULT 0,
  `icd_ms` INT UNSIGNED NOT NULL DEFAULT 0,
  PRIMARY KEY (`source_spell`,`direction`,`rank`),
  KEY `idx_formula` (`formula_spell`),
  KEY `idx_enchant` (`enchant_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8;
DELETE FROM `enchant_comprehension_variant` WHERE `source_spell`=21153;
INSERT INTO `enchant_comprehension_variant` (`source_spell`,`direction`,`rank`,`enchant_id`,`formula_spell`,`proc_spell`,`chance_pct`,`icd_ms`) VALUES
(21153,1,1,30200,35210,21153,8,0),
(21153,1,2,30201,35211,21153,12,0),
(21153,1,3,30202,35212,21153,16,0),
(21153,2,1,30203,35213,21153,0,40000),
(21153,2,2,30204,35214,21153,0,25000),
(21153,2,3,30205,35215,21153,0,12000),
(21153,3,1,30206,35216,35200,0,0),
(21153,3,2,30207,35217,35201,0,0),
(21153,3,3,30208,35218,35202,0,0);
DELETE FROM `enchant_comprehension_map` WHERE `source_spell`=21153;
DELETE FROM `enchant_upgrade_override` WHERE `chain_id` IN (2001,2002,2003);
INSERT INTO `enchant_upgrade_override` (`spell_id`,`mode`,`chain_id`,`rank`) VALUES
(35210,1,2001,0),
(35211,1,2001,1),
(35212,1,2001,2),
(35213,1,2002,0),
(35214,1,2002,1),
(35215,1,2002,2),
(35216,1,2003,0),
(35217,1,2003,1),
(35218,1,2003,2);
