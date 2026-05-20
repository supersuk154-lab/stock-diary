# Supabase 데이터베이스 스키마 검사 및 상태 보고서

사용자님께서 제공해 주신 모든 SQL 설정 및 변경 스크립트를 기반으로 데이터베이스 구조를 검사한 결과 보고서입니다.

---

## 🔍 주요 발견 사항 및 잠재적 문제점

현재 데이터베이스는 정상 동작하는 수준이지만, 시간이 지나면서 여러 테이블 생성 및 변경(Alter) 스크립트가 누적 적용되어 몇 가지 비일관성, 중복 규칙, 그리고 PostgreSQL의 고유한 동작 특징으로 인한 잠재적 문제가 발견되었습니다.

### 1. 컬럼 기본값 제약 조건 스킵 (`IF NOT EXISTS` 특징)
- **문제점**: 기존에 `ticker` 컬럼을 기본값 없이 생성한 상태에서, 나중에 `ALTER TABLE trades ADD COLUMN IF NOT EXISTS ticker TEXT DEFAULT '';`를 실행하면 **PostgreSQL은 컬럼이 이미 존재하므로 이 문장 전체를 무시(스킵)합니다.**
- **영향**: 컬럼은 존재하지만 기본값 제약 조건이 걸리지 않아, 향후 티커 없이 데이터를 추가할 때 빈 문자열(`''`) 대신 `NULL` 값이 들어갈 수 있습니다.
- **해결 방안**: 컬럼의 기본값(Default)을 명시적으로 재설정하는 SQL을 실행해야 합니다.

### 2. 불필요하게 중복된 RLS 보안 정책
- **문제점**: `trades` 및 `journals` 테이블에 대해 개별 보안 정책(`Users can view own trades`, `Users can insert own trades` 등)과 전체 권한 통합 정책(`own_data_only`)이 중복 적용되어 있습니다.
- **영향**: PostgreSQL에서 여러 개의 RLS 허용(Permissive) 정책은 **`OR`** 조건으로 합쳐집니다. 기능상 차단되지는 않지만, 나중에 정책을 수정할 때 일부 중복 정책을 빠뜨려 보안 구멍이 생길 수 있으므로 불필요한 정책은 정리하는 것이 좋습니다.
- **해결 방안**: 지저분한 개별 정책을 삭제하고, 안전하고 깔끔한 `own_data_only` 하나로 단일화합니다.

### 3. 수량 및 단가 데이터 타입의 혼용 (Float vs Numeric)
- **문제점**: 일부 스크립트에서는 `quantity`와 `price`를 `float`으로 설정했고, 다른 스크립트에서는 정확도가 높은 `numeric` 타입으로 설정했습니다.
- **영향**: 소수점이 들어가는 금융 데이터(특히 주식 수량 및 단가)는 `float` 타입을 사용할 경우 미세한 부동 소수점 연산 오류(예: `0.1 + 0.2 = 0.30000000000000004`)가 누적되어 총자산 계산 시 오차가 발생할 수 있습니다.
- **해결 방안**: 수량, 단가, 배당금 관련 금액 컬럼들을 모두 정확한 연산이 가능한 `numeric` 타입으로 통일합니다.

---

## 🛠️ 데이터베이스 정리 및 최적화 SQL 스크립트

Supabase **SQL Editor**에 아래 쿼리를 전체 복사하여 붙여넣고 우측 하단의 **Run** 버튼을 실행해 주시면, 중복 정책이 깔끔하게 삭제되고 컬럼 타입 및 기본값 설정이 올바르게 교정됩니다.

