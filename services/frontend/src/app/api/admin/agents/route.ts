import { NextRequest, NextResponse } from "next/server";
import pool from "@/lib/db";
import { requireRole } from "@/lib/auth";

export async function GET(req: NextRequest) {
  const user = await requireRole(req, "admin");
  if (user instanceof Response) return user;

  const result = await pool.query(
    `SELECT a.id, a.beckn_id, a.label, a.agent_name->>'en' AS name, a.description,
            a.status, a.pricing_model, a.created_at,
            c.name AS category_name,
            p.organization->>'name' AS company_name,
            COALESCE(s.total_queries, 0)::int AS total_queries
     FROM agents a
     LEFT JOIN categories c ON c.id = a.category_id
     LEFT JOIN providers p ON p.id = a.provider_id
     LEFT JOIN agent_stats s ON s.agent_id = a.id
     ORDER BY a.id`
  );

  return NextResponse.json(result.rows);
}

export async function PUT(req: NextRequest) {
  const user = await requireRole(req, "admin");
  if (user instanceof Response) return user;

  const { id, status } = await req.json();
  if (!id || !status) return NextResponse.json({ error: "ID y status requeridos" }, { status: 400 });

  await pool.query("UPDATE agents SET status = $1, updated_at = NOW() WHERE id = $2", [status, id]);

  return NextResponse.json({ ok: true });
}
