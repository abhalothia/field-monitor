-- FFL external-data foundation. Apply after 0001_ffl_private_schema.sql,
-- through a reviewed direct/session PostgreSQL connection to the authorised
-- Supabase project. This migration is intentionally private: no ffl.ext_*
-- relation is exposed to the Data API.

begin;

create table if not exists ffl.ext_geography_datasets (
    id uuid primary key,
    source_id text not null references ffl.source_registry(id),
    state_slug text not null check (state_slug in ('andhra_pradesh', 'telangana', 'karnataka', 'tamil_nadu', 'kerala')),
    state_code text not null check (state_code ~ '^[0-9]+$'),
    revision text not null check (revision ~ '^[0-9a-f]{40}$'),
    content_sha256 text not null check (content_sha256 ~ '^[0-9a-f]{64}$'),
    source_url text not null check (source_url ~ '^https://raw.githubusercontent.com/'),
    attribution text not null,
    status text not null check (status in ('review', 'published', 'quarantined', 'retired')),
    reviewed_by text,
    reviewed_at timestamptz,
    created_at timestamptz not null default now(),
    unique (source_id, state_slug, revision),
    unique (source_id, state_slug, content_sha256),
    check ((status = 'published') = (reviewed_by is not null and reviewed_at is not null))
);

create table if not exists ffl.ext_places (
    dataset_id uuid not null references ffl.ext_geography_datasets(id),
    place_kind text not null check (place_kind in ('district', 'subdistrict', 'village')),
    place_code text not null check (place_code ~ '^[0-9]+$'),
    parent_code text,
    canonical_name text not null,
    native_name text,
    native_name_source text check (native_name_source in ('authoritative', 'transliterated')),
    pincode text check (pincode is null or pincode ~ '^[0-9]{6}$'),
    created_at timestamptz not null default now(),
    primary key (dataset_id, place_kind, place_code),
    check ((native_name is null) = (native_name_source is null)),
    check (
        (place_kind = 'district' and parent_code is not null)
        or (place_kind in ('subdistrict', 'village') and parent_code is not null)
    )
);

create index if not exists ext_places_dataset_parent_idx
    on ffl.ext_places (dataset_id, parent_code, place_kind);
create index if not exists ext_places_dataset_name_idx
    on ffl.ext_places (dataset_id, canonical_name);
create index if not exists ext_places_dataset_pincode_idx
    on ffl.ext_places (dataset_id, pincode) where pincode is not null;

create table if not exists ffl.ext_location_bindings (
    operating_unit_id text primary key references ffl.operating_units(id),
    dataset_id uuid not null,
    village_place_kind text not null default 'village'
        check (village_place_kind = 'village'),
    village_code text not null,
    bound_by text not null,
    bound_at timestamptz not null default now(),
    supersedes_operating_unit_id text,
    notes text,
    foreign key (dataset_id, village_place_kind, village_code)
        references ffl.ext_places(dataset_id, place_kind, place_code)
        deferrable initially immediate
);

revoke all on all tables in schema ffl from public;
revoke all on all tables in schema ffl from anon;
revoke all on all tables in schema ffl from authenticated;

commit;
