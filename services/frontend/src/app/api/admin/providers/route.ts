import { NextRequest, NextResponse } from "next/server";
import pool from "@/lib/db";
import { requireRole } from "@/lib/auth";

export async function GET(req: NextRequest) {
  const user = await requireRole(req, "admin");
  if (user instanceof Response) return user;

  const result = await pool.query(
    `SELECT p.*, COUNT(u.id)::int AS publisher_count
     FROM providers p
     LEFT JOIN users u ON u.provider_id = p.id AND u.role = 'publisher'
     GROUP BY p.id
     ORDER BY p.id`
  );

  return NextResponse.json(result.rows);
}

export async function PUT(req: NextRequest) {
  const user = await requireRole(req, "admin");
  if (user instanceof Response) return user;

  const { id, status } = await req.json();
  if (!id || !status) return NextResponse.json({ error: "ID y status requeridos" }, { status: 400 });

  await pool.query("UPDATE providers SET status = $1, updated_at = NOW() WHERE id = $2", [status, id]);

  return NextResponse.json({ ok: true });
}
