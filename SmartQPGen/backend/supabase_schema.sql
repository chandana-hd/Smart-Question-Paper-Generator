-- Supabase Database Schema for SmartQPGen
-- Run this in your Supabase SQL editor

-- Enable Row Level Security
ALTER DATABASE postgres SET "app.jwt_secret" TO 'your-jwt-secret';

-- Users table (extends Firebase auth)
CREATE TABLE IF NOT EXISTS users (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    firebase_uid TEXT UNIQUE NOT NULL,
    email TEXT NOT NULL,
    name TEXT,
    role TEXT DEFAULT 'faculty' CHECK (role IN ('faculty', 'hod', 'admin')),
    department TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Question Banks table (from Firebase parsing)
CREATE TABLE IF NOT EXISTS question_banks (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES users(id) ON DELETE CASCADE,
    firebase_doc_id TEXT, -- Reference to Firebase document
    source_file TEXT NOT NULL,
    subject TEXT,
    total_questions INTEGER DEFAULT 0,
    uploaded_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    metadata JSONB DEFAULT '{}'::jsonb
);

-- Saved Question Papers table (main storage in Supabase)
CREATE TABLE IF NOT EXISTS saved_question_papers (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES users(id) ON DELETE CASCADE,
    firebase_paper_id TEXT, -- Reference to Firebase generated paper
    paper_name TEXT NOT NULL,
    subject TEXT,
    pattern TEXT CHECK (pattern IN ('standard', 'cie1', 'cie2', 'custom')),
    total_marks INTEGER DEFAULT 100,
    question_count INTEGER DEFAULT 0,
    questions JSONB NOT NULL DEFAULT '[]'::jsonb,
    metadata JSONB DEFAULT '{}'::jsonb,
    status TEXT DEFAULT 'draft' CHECK (status IN ('draft', 'submitted', 'approved', 'rejected')),
    tags TEXT[] DEFAULT '{}',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Approvals table (HOD approval workflow)
CREATE TABLE IF NOT EXISTS approvals (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    paper_id UUID REFERENCES saved_question_papers(id) ON DELETE CASCADE,
    submitted_by UUID REFERENCES users(id) ON DELETE CASCADE,
    reviewed_by UUID REFERENCES users(id) ON DELETE SET NULL,
    status TEXT DEFAULT 'pending' CHECK (status IN ('pending', 'approved', 'rejected')),
    comments TEXT,
    hod_comments TEXT,
    submitted_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    reviewed_at TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Indexes for better performance
CREATE INDEX IF NOT EXISTS idx_users_firebase_uid ON users(firebase_uid);
CREATE INDEX IF NOT EXISTS idx_question_banks_user_id ON question_banks(user_id);
CREATE INDEX IF NOT EXISTS idx_saved_papers_user_id ON saved_question_papers(user_id);
CREATE INDEX IF NOT EXISTS idx_saved_papers_status ON saved_question_papers(status);
CREATE INDEX IF NOT EXISTS idx_approvals_paper_id ON approvals(paper_id);
CREATE INDEX IF NOT EXISTS idx_approvals_status ON approvals(status);

-- Row Level Security (RLS) policies
ALTER TABLE users ENABLE ROW LEVEL SECURITY;
ALTER TABLE question_banks ENABLE ROW LEVEL SECURITY;
ALTER TABLE saved_question_papers ENABLE ROW LEVEL SECURITY;
ALTER TABLE approvals ENABLE ROW LEVEL SECURITY;

-- Users can only see their own data
CREATE POLICY "Users can view own data" ON users
    FOR ALL USING (auth.uid()::text = firebase_uid);

CREATE POLICY "Users can view own question banks" ON question_banks
    FOR ALL USING (user_id IN (
        SELECT id FROM users WHERE firebase_uid = auth.uid()::text
    ));

CREATE POLICY "Users can view own saved papers" ON saved_question_papers
    FOR ALL USING (user_id IN (
        SELECT id FROM users WHERE firebase_uid = auth.uid()::text
    ));

CREATE POLICY "Users can view own approvals" ON approvals
    FOR ALL USING (submitted_by IN (
        SELECT id FROM users WHERE firebase_uid = auth.uid()::text
    ));

-- HODs can view all approvals
CREATE POLICY "HODs can view all approvals" ON approvals
    FOR ALL USING (reviewed_by IN (
        SELECT id FROM users WHERE firebase_uid = auth.uid()::text AND role = 'hod'
    ));

-- Functions for updated_at timestamps
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ language 'plpgsql';

-- Triggers for updated_at
CREATE TRIGGER update_users_updated_at BEFORE UPDATE ON users
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_saved_papers_updated_at BEFORE UPDATE ON saved_question_papers
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
