-- ==========================================================
-- AI 주식 다이어리 — Supabase 테이블 설정
-- ==========================================================
-- 사용 방법:
--   1. Supabase 대시보드 → 왼쪽 메뉴 "SQL Editor" 클릭
--   2. "New query" 버튼 클릭
--   3. 아래 내용 전체를 복사해서 붙여넣기
--   4. 오른쪽 아래 "Run" 버튼 클릭
-- ==========================================================

-- 1. journals 테이블 생성
create table if not exists journals (
  id bigserial primary key,
  user_id uuid references auth.users(id) on delete cascade not null default auth.uid(),
  created_at timestamptz default now(),
  tags text default '',
  content text default '',
  ai_feedback text default ''
);

-- 2. 인덱스 추가 (조회 속도 향상)
create index if not exists journals_user_created_idx
  on journals (user_id, created_at desc);

create index if not exists journals_tags_idx
  on journals using gin (to_tsvector('simple', tags));

-- 3. Row Level Security 활성화 (사용자별 데이터 격리)
alter table journals enable row level security;

-- 4. 정책: 자기 일기만 조회 가능
drop policy if exists "Users can view own journals" on journals;
create policy "Users can view own journals"
  on journals for select
  to authenticated
  using (auth.uid() = user_id);

-- 5. 정책: 자기 user_id로만 삽입 가능
drop policy if exists "Users can insert own journals" on journals;
create policy "Users can insert own journals"
  on journals for insert
  to authenticated
  with check (auth.uid() = user_id);

-- 6. 정책: 자기 일기만 수정 가능
drop policy if exists "Users can update own journals" on journals;
create policy "Users can update own journals"
  on journals for update
  to authenticated
  using (auth.uid() = user_id)
  with check (auth.uid() = user_id);

-- 7. 정책: 자기 일기만 삭제 가능
drop policy if exists "Users can delete own journals" on journals;
create policy "Users can delete own journals"
  on journals for delete
  to authenticated
  using (auth.uid() = user_id);

-- ==========================================================
-- 2. trades 테이블 생성 (보물함 재고)
-- ==========================================================
create table if not exists trades (
  id bigserial primary key,
  user_id uuid references auth.users(id) on delete cascade not null default auth.uid(),
  created_at timestamptz default now(),
  stock_name text not null,
  quantity float not null default 0,
  price float not null default 0,
  currency text not null default 'KRW',
  type text not null default 'buy'  -- 'buy' | 'sell' | 'dividend'
);

-- 기존 trades 행에 type 컬럼이 없으면 backfill
alter table trades add column if not exists type text not null default 'buy';
update trades set type = 'buy' where type is null;

create index if not exists trades_user_created_idx
  on trades (user_id, created_at desc);

alter table trades enable row level security;

drop policy if exists "Users can view own trades" on trades;
create policy "Users can view own trades"
  on trades for select to authenticated using (auth.uid() = user_id);

drop policy if exists "Users can insert own trades" on trades;
create policy "Users can insert own trades"
  on trades for insert to authenticated with check (auth.uid() = user_id);

drop policy if exists "Users can delete own trades" on trades;
create policy "Users can delete own trades"
  on trades for delete to authenticated using (auth.uid() = user_id);

-- ==========================================================
-- 완료! 이제 앱에서 정상 작동합니다.
-- ==========================================================
