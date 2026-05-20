-- ============================================================
-- app_logs 테이블 — 앱 이벤트 영구 로그
-- Supabase SQL Editor에서 실행하세요.
-- ============================================================

-- 1. 테이블 생성
CREATE TABLE IF NOT EXISTS public.app_logs (
    id          BIGSERIAL PRIMARY KEY,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    user_id     UUID REFERENCES auth.users(id) ON DELETE SET NULL,
    level       TEXT NOT NULL DEFAULT 'INFO',   -- INFO / WARNING / ERROR
    event       TEXT NOT NULL,                  -- e.g. login, diary_save, ai_chat_reply
    message     TEXT NOT NULL DEFAULT '',
    extra       JSONB NOT NULL DEFAULT '{}'
);

-- 2. 인덱스 (자주 쓰는 검색 패턴 최적화)
CREATE INDEX IF NOT EXISTS app_logs_created_at_idx ON public.app_logs (created_at DESC);
CREATE INDEX IF NOT EXISTS app_logs_user_id_idx    ON public.app_logs (user_id);
CREATE INDEX IF NOT EXISTS app_logs_event_idx      ON public.app_logs (event);
CREATE INDEX IF NOT EXISTS app_logs_level_idx      ON public.app_logs (level);

-- 3. Row Level Security 활성화
ALTER TABLE public.app_logs ENABLE ROW LEVEL SECURITY;

-- 4. RLS 정책
-- 4-1. 로그 삽입: 모든 사용자 (익명 포함) — 앱이 anon key로 INSERT 함
CREATE POLICY "app_logs_insert_all"
    ON public.app_logs
    FOR INSERT
    WITH CHECK (true);

-- 4-2. 로그 조회: 본인 로그만 읽기
CREATE POLICY "app_logs_select_own"
    ON public.app_logs
    FOR SELECT
    USING (auth.uid() = user_id);

-- (선택) 4-3. 서비스 롤(service_role)로 전체 조회 가능하게 하려면 아래 정책 추가
-- CREATE POLICY "app_logs_select_service"
--     ON public.app_logs
--     FOR SELECT
--     USING (current_setting('role') = 'service_role');

-- 5. 오래된 로그 자동 삭제 (90일 보관)
-- pg_cron 확장이 활성화된 경우에만 작동합니다.
-- Supabase 대시보드 → Database → Extensions → pg_cron 활성화 후 실행하세요.
-- SELECT cron.schedule(
--     'delete_old_app_logs',
--     '0 3 * * *',   -- 매일 새벽 3시
--     $$DELETE FROM public.app_logs WHERE created_at < NOW() - INTERVAL '90 days'$$
-- );
