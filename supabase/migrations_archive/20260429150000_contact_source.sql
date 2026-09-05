-- Add source column to contacts table
ALTER TABLE public.contacts ADD COLUMN source public.lead_source;
