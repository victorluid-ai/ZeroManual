-- Mantenimiento — esquema inicial (Supabase / PostgreSQL)
-- Plataforma de mantenimiento preventivo para grupos de restauración

create extension if not exists "pgcrypto";

-- ---------------------------------------------------------------------------
-- Tenant: grupo de restauración
-- ---------------------------------------------------------------------------
create table if not exists public.groups (
  id uuid primary key default gen_random_uuid(),
  name text not null,
  slug text not null unique,
  contact_email text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

-- ---------------------------------------------------------------------------
-- Restaurantes / locales del grupo
-- ---------------------------------------------------------------------------
create table if not exists public.restaurants (
  id uuid primary key default gen_random_uuid(),
  group_id uuid not null references public.groups(id) on delete cascade,
  name text not null,
  code text,
  address text,
  city text,
  timezone text not null default 'Europe/Madrid',
  is_active boolean not null default true,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (group_id, code)
);

create index if not exists idx_restaurants_group on public.restaurants(group_id);

-- ---------------------------------------------------------------------------
-- Catálogo de tipos de máquina (horno, hosper, cámara, etc.)
-- ---------------------------------------------------------------------------
create table if not exists public.equipment_types (
  id uuid primary key default gen_random_uuid(),
  name text not null unique,
  category text not null default 'cocina',
  default_interval_days integer not null default 90
    check (default_interval_days > 0),
  description text,
  created_at timestamptz not null default now()
);

-- ---------------------------------------------------------------------------
-- Equipamiento físico por restaurante
-- ---------------------------------------------------------------------------
create table if not exists public.equipment (
  id uuid primary key default gen_random_uuid(),
  restaurant_id uuid not null references public.restaurants(id) on delete cascade,
  equipment_type_id uuid not null references public.equipment_types(id),
  name text not null,
  brand text,
  model text,
  serial_number text,
  location_note text,
  installed_at date,
  status text not null default 'operativo'
    check (status in ('operativo', 'en_reparacion', 'fuera_servicio', 'retirado')),
  notes text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create index if not exists idx_equipment_restaurant on public.equipment(restaurant_id);
create index if not exists idx_equipment_type on public.equipment(equipment_type_id);
create index if not exists idx_equipment_status on public.equipment(status);

-- ---------------------------------------------------------------------------
-- Planes de mantenimiento preventivo
-- ---------------------------------------------------------------------------
create table if not exists public.maintenance_plans (
  id uuid primary key default gen_random_uuid(),
  equipment_id uuid not null references public.equipment(id) on delete cascade,
  title text not null,
  description text,
  interval_days integer not null check (interval_days > 0),
  lead_time_days integer not null default 7 check (lead_time_days >= 0),
  priority text not null default 'media'
    check (priority in ('baja', 'media', 'alta', 'critica')),
  is_active boolean not null default true,
  last_completed_at date,
  next_due_at date not null,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create index if not exists idx_plans_equipment on public.maintenance_plans(equipment_id);
create index if not exists idx_plans_next_due on public.maintenance_plans(next_due_at)
  where is_active = true;

-- ---------------------------------------------------------------------------
-- Historial de intervenciones
-- ---------------------------------------------------------------------------
create table if not exists public.maintenance_logs (
  id uuid primary key default gen_random_uuid(),
  plan_id uuid not null references public.maintenance_plans(id) on delete cascade,
  equipment_id uuid not null references public.equipment(id) on delete cascade,
  performed_at date not null default current_date,
  performed_by text,
  cost_eur numeric(12, 2),
  notes text,
  result text not null default 'ok'
    check (result in ('ok', 'incidencia', 'reprogramado')),
  created_at timestamptz not null default now()
);

create index if not exists idx_logs_plan on public.maintenance_logs(plan_id);
create index if not exists idx_logs_equipment on public.maintenance_logs(equipment_id);

-- ---------------------------------------------------------------------------
-- Sistema de alarmas
-- ---------------------------------------------------------------------------
create table if not exists public.alarms (
  id uuid primary key default gen_random_uuid(),
  group_id uuid not null references public.groups(id) on delete cascade,
  plan_id uuid references public.maintenance_plans(id) on delete set null,
  equipment_id uuid references public.equipment(id) on delete set null,
  restaurant_id uuid references public.restaurants(id) on delete set null,
  severity text not null default 'aviso'
    check (severity in ('info', 'aviso', 'urgente', 'critica')),
  status text not null default 'abierta'
    check (status in ('abierta', 'reconocida', 'resuelta', 'silenciada')),
  title text not null,
  message text,
  due_at date,
  acknowledged_at timestamptz,
  resolved_at timestamptz,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create index if not exists idx_alarms_group_status on public.alarms(group_id, status);
create index if not exists idx_alarms_severity on public.alarms(severity)
  where status = 'abierta';
create index if not exists idx_alarms_due on public.alarms(due_at)
  where status in ('abierta', 'reconocida');

-- ---------------------------------------------------------------------------
-- updated_at automático
-- ---------------------------------------------------------------------------
create or replace function public.set_updated_at()
returns trigger
language plpgsql
as $$
begin
  new.updated_at = now();
  return new;
end;
$$;

drop trigger if exists trg_groups_updated on public.groups;
create trigger trg_groups_updated
  before update on public.groups
  for each row execute function public.set_updated_at();

drop trigger if exists trg_restaurants_updated on public.restaurants;
create trigger trg_restaurants_updated
  before update on public.restaurants
  for each row execute function public.set_updated_at();

drop trigger if exists trg_equipment_updated on public.equipment;
create trigger trg_equipment_updated
  before update on public.equipment
  for each row execute function public.set_updated_at();

drop trigger if exists trg_plans_updated on public.maintenance_plans;
create trigger trg_plans_updated
  before update on public.maintenance_plans
  for each row execute function public.set_updated_at();

drop trigger if exists trg_alarms_updated on public.alarms;
create trigger trg_alarms_updated
  before update on public.alarms
  for each row execute function public.set_updated_at();

-- ---------------------------------------------------------------------------
-- Vista operativa: próximos mantenimientos + estado de alarma
-- ---------------------------------------------------------------------------
create or replace view public.v_upcoming_maintenance as
select
  p.id as plan_id,
  p.title as plan_title,
  p.priority,
  p.interval_days,
  p.lead_time_days,
  p.next_due_at,
  p.last_completed_at,
  (p.next_due_at - current_date) as days_until_due,
  case
    when p.next_due_at < current_date then 'vencido'
    when p.next_due_at <= current_date + p.lead_time_days then 'proximo'
    else 'ok'
  end as urgency,
  e.id as equipment_id,
  e.name as equipment_name,
  e.brand,
  e.model,
  e.status as equipment_status,
  et.name as equipment_type,
  r.id as restaurant_id,
  r.name as restaurant_name,
  r.city,
  g.id as group_id,
  g.name as group_name
from public.maintenance_plans p
join public.equipment e on e.id = p.equipment_id
join public.equipment_types et on et.id = e.equipment_type_id
join public.restaurants r on r.id = e.restaurant_id
join public.groups g on g.id = r.group_id
where p.is_active = true
  and e.status <> 'retirado'
  and r.is_active = true;

-- ---------------------------------------------------------------------------
-- Función: regenerar alarmas a partir de planes vencidos / próximos
-- ---------------------------------------------------------------------------
create or replace function public.refresh_maintenance_alarms(p_group_id uuid default null)
returns integer
language plpgsql
as $$
declare
  v_count integer := 0;
  rec record;
  v_severity text;
  v_title text;
begin
  for rec in
    select * from public.v_upcoming_maintenance
    where urgency in ('vencido', 'proximo')
      and (p_group_id is null or group_id = p_group_id)
  loop
    v_severity := case
      when rec.urgency = 'vencido' and rec.priority in ('alta', 'critica') then 'critica'
      when rec.urgency = 'vencido' then 'urgente'
      when rec.priority = 'critica' then 'urgente'
      else 'aviso'
    end;

    v_title := case
      when rec.urgency = 'vencido' then
        'Mantenimiento vencido: ' || rec.equipment_name
      else
        'Mantenimiento próximo: ' || rec.equipment_name
    end;

    -- Evitar duplicados abiertos del mismo plan
    if not exists (
      select 1 from public.alarms a
      where a.plan_id = rec.plan_id
        and a.status in ('abierta', 'reconocida')
    ) then
      insert into public.alarms (
        group_id, plan_id, equipment_id, restaurant_id,
        severity, title, message, due_at
      ) values (
        rec.group_id,
        rec.plan_id,
        rec.equipment_id,
        rec.restaurant_id,
        v_severity,
        v_title,
        format(
          '%s en %s — %s (vence %s)',
          rec.plan_title,
          rec.restaurant_name,
          rec.equipment_type,
          rec.next_due_at
        ),
        rec.next_due_at
      );
      v_count := v_count + 1;
    end if;
  end loop;

  return v_count;
end;
$$;

-- ---------------------------------------------------------------------------
-- RLS (listo para auth multi-tenant; service role bypasea)
-- ---------------------------------------------------------------------------
alter table public.groups enable row level security;
alter table public.restaurants enable row level security;
alter table public.equipment_types enable row level security;
alter table public.equipment enable row level security;
alter table public.maintenance_plans enable row level security;
alter table public.maintenance_logs enable row level security;
alter table public.alarms enable row level security;

-- Políticas de lectura/escritura para rol autenticado (ajuste fino con auth.uid() después)
create policy "authenticated_all_groups" on public.groups
  for all to authenticated using (true) with check (true);

create policy "authenticated_all_restaurants" on public.restaurants
  for all to authenticated using (true) with check (true);

create policy "authenticated_all_equipment_types" on public.equipment_types
  for all to authenticated using (true) with check (true);

create policy "authenticated_all_equipment" on public.equipment
  for all to authenticated using (true) with check (true);

create policy "authenticated_all_plans" on public.maintenance_plans
  for all to authenticated using (true) with check (true);

create policy "authenticated_all_logs" on public.maintenance_logs
  for all to authenticated using (true) with check (true);

create policy "authenticated_all_alarms" on public.alarms
  for all to authenticated using (true) with check (true);

-- service_role ya tiene acceso total por defecto en Supabase
