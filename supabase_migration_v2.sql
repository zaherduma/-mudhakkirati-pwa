-- ============================================
-- مذكرتي الذكية - Migration v2
-- جداول التصنيفات المخصصة
-- ============================================

-- 🏷️ أنواع المذكرات
CREATE TABLE IF NOT EXISTS note_types (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    name TEXT NOT NULL UNIQUE,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- 😊 الحالات
CREATE TABLE IF NOT EXISTS moods (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    name TEXT NOT NULL UNIQUE,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- 📍 تصنيفات الأماكن
CREATE TABLE IF NOT EXISTS place_categories (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    name TEXT NOT NULL UNIQUE,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- 🔗 أنواع الروابط
CREATE TABLE IF NOT EXISTS link_types (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    name TEXT NOT NULL UNIQUE,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- 📊 أنواع المتتبعات
CREATE TABLE IF NOT EXISTS tracker_types (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    name TEXT NOT NULL UNIQUE,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- 🔒 RLS
ALTER TABLE note_types ENABLE ROW LEVEL SECURITY;
ALTER TABLE moods ENABLE ROW LEVEL SECURITY;
ALTER TABLE place_categories ENABLE ROW LEVEL SECURITY;
ALTER TABLE link_types ENABLE ROW LEVEL SECURITY;
ALTER TABLE tracker_types ENABLE ROW LEVEL SECURITY;

-- 👤 سياسات السماح للجميع (تطبيق مستخدم واحد)
DROP POLICY IF EXISTS "Allow all on note_types" ON note_types;
CREATE POLICY "Allow all on note_types" ON note_types FOR ALL USING (true) WITH CHECK (true);
DROP POLICY IF EXISTS "Allow all on moods" ON moods;
CREATE POLICY "Allow all on moods" ON moods FOR ALL USING (true) WITH CHECK (true);
DROP POLICY IF EXISTS "Allow all on place_categories" ON place_categories;
CREATE POLICY "Allow all on place_categories" ON place_categories FOR ALL USING (true) WITH CHECK (true);
DROP POLICY IF EXISTS "Allow all on link_types" ON link_types;
CREATE POLICY "Allow all on link_types" ON link_types FOR ALL USING (true) WITH CHECK (true);
DROP POLICY IF EXISTS "Allow all on tracker_types" ON tracker_types;
CREATE POLICY "Allow all on tracker_types" ON tracker_types FOR ALL USING (true) WITH CHECK (true);