```sql
-- ============================================================
-- 1. 중복된 RLS 보안 정책 깔끔하게 제거
-- ============================================================

-- journals 테이블의 중복 정책 삭제
DROP POLICY IF EXISTS "Users can view own journals" ON public.journals;
DROP POLICY IF EXISTS "Users can insert own journals" ON public.journals;
DROP POLICY IF EXISTS "Users can update own journals" ON public.journals;
DROP POLICY IF EXISTS "Users can delete own journals" ON public.journals;

-- trades 테이블의 중복 정책 삭제
DROP POLICY IF EXISTS "Users can view own trades" ON public.trades;
DROP POLICY IF EXISTS "Users can insert own trades" ON public.trades;
DROP POLICY IF EXISTS "Users can update own trades" ON public.trades;
DROP POLICY IF EXISTS "Users can delete own trades" ON public.trades;

-- ============================================================
-- 2. 컬럼 기본값(Default) 및 데이터 타입 최적화
-- ============================================================

-- trades 테이블의 ticker 컬럼 기본값 강제 설정 및 기존 NULL 보정
ALTER TABLE public.trades ALTER COLUMN ticker SET DEFAULT '';
UPDATE public.trades SET ticker = '' WHERE ticker IS NULL;

-- trades 테이블의 type 컬럼 기본값 강제 설정 및 기존 NULL 보정
ALTER TABLE public.trades ALTER COLUMN type SET DEFAULT 'buy';
UPDATE public.trades SET type = 'buy' WHERE type IS NULL;

-- 수량, 단가, 배당금 데이터 타입을 정확한 numeric(실수형)으로 통일
ALTER TABLE public.trades ALTER COLUMN quantity TYPE numeric;
ALTER TABLE public.trades ALTER COLUMN price TYPE numeric;
ALTER TABLE public.trades ALTER COLUMN dividend_amount TYPE numeric;

-- 배당금 컬럼의 기본값 설정 및 기존 NULL 보정
ALTER TABLE public.trades ALTER COLUMN dividend_amount SET DEFAULT 0;
UPDATE public.trades SET dividend_amount = 0 WHERE dividend_amount IS NULL;
```

---

## 🗑️ 데이터베이스 전체 초기화 및 깔끔한 재구축 SQL 스크립트

기존 데이터를 모두 삭제하고 완벽하게 깨끗한 상태에서 데이터베이스를 처음부터 새로 구축하시려면, 아래 스크립트를 전체 복사하여 Supabase **SQL Editor**에서 실행해 주세요. 

> [!WARNING]
> 이 스크립트를 실행하면 기존의 모든 거래 내역(`trades`), 일기(`journals`), 로그(`app_logs`) 데이터가 영구적으로 삭제(Drop)됩니다.

