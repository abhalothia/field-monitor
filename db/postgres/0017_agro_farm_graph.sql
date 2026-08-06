-- Canonical private Farm-to-Field graph.  A field may have one current Farm
-- membership while retaining ended membership history for reviewed reassignments.

BEGIN;

SET LOCAL search_path = agro, pg_catalog;

CREATE TABLE IF NOT EXISTS agro_farms (
    id TEXT PRIMARY KEY,
    operating_unit_id TEXT NOT NULL REFERENCES agro_operating_units(id),
    name TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('active', 'archived')),
    reviewed_by_person_id TEXT NOT NULL REFERENCES agro_people(id),
    created_at TIMESTAMPTZ NOT NULL
);

CREATE TABLE IF NOT EXISTS agro_farm_fields (
    id TEXT PRIMARY KEY,
    farm_id TEXT NOT NULL REFERENCES agro_farms(id),
    operational_block_id TEXT NOT NULL REFERENCES agro_operational_blocks(id),
    starts_on DATE NOT NULL,
    ends_on DATE,
    status TEXT NOT NULL CHECK (status IN ('active', 'ended')),
    reviewed_by_person_id TEXT NOT NULL REFERENCES agro_people(id),
    created_at TIMESTAMPTZ NOT NULL,
    CHECK ((status = 'active' AND ends_on IS NULL) OR (status = 'ended' AND ends_on IS NOT NULL))
);

CREATE UNIQUE INDEX IF NOT EXISTS agro_idx_farm_fields_one_active_field
    ON agro_farm_fields (operational_block_id) WHERE status = 'active';

CREATE OR REPLACE FUNCTION agro_guard_farm_field_operating_unit()
RETURNS TRIGGER
LANGUAGE plpgsql
SET search_path = agro, pg_catalog
AS $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM agro_farms
        JOIN agro_operational_blocks
          ON agro_operational_blocks.id = NEW.operational_block_id
        WHERE agro_farms.id = NEW.farm_id
          AND agro_farms.operating_unit_id = agro_operational_blocks.operating_unit_id
    ) THEN
        RAISE EXCEPTION 'farm and field must belong to the same operating unit';
    END IF;
    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS agro_farm_fields_matching_operating_unit ON agro_farm_fields;
CREATE TRIGGER agro_farm_fields_matching_operating_unit
BEFORE INSERT OR UPDATE OF farm_id, operational_block_id ON agro_farm_fields
FOR EACH ROW EXECUTE FUNCTION agro_guard_farm_field_operating_unit();

REVOKE ALL ON TABLE agro_farms, agro_farm_fields FROM PUBLIC;
REVOKE ALL ON FUNCTION agro_guard_farm_field_operating_unit() FROM PUBLIC;
GRANT SELECT, INSERT ON TABLE agro_farms, agro_farm_fields TO agro_vc_runtime;

COMMIT;
