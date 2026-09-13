-- Phase 21: scene-scoped episodic memory (grill decision #7).
-- Additive: older rows keep NULL and always surface in retrieval.

ALTER TABLE agent_memories ADD COLUMN location TEXT;
