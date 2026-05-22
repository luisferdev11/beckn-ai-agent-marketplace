import { NextRequest, NextResponse } from "next/server";
import pool from "@/lib/db";
import { verifyPassword, signToken } from "@/lib/auth";

export async function POST(req: NextRequest) {
  const { email, password } = await req.json();

  if (!email || !password) {
    return NextResponse.json({ error: "Credenciales requeridas" }, { status: 400 });
  }

  const result = await pool.query(
    "SELECT id, email, password_hash, role, subscription_status, provider_id FROM users WHERE email = $1",
    [email]
  );

  if (!result.rows.length) {
    return NextResponse.json({ error: "Credenciales inválidas" }, { status: 401 });
  }

  const user = result.rows[0];
  const valid = await verifyPassword(password, user.password_hash);
  if (!valid) {
    return NextResponse.json({ error: "Credenciales inválidas" }, { status: 401 });
  }

  const token = await signToken({
    id: user.id,
    email: user.email,
    role: user.role,
    subscription_status: user.subscription_status,
    provider_id: user.provider_id,
  });

  const response = NextResponse.json({
    user: {
      id: user.id,
      email: user.email,
      role: user.role,
      subscription_status: user.subscription_status,
      provider_id: user.provider_id,
    },
    token,
  });

  response.cookies.set("token", token, {
    httpOnly: true,
    secure: process.env.NODE_ENV === "production",
    sameSite: "lax",
    maxAge: 60 * 60 * 24,
    path: "/",
  });

  return response;
}
