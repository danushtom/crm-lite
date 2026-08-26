-- Corrects an error in 20260822170000.
--
-- That migration removed the six duplicated facts by dropping them from `leads`. For stage,
-- value, currency, probability and score that was right: they describe a pursuit. `tags` is
-- the exception -- it categorises the *prospect* (FR-LP-09, "Lead tags"), and the copy on
-- `opportunities` was the mirror. The wrong side was dropped, leaving the API declaring a
-- column that no longer existed and lead creation failing with "could not find the 'tags'
-- column of 'leads' in the schema cache".
--
-- No data was lost: the mirror on `opportunities` still holds every tag set, so the values
-- are restored from there before that column is dropped in turn.

ALTER TABLE public.leads ADD COLUMN IF NOT EXISTS tags TEXT[] NOT NULL DEFAULT '{}';

-- Restore from the earliest pursuit per lead: before the split they were all copies of one
-- another, so the oldest is as good as any and is deterministic.
UPDATE public.leads l
SET tags = src.tags
FROM (
  SELECT DISTINCT ON (lead_id) lead_id, tags
  FROM public.opportunities
  ORDER BY lead_id, created_at ASC, id ASC
) AS src
WHERE src.lead_id = l.id
  AND l.tags = '{}'
  AND src.tags <> '{}';

ALTER TABLE public.opportunities DROP COLUMN IF EXISTS tags;

CREATE INDEX IF NOT EXISTS leads_tags_idx ON public.leads USING gin (tags);

COMMENT ON COLUMN public.leads.tags IS
  'Free-form labels categorising the prospect. Owned here; pursuits do not carry their own.';
