import { NextRequest, NextResponse } from "next/server";
import pool from "@/lib/db";
import { metricsPool } from "@/lib/db";
import { requireRole } from "@/lib/auth";

export async function GET(req: NextRequest) {
  const user = await requireRole(req, "publisher", "admin");
  if (user instanceof Response) return user;

  // Get agents belonging to this publisher (catalog DB)
  const agentsResult = await pool.query(
    `SELECT id, label, agent_name->>'en' AS name
     FROM agents WHERE provider_id = $1`,
    [user.provider_id]
  );

  if (agentsResult.rows.length === 0) {
    return NextResponse.json([]);
  }

  const agentIds = agentsResult.rows.map((a: { id: number }) => a.id);
  const agentMap = new Map(agentsResult.rows.map((a: { id: number; label: string; name: string }) => [a.id, a]));

  // Get stats for those agents (metrics DB)
  const statsResult = await metricsPool.query(
    `SELECT agent_id, total_queries, unique_users, week_queries, last_used_at
     FROM agent_stats
     WHERE agent_id = ANY($1)
     ORDER BY total_queries DESC`,
    [agentIds]
  );

  // Merge results
  const merged = statsResult.rows.map((s: { agent_id: number; total_queries: number; unique_users: number; week_queries: number; last_used_at: string }) => ({
    ...s,
    label: agentMap.get(s.agent_id)?.label,
    name: agentMap.get(s.agent_id)?.name,
  }));

  return NextResponse.json(merged);
}
