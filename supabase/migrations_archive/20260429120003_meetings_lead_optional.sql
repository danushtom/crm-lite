-- Allow calendar-synced meetings without a CRM lead (Google events)
ALTER TABLE public.meetings ALTER COLUMN lead_id DROP NOT NULL;
