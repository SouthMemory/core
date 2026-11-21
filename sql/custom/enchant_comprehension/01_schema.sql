CREATE TABLE IF NOT EXISTS `enchant_line` (
  `line_id` INT UNSIGNED NOT NULL,
  `base_spell` INT UNSIGNED NOT NULL DEFAULT 0,
  `base_enchant_id` INT UNSIGNED NOT NULL DEFAULT 0,
  `slot_mask` INT UNSIGNED NOT NULL DEFAULT 0,
  `eq_class` INT NOT NULL DEFAULT -1,
  `eq_subclass` INT UNSIGNED NOT NULL DEFAULT 0,
  `eq_inv` INT UNSIGNED NOT NULL DEFAULT 0,
  `axis_kind` TINYINT UNSIGNED NOT NULL DEFAULT 0,
  PRIMARY KEY (`line_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8;

CREATE TABLE IF NOT EXISTS `enchant_line_rank` (
  `line_id` INT UNSIGNED NOT NULL,
  `direction` TINYINT UNSIGNED NOT NULL,
  `rank` TINYINT UNSIGNED NOT NULL,
  `formula_spell` INT UNSIGNED NOT NULL,
  `enchant_id` INT UNSIGNED NOT NULL,
  `proc_spell` INT UNSIGNED NOT NULL DEFAULT 0,
  `chance_pct` INT UNSIGNED NOT NULL DEFAULT 0,
  `icd_ms` INT UNSIGNED NOT NULL DEFAULT 0,
  PRIMARY KEY (`line_id`, `direction`, `rank`),
  KEY `idx_formula` (`formula_spell`),
  KEY `idx_enchant` (`enchant_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8;
