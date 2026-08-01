import sqlite3


def create_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS operating_units (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS land_parcels (
            id TEXT PRIMARY KEY,
            operating_unit_id TEXT NOT NULL REFERENCES operating_units(id),
            name TEXT NOT NULL,
            area_hectares REAL NOT NULL,
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS operational_blocks (
            id TEXT PRIMARY KEY,
            operating_unit_id TEXT NOT NULL REFERENCES operating_units(id),
            name TEXT NOT NULL,
            area_hectares REAL NOT NULL,
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS block_parcels (
            operational_block_id TEXT NOT NULL REFERENCES operational_blocks(id),
            land_parcel_id TEXT NOT NULL REFERENCES land_parcels(id),
            created_at TEXT NOT NULL,
            PRIMARY KEY (operational_block_id, land_parcel_id)
        );

        CREATE TABLE IF NOT EXISTS rights_to_operate (
            id TEXT PRIMARY KEY,
            land_parcel_id TEXT NOT NULL REFERENCES land_parcels(id),
            right_type TEXT NOT NULL,
            starts_on TEXT NOT NULL,
            ends_on TEXT NOT NULL,
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS seasons (
            id TEXT PRIMARY KEY,
            operating_unit_id TEXT NOT NULL REFERENCES operating_units(id),
            name TEXT NOT NULL,
            starts_on TEXT NOT NULL,
            ends_on TEXT NOT NULL,
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS crop_allocations (
            id TEXT PRIMARY KEY,
            operating_unit_id TEXT NOT NULL REFERENCES operating_units(id),
            operational_block_id TEXT NOT NULL REFERENCES operational_blocks(id),
            season_id TEXT NOT NULL REFERENCES seasons(id),
            crop_name TEXT NOT NULL,
            cultivar TEXT,
            area_hectares REAL NOT NULL,
            status TEXT NOT NULL,
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS people (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            role TEXT NOT NULL,
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS signal_templates (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            version INTEGER NOT NULL,
            status TEXT NOT NULL,
            fields_json TEXT NOT NULL,
            owner_id TEXT NOT NULL REFERENCES people(id),
            published_at TEXT NOT NULL,
            UNIQUE (name, version)
        );

        CREATE TABLE IF NOT EXISTS work_items (
            id TEXT PRIMARY KEY,
            allocation_id TEXT NOT NULL REFERENCES crop_allocations(id),
            title TEXT NOT NULL,
            owner_id TEXT NOT NULL REFERENCES people(id),
            due_at TEXT NOT NULL,
            status TEXT NOT NULL,
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS exception_records (
            id TEXT PRIMARY KEY,
            allocation_id TEXT NOT NULL REFERENCES crop_allocations(id),
            title TEXT NOT NULL,
            severity TEXT NOT NULL,
            owner_id TEXT NOT NULL REFERENCES people(id),
            fallback_owner_id TEXT NOT NULL REFERENCES people(id),
            observed_at TEXT NOT NULL,
            idempotency_key TEXT NOT NULL UNIQUE,
            status TEXT NOT NULL,
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS decisions (
            id TEXT PRIMARY KEY,
            allocation_id TEXT NOT NULL REFERENCES crop_allocations(id),
            title TEXT NOT NULL,
            owner_id TEXT NOT NULL REFERENCES people(id),
            review_due_at TEXT NOT NULL,
            status TEXT NOT NULL,
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS audit_events (
            id TEXT PRIMARY KEY,
            entity_type TEXT NOT NULL,
            entity_id TEXT NOT NULL,
            from_status TEXT NOT NULL,
            to_status TEXT NOT NULL,
            actor_id TEXT NOT NULL REFERENCES people(id),
            reason TEXT NOT NULL,
            created_at TEXT NOT NULL
        );
        """
    )
    conn.commit()
