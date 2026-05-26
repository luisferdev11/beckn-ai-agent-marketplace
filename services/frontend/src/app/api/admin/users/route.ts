import { NextRequest, NextResponse } from "next/server";
import pool from "@/lib/db";
import { requireRole } from "@/lib/auth";

export async function GET(req: NextRequest) {
  const user = await requireRole(req, "admin");
  if (user instanceof Response) return user;

  const result = await pool.query(
    `SELECT u.id, u.email, u.role, u.subscription_status, u.provider_id, u.created_at,
            p.organization->>'name' AS company_name
     FROM users u
     LEFT JOIN providers p ON p.id = u.provider_id
     ORDER BY u.created_at DESC`
  );

  return NextResponse.json(result.rows);
}

export async function PUT(req: NextRequest) {
  const user = await requireRole(req, "admin");
  if (user instanceof Response) return user;

  const { id, role, subscription_status } = await req.json();
  if (!id) return NextResponse.json({ error: "ID requerido" }, { status: 400 });

  const sets: string[] = [];
  const vals: unknown[] = [];
  let idx = 1;

  if (role) {
    sets.push(`role = $${idx++}`);
    vals.push(role);
  }
  if (subscription_status) {
    sets.push(`subscription_status = $${idx++}`);
    vals.push(subscription_status);
  }

  if (!sets.length) return NextResponse.json({ error: "Nada que actualizar" }, { status: 400 });

  sets.push(`updated_at = NOW()`);
  vals.push(id);

  await pool.query(`UPDATE users SET ${sets.join(", ")} WHERE id = $${idx}`, vals);

  return NextResponse.json({ ok: true });
}
