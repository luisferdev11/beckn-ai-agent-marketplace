import { NextRequest, NextResponse } from "next/server";
import pool from "@/lib/db";

export async function POST(req: NextRequest) {
  const { email } = await req.json();
  if (!email) return NextResponse.json({ error: "Email requerido" }, { status: 400 });

  const result = await pool.query("SELECT id FROM users WHERE email = $1", [email]);
  return NextResponse.json({ exists: result.rows.length > 0 });
}
