-- Provider-facing identity map. Internal UUIDs remain primary keys forever.

CREATE TABLE IF NOT EXISTS external_ids (
    id           UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
    entity_type  VARCHAR(30)  NOT NULL
                   CHECK (entity_type IN (
                       'club', 'player', 'fixture', 'tournament', 'user'
                   )),
    entity_id    UUID         NOT NULL,
    provider     VARCHAR(50)  NOT NULL,
    external_id  VARCHAR(255) NOT NULL,
    created_at   TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    updated_at   TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    UNIQUE (provider, entity_type, external_id),
    UNIQUE (provider, entity_type, entity_id)
);

CREATE INDEX IF NOT EXISTS idx_external_ids_entity
    ON external_ids (entity_type, entity_id);
CREATE INDEX IF NOT EXISTS idx_external_ids_lookup
    ON external_ids (provider, entity_type, external_id);
