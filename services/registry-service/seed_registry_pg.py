"""Create the registry tables and seed rows in an empty PostgreSQL database.

Mirrors seed_registry.sh. Unlike that script it never deletes anything: it
refuses to run if any registry table already exists.

Usage, from services/registry-service, with DATABASE_URL set (environment or .env):
    uv run python seed_registry_pg.py
"""

import sys
from urllib.parse import urlsplit

import psycopg

import config

TABLES = ("plots", "farms", "crops", "soils", "emitters")

SCHEMA_AND_SEED = """
CREATE TABLE farms (
  id   TEXT PRIMARY KEY,
  name TEXT NOT NULL
);

CREATE TABLE crops (
  id   TEXT PRIMARY KEY,
  name TEXT NOT NULL
);

CREATE TABLE soils (
  id                         TEXT PRIMARY KEY,
  name                       TEXT NOT NULL,
  available_water_mm_per_m   INTEGER NOT NULL
);

CREATE TABLE emitters (
  id       TEXT PRIMARY KEY,
  name     TEXT NOT NULL,
  flow_lph DOUBLE PRECISION NOT NULL
);

CREATE TABLE plots (
  id                 TEXT PRIMARY KEY,
  farm_id            TEXT NOT NULL REFERENCES farms(id),
  name               TEXT NOT NULL,
  area_m2            DOUBLE PRECISION NOT NULL,
  crop_id            TEXT NOT NULL REFERENCES crops(id),
  planting_date      TEXT NOT NULL,
  soil_id            TEXT NOT NULL REFERENCES soils(id),
  row_spacing_m      DOUBLE PRECISION NOT NULL,
  emitter_spacing_m  DOUBLE PRECISION NOT NULL,
  emitter_id         TEXT NOT NULL REFERENCES emitters(id),
  lat                DOUBLE PRECISION NOT NULL,
  lon                DOUBLE PRECISION NOT NULL,
  UNIQUE (farm_id, name)
);

INSERT INTO crops (id, name) VALUES
  ('tomato', 'Tomato'),
  ('bell-pepper', 'Bell pepper');

INSERT INTO soils (id, name, available_water_mm_per_m) VALUES
  ('sand', 'Sand', 83),
  ('loam', 'Loam', 175),
  ('clay-loam', 'Clay loam', 200);

INSERT INTO emitters (id, name, flow_lph) VALUES
  ('dripnet-pc-0.6', 'DripNet PC', 0.6),
  ('dripnet-pc-1.0', 'DripNet PC', 1.0),
  ('dripnet-pc-1.6', 'DripNet PC', 1.6),
  ('dripnet-pc-2.0', 'DripNet PC', 2.0);

INSERT INTO farms (id, name) VALUES
  ('b7e2c0a0-3c1d-4f0a-9a11-0c5d2e6f1001', 'Demo cooperative'),
  ('a9c1e4b2-6f70-4d8e-a144-3f8b5c904004', 'East farm');

INSERT INTO plots (
  id, farm_id, name, area_m2, crop_id, planting_date, soil_id,
  row_spacing_m, emitter_spacing_m, emitter_id, lat, lon
) VALUES
  (
    'c8f3d1b0-4d2e-5a1b-8b22-1d6e3f702002',
    'b7e2c0a0-3c1d-4f0a-9a11-0c5d2e6f1001',
    'North block', 1000, 'tomato', '2026-03-01', 'loam',
    1.5, 0.4, 'dripnet-pc-1.0', 31.25, 34.79
  ),
  (
    'd9a4e2c1-5e3f-4b6a-9c33-2e7f4a803003',
    'b7e2c0a0-3c1d-4f0a-9a11-0c5d2e6f1001',
    'East block', 800, 'bell-pepper', '2026-04-12', 'clay-loam',
    1.5, 0.4, 'dripnet-pc-1.6', 31.26, 34.80
  ),
  (
    'e0b5f3d2-6f40-4c7b-8d44-3f8a5b914004',
    'a9c1e4b2-6f70-4d8e-a144-3f8b5c904004',
    'West block', 1500, 'tomato', '2026-02-15', 'sand',
    1.5, 0.4, 'dripnet-pc-0.6', 31.40, 34.60
  ),
  (
    'f1c6a4e3-7051-4d8c-9e55-4a9b6c025005',
    'a9c1e4b2-6f70-4d8e-a144-3f8b5c904004',
    'Greenhouse', 400, 'bell-pepper', '2026-05-01', 'loam',
    1.2, 0.3, 'dripnet-pc-2.0', 31.41, 34.61
  );
"""


class DatabaseNotEmpty(Exception):
    pass


def seed(conn: psycopg.Connection) -> None:
    with conn.transaction():
        existing = [
            name
            for (name,) in conn.execute(
                "SELECT table_name FROM information_schema.tables"
                " WHERE table_schema = current_schema() AND table_name = ANY(%s)",
                (list(TABLES),),
            )
        ]
        if existing:
            raise DatabaseNotEmpty(
                f"Registry tables already exist: {', '.join(sorted(existing))}"
            )
        conn.execute(SCHEMA_AND_SEED)


def main() -> int:
    try:
        url = config.database_url()
    except ValueError as error:
        print(error, file=sys.stderr)
        return 1
    if urlsplit(url).scheme not in ("postgresql", "postgres"):
        print("DATABASE_URL is not a PostgreSQL URL.", file=sys.stderr)
        return 1
    with psycopg.connect(url) as conn:
        try:
            seed(conn)
        except DatabaseNotEmpty as error:
            print(f"{error}. Nothing was changed.", file=sys.stderr)
            return 1
        counts = {
            table: conn.execute(f"SELECT count(*) FROM {table}").fetchone()[0]
            for table in TABLES
        }
    print("Seeded PostgreSQL database:")
    print("  " + ", ".join(f"{n} {table}" for table, n in counts.items()))
    return 0


if __name__ == "__main__":
    sys.exit(main())