```sql
-- ============================================================
-- 1. 기존 테이블 및 정책 전체 삭제 (의존성 순서 고려)
-- ============================================================
DROP TABLE IF EXISTS public.journals CASCADE;
DROP TABLE IF EXISTS public.trades CASCADE;
DROP TABLE IF EXISTS public.krx_tickers CASCADE;
DROP TABLE IF EXISTS public.daily_reports CASCADE;
DROP TABLE IF EXISTS public.app_logs CASCADE;

-- ============================================================
-- 2. journals (다이어리 작성 이력) 테이블 생성
-- ============================================================
CREATE TABLE public.journals (
  id          BIGSERIAL PRIMARY KEY,
  user_id     UUID REFERENCES auth.users(id) ON DELETE CASCADE NOT NULL DEFAULT auth.uid(),
  created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  tags        TEXT NOT NULL DEFAULT '',
  content     TEXT NOT NULL DEFAULT '',
  ai_feedback TEXT NOT NULL DEFAULT ''
);

CREATE INDEX journals_user_created_idx ON public.journals (user_id, created_at DESC);
CREATE INDEX journals_tags_idx ON public.journals USING gin (to_tsvector('simple', tags));

ALTER TABLE public.journals ENABLE ROW LEVEL SECURITY;
CREATE POLICY "own_data_only" ON public.journals FOR ALL USING (auth.uid() = user_id);

-- ============================================================
-- 3. trades (매매 및 배당금 거래 기록) 테이블 생성
-- ============================================================
CREATE TABLE public.trades (
  id              BIGSERIAL PRIMARY KEY,
  user_id         UUID REFERENCES auth.users(id) ON DELETE CASCADE NOT NULL DEFAULT auth.uid(),
  created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  stock_name      TEXT NOT NULL,
  quantity        NUMERIC NOT NULL DEFAULT 0,
  price           NUMERIC NOT NULL DEFAULT 0,
  currency        TEXT NOT NULL DEFAULT 'KRW',
  type            TEXT NOT NULL DEFAULT 'buy', -- 'buy' | 'sell' | 'dividend'
  dividend_amount NUMERIC NOT NULL DEFAULT 0,
  ticker          TEXT NOT NULL DEFAULT ''
);

CREATE INDEX trades_user_created_idx ON public.trades (user_id, created_at DESC);

ALTER TABLE public.trades ENABLE ROW LEVEL SECURITY;
CREATE POLICY "own_data_only" ON public.trades FOR ALL USING (auth.uid() = user_id);

-- ============================================================
-- 4. krx_tickers (국내 주식 종목명/티커 캐시 테이블) 테이블 생성
-- ============================================================
CREATE TABLE public.krx_tickers (
  name       TEXT PRIMARY KEY,
  ticker     TEXT NOT NULL,
  updated_at TIMESTAMPTZ DEFAULT NOW()
);

ALTER TABLE public.krx_tickers ENABLE ROW LEVEL SECURITY;
CREATE POLICY "krx_tickers_select" ON public.krx_tickers FOR SELECT USING (true);
CREATE POLICY "krx_tickers_upsert" ON public.krx_tickers FOR ALL USING (auth.role() = 'authenticated');

-- ============================================================
-- 5. daily_reports (일일 리포트 게시판) 테이블 생성
-- ============================================================
CREATE TABLE public.daily_reports (
  id           BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  created_at   TIMESTAMPTZ DEFAULT NOW(),
  title        TEXT NOT NULL,
  html_content TEXT NOT NULL,
  uploaded_by  TEXT NOT NULL DEFAULT ''
);

ALTER TABLE public.daily_reports ENABLE ROW LEVEL SECURITY;
CREATE POLICY "authenticated users can read" ON public.daily_reports FOR SELECT USING (auth.role() = 'authenticated');
CREATE POLICY "authenticated users can insert" ON public.daily_reports FOR INSERT WITH CHECK (auth.role() = 'authenticated');

-- ============================================================
-- 6. app_logs (앱 이벤트 및 오류 로그) 테이블 생성
-- ============================================================
CREATE TABLE public.app_logs (
  id          BIGSERIAL PRIMARY KEY,
  created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  user_id     UUID REFERENCES auth.users(id) ON DELETE SET NULL,
  level       TEXT NOT NULL DEFAULT 'INFO', -- 'INFO' | 'WARNING' | 'ERROR'
  event       TEXT NOT NULL,
  message     TEXT NOT NULL DEFAULT '',
  extra       JSONB NOT NULL DEFAULT '{}'
);

CREATE INDEX app_logs_created_at_idx ON public.app_logs (created_at DESC);
CREATE INDEX app_logs_user_id_idx ON public.app_logs (user_id);

ALTER TABLE public.app_logs ENABLE ROW LEVEL SECURITY;
CREATE POLICY "app_logs_insert_all" ON public.app_logs FOR INSERT WITH CHECK (true);
CREATE POLICY "app_logs_select_own" ON public.app_logs FOR SELECT USING (auth.uid() = user_id);
```

---

## 📋 추천 데이터베이스 최종 통합 스키마 (백업용)

향후 데이터베이스를 완전히 초기화하고 처음부터 다시 구축해야 할 경우를 대비해, 모든 테이블 정의와 RLS 정책, 인덱스를 한곳에 완벽히 통합한 권장 스키마입니다:

