import { NextRequest, NextResponse } from "next/server";
import { getUser } from "@/lib/auth";
import pool from "@/lib/db";

export async function GET(req: NextRequest) {
  const user = await getUser(req);
  if (!user) {
    return NextResponse.json({ error: "No autenticado" }, { status: 401 });
  }

  // Fetch fresh data from DB (role could have changed)
  const result = await pool.query(
    `SELECT u.id, u.email, u.role, u.subscription_status, u.provider_id,
            p.organization->>'name' AS company_name
     FROM users u
     LEFT JOIN providers p ON p.id = u.provider_id
     WHERE u.id = $1`,
    [user.id]
  );

  if (!result.rows.length) {
    return NextResponse.json({ error: "Usuario no encontrado" }, { status: 404 });
  }

  return NextResponse.json(result.rows[0]);
}
