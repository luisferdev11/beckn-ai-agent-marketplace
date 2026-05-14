import { NextRequest, NextResponse } from "next/server";
import pool from "@/lib/db";
import { requireRole } from "@/lib/auth";
import crypto from "crypto";

export async function GET(req: NextRequest) {
  const user = await requireRole(req, "publisher", "admin");
  if (user instanceof Response) return user;

  const result = await pool.query(
    `SELECT a.id, a.beckn_id, a.label,
            COALESCE(a.agent_name->>'en', a.agent_name #>> '{}') AS agent_name,
            a.description, a.status,
            a.pricing_model, a.category_id, a.created_at, a.access_point_url,
            c.name AS category_name,
            COALESCE(s.total_queries, 0) AS total_queries,
            s.last_used_at
     FROM agents a
     LEFT JOIN categories c ON c.id = a.category_id
     LEFT JOIN agent_stats s ON s.agent_id = a.id
     WHERE a.provider_id = $1
     ORDER BY a.id`,
    [user.provider_id]
  );

  return NextResponse.json(result.rows);
}

export async function POST(req: NextRequest) {
  const user = await requireRole(req, "publisher", "admin");
  if (user instanceof Response) return user;

  if (!user.provider_id) {
    return NextResponse.json({ error: "No tienes compañía vinculada" }, { status: 400 });
  }

  const body = await req.json();
  const {
    agent_name, description, category_id, pricing_model,
    access_point_url, status,
  } = body;

  if (!agent_name || !category_id) {
    return NextResponse.json({ error: "Nombre y categoría requeridos" }, { status: 400 });
  }

  if (!access_point_url) {
    return NextResponse.json({ error: "Endpoint URL requerido" }, { status: 400 });
  }

  // Auto-generate beckn_id from agent name
  const slug = agent_name
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-|-$/g, "")
    .slice(0, 30);
  const suffix = crypto.randomBytes(3).toString("hex");
  const beckn_id = `agent-${slug}-${suffix}`;

  try {
    const result = await pool.query(
      `INSERT INTO agents (
         provider_id, category_id, agent_name, label, beckn_id,
         description, pricing_model, access_point_url, status
       )
       VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
       RETURNING id, beckn_id, label, description, status, created_at`,
      [
        user.provider_id,
        category_id,
        JSON.stringify(agent_name),
        agent_name,
        beckn_id,
        description || "",
        JSON.stringify(pricing_model || {}),
        access_point_url,
        status || "active",
      ]
    );

    // Create initial stats row
    await pool.query("INSERT INTO agent_stats (agent_id) VALUES ($1)", [result.rows[0].id]);

    return NextResponse.json(result.rows[0], { status: 201 });
  } catch (err: unknown) {
    const message = err instanceof Error ? err.message : "Database error";
    console.error("POST /api/publisher/agents failed:", message);
    return NextResponse.json({ error: message }, { status: 500 });
  }
}
