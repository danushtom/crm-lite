-- Voice agents become configurable by the people who actually run the calls.
--
-- Until now an agent was a free-text `system_prompt`: an admin wrote raw LLM instructions into
-- a textarea and hoped. Two problems with that, and this migration addresses both.
--
-- 1. THE SCRIPT IS NOW STRUCTURED DATA (`script` jsonb), not prose. Goal, opening, talking
--    points, questions, objection handling, must/never rules, closing, tone. `system_prompt`
--    stays, but becomes the *compiled output* of that structure -- generated server-side by
--    dracara_ai.voice_script.compile_prompt(), never written by a client again. The compiler
--    appends the non-negotiable guardrails after the client's own words, so no amount of
--    creative scripting can remove "don't invent prices" or "don't promise delivery dates".
--
-- 2. THE AGENT ONLY SEES WHAT THE ORGANIZATION SHARES (`data_access` jsonb): which mid-call
--    tools it may call, and which lead fields it may be told. Enforced in three places, because
--    a tool call can arrive whether or not we declared the tool: the declarations sent to the
--    platform, the dispatcher in app/services/voice_tools.py, and the field filter inside
--    get_lead_context. The dispatcher check is the one that matters -- see that module.
--
-- Plus the persona an organization's customers actually hear: the name the agent gives on the
-- phone, its job title, and an avatar, so a roster of agents reads as a team rather than a list
-- of prompt blobs.

-- ---------------------------------------------------------------------------
-- 1. Persona.
-- ---------------------------------------------------------------------------
ALTER TABLE public.voice_agents
  -- The name the agent says on the call ("this is Maya"). Distinct from `name`, which is the
  -- internal label in the CRM ("Inbound receptionist"). They are usually not the same thing.
  ADD COLUMN IF NOT EXISTS persona_name TEXT,
  ADD COLUMN IF NOT EXISTS role_title TEXT,
  -- One of a fixed set of illustrated avatars rendered client-side (no uploads, no storage).
  ADD COLUMN IF NOT EXISTS avatar_key TEXT;

-- ---------------------------------------------------------------------------
-- 2. The script, and the data it may use.
-- ---------------------------------------------------------------------------
ALTER TABLE public.voice_agents
  ADD COLUMN IF NOT EXISTS script JSONB NOT NULL DEFAULT '{}'::jsonb,
  ADD COLUMN IF NOT EXISTS data_access JSONB NOT NULL DEFAULT '{}'::jsonb;

COMMENT ON COLUMN public.voice_agents.script IS
  'Structured call script (goal, opening, talking points, questions, objections, rules, closing, tone). The source of truth; system_prompt is compiled from it.';
COMMENT ON COLUMN public.voice_agents.system_prompt IS
  'Compiled from `script` by dracara_ai.voice_script.compile_prompt(). Server-generated -- not client-writable.';
COMMENT ON COLUMN public.voice_agents.data_access IS
  'What this agent may use mid-call: {"tools": {name: bool}, "lead_fields": [...]}. Enforced in app/services/voice_tools.py, not just in the tool declarations.';

-- ---------------------------------------------------------------------------
-- 3. Backfill. Existing agents keep behaving exactly as they do today: their hand-written
-- prompt moves into the script's free-text "extra" section, which the compiler emits verbatim.
-- system_prompt is left untouched here; the next save through the API recompiles it.
-- ---------------------------------------------------------------------------
UPDATE public.voice_agents
SET script = jsonb_build_object(
      'goal', 'custom',
      'tone', 'warm',
      'extra', system_prompt
    ),
    -- Everything on, matching what these agents could already do before the policy existed:
    -- a migration must not quietly take capability away from a working agent.
    data_access = jsonb_build_object(
      'tools', jsonb_build_object(
        'check_consent', TRUE,
        'get_lead_context', TRUE,
        'search_knowledge_base', TRUE,
        'log_call_outcome', TRUE,
        'update_deal_stage', TRUE,
        'book_appointment', TRUE
      ),
      'lead_fields', jsonb_build_array(
        'company_name', 'project_type', 'stage', 'tags', 'next_followup_date',
        'budget_range', 'timeline', 'pain_points', 'decision_makers', 'notes'
      )
    )
WHERE script = '{}'::jsonb;

-- ---------------------------------------------------------------------------
-- 4. Call → script linkage. "What was this agent told when it said that?" is the first
-- question anyone asks about a bad call, and the script changes over time, so the answer has to
-- be captured at dial time rather than inferred from the agent's current configuration.
-- ---------------------------------------------------------------------------
ALTER TABLE public.calls
  ADD COLUMN IF NOT EXISTS script_snapshot JSONB;

COMMENT ON COLUMN public.calls.script_snapshot IS
  'The agent''s script and data-access policy as they were when this call was placed. Write-once at dial time.';
