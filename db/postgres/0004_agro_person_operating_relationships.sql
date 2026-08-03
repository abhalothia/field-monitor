-- Time-bounded, reviewed person relationships to one FFL operating scope.
--
-- Apply manually after 0001 through 0003 with the reviewed private migration
-- role.  This only adds private ``agro`` relations; it must not expose any
-- contact or land relationship through Supabase's Data API.

BEGIN;
SET LOCAL search_path = agro, pg_catalog;

CREATE TABLE IF NOT EXISTS agro_person_operating_relationships (
    id TEXT PRIMARY KEY,
    person_id TEXT NOT NULL REFERENCES agro_people(id),
    scope_type TEXT NOT NULL CHECK (scope_type IN (
        'operating_unit', 'land_parcel', 'operational_block', 'crop_allocation'
    )),
    operating_unit_id TEXT REFERENCES agro_operating_units(id),
    land_parcel_id TEXT REFERENCES agro_land_parcels(id),
    operational_block_id TEXT REFERENCES agro_operational_blocks(id),
    crop_allocation_id TEXT REFERENCES agro_crop_allocations(id),
    role TEXT NOT NULL CHECK (role IN (
        'grower', 'landholder', 'lessee', 'field_operator', 'manager',
        'agronomist', 'reviewer', 'buyer_contact'
    )),
    starts_on DATE NOT NULL,
    ends_on DATE,
    status TEXT NOT NULL CHECK (status IN ('active', 'ended')),
    provenance TEXT,
    reviewed_by_person_id TEXT REFERENCES agro_people(id),
    ended_by_person_id TEXT REFERENCES agro_people(id),
    ended_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL,
    CHECK (
        (scope_type = 'operating_unit' AND operating_unit_id IS NOT NULL
            AND land_parcel_id IS NULL AND operational_block_id IS NULL AND crop_allocation_id IS NULL)
        OR
        (scope_type = 'land_parcel' AND land_parcel_id IS NOT NULL
            AND operating_unit_id IS NULL AND operational_block_id IS NULL AND crop_allocation_id IS NULL)
        OR
        (scope_type = 'operational_block' AND operational_block_id IS NOT NULL
            AND operating_unit_id IS NULL AND land_parcel_id IS NULL AND crop_allocation_id IS NULL)
        OR
        (scope_type = 'crop_allocation' AND crop_allocation_id IS NOT NULL
            AND operating_unit_id IS NULL AND land_parcel_id IS NULL AND operational_block_id IS NULL)
    ),
    CHECK ((status = 'active' AND ends_on IS NULL AND ended_by_person_id IS NULL AND ended_at IS NULL)
        OR (status = 'ended' AND ends_on IS NOT NULL)),
    CHECK (provenance IS NOT NULL OR reviewed_by_person_id IS NOT NULL)
);

CREATE INDEX IF NOT EXISTS agro_idx_person_operating_relationships_person_starts
    ON agro_person_operating_relationships (person_id, starts_on, created_at);
CREATE INDEX IF NOT EXISTS agro_idx_person_operating_relationships_scope_starts
    ON agro_person_operating_relationships (
        scope_type, operating_unit_id, land_parcel_id, operational_block_id,
        crop_allocation_id, starts_on, created_at
    );
CREATE UNIQUE INDEX IF NOT EXISTS agro_idx_relationship_active_operating_unit
    ON agro_person_operating_relationships (person_id, operating_unit_id, role)
    WHERE status = 'active' AND scope_type = 'operating_unit';
CREATE UNIQUE INDEX IF NOT EXISTS agro_idx_relationship_active_land_parcel
    ON agro_person_operating_relationships (person_id, land_parcel_id, role)
    WHERE status = 'active' AND scope_type = 'land_parcel';
CREATE UNIQUE INDEX IF NOT EXISTS agro_idx_relationship_active_operational_block
    ON agro_person_operating_relationships (person_id, operational_block_id, role)
    WHERE status = 'active' AND scope_type = 'operational_block';
CREATE UNIQUE INDEX IF NOT EXISTS agro_idx_relationship_active_crop_allocation
    ON agro_person_operating_relationships (person_id, crop_allocation_id, role)
    WHERE status = 'active' AND scope_type = 'crop_allocation';

REVOKE ALL ON TABLE agro_person_operating_relationships FROM PUBLIC;

COMMIT;
