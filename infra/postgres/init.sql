-- PostgreSQL init script
-- Runs once when the container is first created.
-- Creates the n8n schema so n8n can store its own state in the same Postgres
-- instance (saves running a separate DB container).

CREATE SCHEMA IF NOT EXISTS n8n;
