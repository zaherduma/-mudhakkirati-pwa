-- ============================================
-- مذكرتي الذكية - Migration v3
-- جدول الإعدادات (رمز الدخول...)
-- ============================================

-- ⚙️ الإعدادات
CREATE TABLE IF NOT EXISTS settings (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    key TEXT NOT NULL UNIQUE,
    value TEXT NOT NULL,
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- 🔒 RLS
ALTER TABLE settings ENABLE ROW LEVEL SECURITY;

-- 👤 سياسة السماح للجميع
DROP POLICY IF EXISTS "Allow all on settings" ON settings;
CREATE POLICY "Allow all on settings" ON settings FOR ALL USING (true) WITH CHECK (true);

-- 🚀 إدراج القيمة الافتراضية لرمز الدخول
INSERT INTO settings (key, value) VALUES ('passcode', '000000')
ON CONFLICT (key) DO NOTHING;
