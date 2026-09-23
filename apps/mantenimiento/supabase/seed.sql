-- Semilla demo: grupo gastronómico con hornos, Hesper y cámaras
-- Ejecutar en SQL Editor de Supabase DESPUÉS de 001_initial_schema.sql

insert into public.groups (id, name, slug, contact_email)
values (
  'a1111111-1111-1111-1111-111111111111',
  'Grupo Sabores Atlánticos',
  'sabores-atlanticos',
  'ops@saboresatlanticos.es'
)
on conflict (slug) do nothing;

insert into public.equipment_types (id, name, category, default_interval_days, description) values
  ('b1111111-1111-1111-1111-111111111111', 'Horno convencional', 'cocina', 90, 'Revisión de resistencias, sellos y termostato'),
  ('b2222222-2222-2222-2222-222222222222', 'Horno Josper / carbón', 'cocina', 30, 'Limpieza de cenizas, rejillas, tiro y cámara de combustión'),
  ('b3333333-3333-3333-3333-333333333333', 'Horno mixto / combi', 'cocina', 60, 'Descalcificación, sondas, juntas y sistema de vapor'),
  ('b4444444-4444-4444-4444-444444444444', 'Cámara frigorífica', 'frio', 120, 'Compresor, juntas de puerta, sonda de temperatura'),
  ('b5555555-5555-5555-5555-555555555555', 'Lavavajillas industrial', 'office', 45, 'Filtros, boquillas, descalcificación y vaciado'),
  ('b6666666-6666-6666-6666-666666666666', 'Campana extractora', 'ventilacion', 90, 'Filtros metálicos, motor y conductos')
on conflict (name) do nothing;

insert into public.restaurants (id, group_id, name, code, address, city) values
  (
    'c1111111-1111-1111-1111-111111111111',
    'a1111111-1111-1111-1111-111111111111',
    'Mar Brava',
    'MB-01',
    'Paseo Marítimo 12',
    'A Coruña'
  ),
  (
    'c2222222-2222-2222-2222-222222222222',
    'a1111111-1111-1111-1111-111111111111',
    'Asador do Porto',
    'AP-02',
    'Rúa do Porto 8',
    'Vigo'
  ),
  (
    'c3333333-3333-3333-3333-333333333333',
    'a1111111-1111-1111-1111-111111111111',
    'Casa da Brasa',
    'CB-03',
    'Av. da Liberdade 45',
    'Santiago de Compostela'
  )
on conflict do nothing;

insert into public.equipment (id, restaurant_id, equipment_type_id, name, brand, model, serial_number, location_note, installed_at, status) values
  (
    'd1111111-1111-1111-1111-111111111111',
    'c1111111-1111-1111-1111-111111111111',
    'b2222222-2222-2222-2222-222222222222',
    'Josper principal',
    'Josper',
    'HJX-25',
    'JSP-2019-8841',
    'Línea caliente — estación parrilla',
    '2019-03-15',
    'operativo'
  ),
  (
    'd2222222-2222-2222-2222-222222222222',
    'c1111111-1111-1111-1111-111111111111',
    'b3333333-3333-3333-3333-333333333333',
    'Horno combi 1',
    'Rational',
    'iCombi Pro 10-1/1',
    'RAT-2021-1022',
    'Pastelería / regenerado',
    '2021-06-01',
    'operativo'
  ),
  (
    'd3333333-3333-3333-3333-333333333333',
    'c2222222-2222-2222-2222-222222222222',
    'b2222222-2222-2222-2222-222222222222',
    'Josper asador',
    'Josper',
    'HJX-50',
    'JSP-2018-4410',
    'Sala de brasas',
    '2018-11-20',
    'operativo'
  ),
  (
    'd4444444-4444-4444-4444-444444444444',
    'c2222222-2222-2222-2222-222222222222',
    'b4444444-4444-4444-4444-444444444444',
    'Cámara positiva',
    'ColdKit',
    'CP-240',
    'CK-2020-778',
    'Office frío',
    '2020-01-10',
    'operativo'
  ),
  (
    'd5555555-5555-5555-5555-555555555555',
    'c3333333-3333-3333-3333-333333333333',
    'b1111111-1111-1111-1111-111111111111',
    'Horno pizza',
    'Moretti Forni',
    'P120E',
    'MF-2022-331',
    'Estación pizza',
    '2022-04-08',
    'operativo'
  ),
  (
    'd6666666-6666-6666-6666-666666666666',
    'c3333333-3333-3333-3333-333333333333',
    'b5555555-5555-5555-5555-555555555555',
    'Lavavajillas cinta',
    'Winterhalter',
    'MT 2040',
    'WH-2021-990',
    'Office lavado',
    '2021-09-12',
    'en_reparacion'
  )
on conflict do nothing;

insert into public.maintenance_plans (
  id, equipment_id, title, description, interval_days, lead_time_days,
  priority, last_completed_at, next_due_at
) values
  (
    'e1111111-1111-1111-1111-111111111111',
    'd1111111-1111-1111-1111-111111111111',
    'Limpieza profunda Josper',
    'Vaciar cenizas, revisar rejillas, limpiar tiro y comprobar estanqueidad',
    30, 5, 'critica',
    current_date - 35,
    current_date - 5
  ),
  (
    'e2222222-2222-2222-2222-222222222222',
    'd2222222-2222-2222-2222-222222222222',
    'Descalcificación combi',
    'Ciclo Care, revisión de juntas y sonda de núcleo',
    60, 7, 'alta',
    current_date - 50,
    current_date + 10
  ),
  (
    'e3333333-3333-3333-3333-333333333333',
    'd3333333-3333-3333-3333-333333333333',
    'Revisión mensual Josper',
    'Inspección de cámara, ventilación y elementos de seguridad',
    30, 5, 'critica',
    current_date - 28,
    current_date + 2
  ),
  (
    'e4444444-4444-4444-4444-444444444444',
    'd4444444-4444-4444-4444-444444444444',
    'Revisión frigorífica',
    'Comprobar temperaturas, juntas y condensador',
    120, 14, 'media',
    current_date - 90,
    current_date + 30
  ),
  (
    'e5555555-5555-5555-5555-555555555555',
    'd5555555-5555-5555-5555-555555555555',
    'Calibración termostato',
    'Verificar temperatura de cámara y elementos calefactores',
    90, 10, 'media',
    current_date - 100,
    current_date - 10
  ),
  (
    'e6666666-6666-6666-6666-666666666666',
    'd6666666-6666-6666-6666-666666666666',
    'Mantenimiento lavavajillas',
    'Filtros, boquillas, descalcificación y revisión de bomba',
    45, 7, 'alta',
    current_date - 40,
    current_date + 5
  )
on conflict do nothing;

-- Generar alarmas iniciales
select public.refresh_maintenance_alarms('a1111111-1111-1111-1111-111111111111');
