-- ============================================
-- مذكرتي الذكية - Supabase Migration
-- ============================================

-- Enable UUID extension
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- 🗺️ Places (Locations)
CREATE TABLE IF NOT EXISTS places (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    title TEXT,
    lat DOUBLE PRECISION,
    lon DOUBLE PRECISION,
    maps_url TEXT,
    address TEXT,
    category TEXT DEFAULT 'مكان',
    status TEXT DEFAULT 'للزيارة لاحقًا',
    notes TEXT,
    photo_url TEXT,
    photo_path TEXT,
    synced_to_obsidian BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- 📝 Notes
CREATE TABLE IF NOT EXISTS notes (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    title TEXT,
    note_type TEXT DEFAULT 'يومية',
    mood TEXT,
    cause TEXT,
    body TEXT,
    action TEXT DEFAULT 'حفظ فقط',
    topics TEXT[] DEFAULT '{}',
    tags TEXT[] DEFAULT '{}',
    synced_to_obsidian BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- 🔗 Links
CREATE TABLE IF NOT EXISTS links (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    url TEXT,
    title TEXT,
    kind TEXT DEFAULT 'موقع',
    reason TEXT,
    status TEXT DEFAULT 'جديد',
    notes TEXT,
    tags TEXT[] DEFAULT '{}',
    image_url TEXT,
    synced_to_obsidian BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- 📊 Trackers
CREATE TABLE IF NOT EXISTS trackers (
    id TEXT PRIMARY KEY,
    name TEXT,
    kind TEXT DEFAULT 'رقم',
    unit TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- 📈 Tracker Entries
CREATE TABLE IF NOT EXISTS tracker_entries (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tracker_id TEXT REFERENCES trackers(id) ON DELETE CASCADE,
    value TEXT,
    notes TEXT,
    date DATE DEFAULT CURRENT_DATE,
    synced_to_obsidian BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- 🔄 Sync Log
CREATE TABLE IF NOT EXISTS sync_log (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    entity_type TEXT,
    entity_id TEXT,
    action TEXT DEFAULT 'sync',
    status TEXT DEFAULT 'ok',
    synced_to_obsidian BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- 📑 Indexes
CREATE INDEX IF NOT EXISTS idx_places_created ON places(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_places_synced ON places(synced_to_obsidian);
CREATE INDEX IF NOT EXISTS idx_notes_created ON notes(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_notes_synced ON notes(synced_to_obsidian);
CREATE INDEX IF NOT EXISTS idx_links_created ON links(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_links_synced ON links(synced_to_obsidian);
CREATE INDEX IF NOT EXISTS idx_tracker_entries_date ON tracker_entries(date DESC);
CREATE INDEX IF NOT EXISTS idx_tracker_entries_synced ON tracker_entries(synced_to_obsidian);

-- ✅ Enable Row Level Security
ALTER TABLE places ENABLE ROW LEVEL SECURITY;
ALTER TABLE notes ENABLE ROW LEVEL SECURITY;
ALTER TABLE links ENABLE ROW LEVEL SECURITY;
ALTER TABLE trackers ENABLE ROW LEVEL SECURITY;
ALTER TABLE tracker_entries ENABLE ROW LEVEL SECURITY;
ALTER TABLE sync_log ENABLE ROW LEVEL SECURITY;

-- 👤 Allow public access (single-user app)
CREATE POLICY "Allow all on places" ON places FOR ALL USING (true) WITH CHECK (true);
CREATE POLICY "Allow all on notes" ON notes FOR ALL USING (true) WITH CHECK (true);
CREATE POLICY "Allow all on links" ON links FOR ALL USING (true) WITH CHECK (true);
CREATE POLICY "Allow all on trackers" ON trackers FOR ALL USING (true) WITH CHECK (true);
CREATE POLICY "Allow all on tracker_entries" ON tracker_entries FOR ALL USING (true) WITH CHECK (true);
CREATE POLICY "Allow all on sync_log" ON sync_log FOR ALL USING (true) WITH CHECK (true);
