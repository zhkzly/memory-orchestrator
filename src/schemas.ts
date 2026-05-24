import { z } from "zod";

export const provenanceSchema = z.object({
  type: z.enum(["prompt", "file", "diff", "correction", "session"]),
  ref: z.string()
});

export const memoryItemSchema = z.object({
  id: z.string(),
  kind: z.enum(["personal", "project", "evidence", "session"]),
  scope: z.string(),
  source: z.string(),
  confidence: z.number(),
  confidence_rationale: z.string().optional(),
  status: z.enum(["candidate", "verified", "rejected", "outdated"]),
  content: z.string(),
  created_at: z.string(),
  updated_at: z.string(),
  verified_at: z.string().optional(),
  source_content_hash: z.string().optional(),
  retrieval_count: z.number().optional(),
  last_retrieved_at: z.string().optional(),
  cross_project_applicable: z.boolean().optional(),
  references: z.array(z.string()).optional(),
  expires_at: z.string().optional(),
  semantic_tags: z.array(z.string()).optional(),
  provenance: z.array(provenanceSchema)
});

export const rubricProxySchema = z.object({
  id: z.string(),
  criterion: z.string(),
  target: z.string(),
  evidence: z.array(
    z.object({
      ref: z.string(),
      type: z.enum(["file", "prompt", "diff", "test", "session"])
    })
  ),
  score: z.number()
});