```sql
-- ============================================================
-- 1. journals (다이어리 작성 이력)
-- ============================================================
CREATE TABLE IF NOT EXISTS public.journals (
  id          BIGSERIAL PRIMARY KEY,
  user_id     UUID REFERENCES auth.users(id) ON DELETE CASCADE NOT NULL DEFAULT auth.uid(),
  created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  tags        TEXT NOT NULL DEFAULT '',
  content     TEXT NOT NULL DEFAULT '',
  ai_feedback TEXT NOT NULL DEFAULT ''
);

CREATE INDEX IF NOT EXISTS journals_user_created_idx ON public.journals (user_id, created_at DESC);
CREATE INDEX IF NOT EXISTS journals_tags_idx ON public.journals USING gin (to_tsvector('simple', tags));

ALTER TABLE public.journals ENABLE ROW LEVEL SECURITY;
CREATE POLICY "own_data_only" ON public.journals FOR ALL USING (auth.uid() = user_id);

-- ============================================================
-- 2. trades (매매 및 배당금 거래 기록)
-- ============================================================
CREATE TABLE IF NOT EXISTS public.trades (
  id              BIGSERIAL PRIMARY KEY,
  user_id         UUID REFERENCES auth.users(id) ON DELETE CASCADE NOT NULL DEFAULT auth.uid(),
  created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  stock_name      TEXT NOT NULL,
  quantity        NUMERIC NOT NULL DEFAULT 0,
  price           NUMERIC NOT NULL DEFAULT 0,
  currency        TEXT NOT NULL DEFAULT 'KRW',
  type            TEXT NOT NULL DEFAULT 'buy', -- 'buy' | 'sell' | 'dividend'
  dividend_amount NUMERIC NOT NULL DEFAULT 0,
  ticker          TEXT NOT NULL DEFAULT ''
);

CREATE INDEX IF NOT EXISTS trades_user_created_idx ON public.trades (user_id, created_at DESC);

ALTER TABLE public.trades ENABLE ROW LEVEL SECURITY;
CREATE POLICY "own_data_only" ON public.trades FOR ALL USING (auth.uid() = user_id);

-- ============================================================
-- 3. krx_tickers (국내 주식 종목명/티커 캐시 테이블)
-- ============================================================
CREATE TABLE IF NOT EXISTS public.krx_tickers (
  name       TEXT PRIMARY KEY,
  ticker     TEXT NOT NULL,
  updated_at TIMESTAMPTZ DEFAULT NOW()
);

ALTER TABLE public.krx_tickers ENABLE ROW LEVEL SECURITY;
CREATE POLICY "krx_tickers_select" ON public.krx_tickers FOR SELECT USING (true);
CREATE POLICY "krx_tickers_upsert" ON public.krx_tickers FOR ALL USING (auth.role() = 'authenticated');

-- ============================================================
-- 4. daily_reports (일일 리포트 게시판)
-- ============================================================
CREATE TABLE IF NOT EXISTS public.daily_reports (
  id           BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  created_at   TIMESTAMPTZ DEFAULT NOW(),
  title        TEXT NOT NULL,
  html_content TEXT NOT NULL,
  uploaded_by  TEXT NOT NULL DEFAULT ''
);

ALTER TABLE public.daily_reports ENABLE ROW LEVEL SECURITY;
CREATE POLICY "authenticated users can read" ON public.daily_reports FOR SELECT USING (auth.role() = 'authenticated');
CREATE POLICY "authenticated users can insert" ON public.daily_reports FOR INSERT WITH CHECK (auth.role() = 'authenticated');

-- ============================================================
-- 5. app_logs (앱 이벤트 및 오류 로그)
-- ============================================================
CREATE TABLE IF NOT EXISTS public.app_logs (
  id          BIGSERIAL PRIMARY KEY,
  created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  user_id     UUID REFERENCES auth.users(id) ON DELETE SET NULL,
  level       TEXT NOT NULL DEFAULT 'INFO', -- 'INFO' | 'WARNING' | 'ERROR'
  event       TEXT NOT NULL,
  message     TEXT NOT NULL DEFAULT '',
  extra       JSONB NOT NULL DEFAULT '{}'
);

CREATE INDEX IF NOT EXISTS app_logs_created_at_idx ON public.app_logs (created_at DESC);
CREATE INDEX IF NOT EXISTS app_logs_user_id_idx ON public.app_logs (user_id);

ALTER TABLE public.app_logs ENABLE ROW LEVEL SECURITY;
CREATE POLICY "app_logs_insert_all" ON public.app_logs FOR INSERT WITH CHECK (true);
CREATE POLICY "app_logs_select_own" ON public.app_logs FOR SELECT USING (auth.uid() = user_id);
```
