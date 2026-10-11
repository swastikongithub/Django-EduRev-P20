-- Runs once, the first time the PostgreSQL container starts with an empty volume.
-- The automated tests use (and wipe) this separate database, never your development data.
CREATE DATABASE foodloop_test OWNER foodloop;
