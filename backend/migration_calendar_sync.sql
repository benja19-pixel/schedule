-- Agregar columnas faltantes a la tabla synced_events
ALTER TABLE synced_events 
ADD COLUMN IF NOT EXISTS existed_before_sync BOOLEAN DEFAULT FALSE;

ALTER TABLE synced_events 
ADD COLUMN IF NOT EXISTS recurring_group_id VARCHAR(255);

ALTER TABLE synced_events 
ADD COLUMN IF NOT EXISTS is_master_event BOOLEAN DEFAULT FALSE;

ALTER TABLE synced_events 
ADD COLUMN IF NOT EXISTS event_date DATE;

-- Agregar columnas faltantes a la tabla horario_templates
ALTER TABLE horario_templates
ADD COLUMN IF NOT EXISTS has_synced_breaks BOOLEAN DEFAULT FALSE;

ALTER TABLE horario_templates
ADD COLUMN IF NOT EXISTS last_sync_update TIMESTAMP;

-- Agregar columnas faltantes a la tabla horario_exceptions
ALTER TABLE horario_exceptions
ADD COLUMN IF NOT EXISTS sync_source VARCHAR(50);

ALTER TABLE horario_exceptions
ADD COLUMN IF NOT EXISTS external_calendar_id VARCHAR(255);

ALTER TABLE horario_exceptions
ADD COLUMN IF NOT EXISTS sync_metadata JSON;

ALTER TABLE horario_exceptions
ADD COLUMN IF NOT EXISTS is_synced BOOLEAN DEFAULT FALSE;

ALTER TABLE horario_exceptions
ADD COLUMN IF NOT EXISTS sync_connection_id UUID;

-- Actualizar el default de sync_settings en calendar_connections para merge_calendars = true
UPDATE calendar_connections 
SET sync_settings = jsonb_set(
    COALESCE(sync_settings, '{}')::jsonb, 
    '{merge_calendars}', 
    'true'::jsonb
)
WHERE sync_settings IS NULL OR (sync_settings->>'merge_calendars')::boolean IS NULL;