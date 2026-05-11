import { NextRequest, NextResponse } from "next/server";
import pool from "@/lib/db";
import { requireRole } from "@/lib/auth";

export async function GET(req: NextRequest) {
  const user = await requireRole(req, "publisher", "admin");
  if (user instanceof Response) return user;

  const result = await pool.query(
    `SELECT s.agent_id, a.label, a.agent_name->>'en' AS name,
            s.total_queries, s.unique_users, s.week_queries, s.last_used_at
     FROM agent_stats s
     JOIN agents a ON a.id = s.agent_id
     WHERE a.provider_id = $1
     ORDER BY s.total_queries DESC`,
    [user.provider_id]
  );

  return NextResponse.json(result.rows);
}
