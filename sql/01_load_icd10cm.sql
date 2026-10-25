-- Loads the FY2027 ICD-10-CM order file into Postgres (table icd10cm).
-- Run from the project folder:
--   docker compose exec -T postgres psql -v ON_ERROR_STOP=1 -U medcoding -d icd < sql/01_load_icd10cm.sql

DROP TABLE IF EXISTS stg_order;
CREATE TABLE stg_order (line text);

\copy stg_order FROM '/import/Code Descriptions/icd10cm_order_2027.txt' WITH (FORMAT csv, DELIMITER E'\x01', QUOTE E'\x02')

DROP TABLE IF EXISTS icd10cm;
CREATE TABLE icd10cm (
  order_num   integer PRIMARY KEY,
  code        text NOT NULL UNIQUE,
  is_billable boolean NOT NULL,
  short_desc  text NOT NULL,
  long_desc   text NOT NULL,
  -- search_text holds each description twice: as written and with hyphens removed,
  -- so "gastroesophageal" and "gastro-esophageal" both match the same code.
  search_text text GENERATED ALWAYS AS (long_desc || ' ' || replace(long_desc, '-', '')) STORED
);

INSERT INTO icd10cm (order_num, code, is_billable, short_desc, long_desc)
SELECT substr(line,1,5)::integer,
       btrim(substr(line,7,7)),
       substr(line,15,1) = '1',
       btrim(substr(line,17,60)),
       btrim(substr(line,78))
FROM stg_order;

CREATE INDEX icd10cm_search_fts_idx
  ON icd10cm USING gin (to_tsvector('english', search_text));
ANALYZE icd10cm;
