-- A real monthly trend, to replace a fabricated one.
--
-- The dashboard drew a six-month "revenue" chart from a formula over pipeline_total:
--
--     base * (0.65 + i * 0.06) + (i % 3) * base * 0.08
--
-- It moved when the pipeline moved, so it looked plausible, but it described nothing that had
-- happened. This returns what actually did: value won and value opened, per month.
--
-- "Won when" comes from the audit log where possible -- it records the stage transition and
-- its timestamp -- and falls back to updated_at for opportunities won before auditing existed.

CREATE OR REPLACE FUNCTION public.pipeline_trend(months INTEGER DEFAULT 6)
RETURNS jsonb
LANGUAGE plpgsql
STABLE
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
  uid uuid := auth.uid();
  adm boolean := public.is_admin(uid);
  span INTEGER := GREATEST(1, LEAST(months, 24));
  result jsonb;
BEGIN
  IF uid IS NULL THEN
    RAISE EXCEPTION 'not authenticated';
  END IF;

  WITH bounds AS (
    SELECT date_trunc('month', NOW()) - ((span - 1) || ' months')::INTERVAL AS first_month
  ),
  buckets AS (
    SELECT generate_series(
             (SELECT first_month FROM bounds),
             date_trunc('month', NOW()),
             '1 month'::INTERVAL
           ) AS month
  ),
  visible AS (
    SELECT o.*
    FROM public.opportunities o
    JOIN public.leads l ON l.id = o.lead_id
    WHERE o.deleted_at IS NULL
      AND l.deleted_at IS NULL
      AND (adm OR l.owner_id = uid)
  ),
  won AS (
    SELECT
      date_trunc(
        'month',
        COALESCE(
          (
            SELECT MAX(a.occurred_at)
            FROM public.audit_log a
            WHERE a.table_name = 'opportunities'
              AND a.record_id = v.id
              AND a.new_values ->> 'stage' = 'won'
          ),
          v.updated_at
        )
      ) AS month,
      COALESCE(v.quoted_value, 0) AS value
    FROM visible v
    WHERE v.stage = 'won'::public.lead_stage
  ),
  opened AS (
    SELECT date_trunc('month', v.created_at) AS month,
           COALESCE(v.quoted_value, 0) AS value
    FROM visible v
  )
  SELECT jsonb_agg(
           jsonb_build_object(
             'month', to_char(b.month, 'YYYY-MM'),
             'label', to_char(b.month, 'Mon'),
             'won_value', COALESCE(w.total, 0),
             'won_count', COALESCE(w.n, 0),
             'opened_value', COALESCE(o.total, 0),
             'opened_count', COALESCE(o.n, 0)
           )
           ORDER BY b.month
         )
    INTO result
  FROM buckets b
  LEFT JOIN (
    SELECT month, SUM(value)::numeric AS total, COUNT(*)::int AS n FROM won GROUP BY month
  ) w ON w.month = b.month
  LEFT JOIN (
    SELECT month, SUM(value)::numeric AS total, COUNT(*)::int AS n FROM opened GROUP BY month
  ) o ON o.month = b.month;

  RETURN COALESCE(result, '[]'::jsonb);
END;
$$;

GRANT EXECUTE ON FUNCTION public.pipeline_trend(INTEGER) TO authenticated;

COMMENT ON FUNCTION public.pipeline_trend IS
  'Monthly won and opened value, scoped by RLS. Replaces a chart that was generated from a '
  'formula over the current pipeline total and described nothing that had happened.';
