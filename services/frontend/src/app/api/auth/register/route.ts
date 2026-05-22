import { NextRequest, NextResponse } from "next/server";
import pool from "@/lib/db";
import { hashPassword, signToken, type Role } from "@/lib/auth";

export async function POST(req: NextRequest) {
  const body = await req.json();
  const { email, password, role, provider_id, new_provider, integration_mode } = body as {
    email?: string;
    password?: string;
    role?: Role;
    provider_id?: number | null;
    new_provider?: { subscriber_id: string; bpp_uri: string; organization: Record<string, string> };
    integration_mode?: string;
  };

  if (!email || !password) {
    return NextResponse.json({ error: "Email y contraseña requeridos" }, { status: 400 });
  }

  const validRoles: Role[] = ["consumer", "publisher"];
  const userRole = validRoles.includes(role as Role) ? (role as Role) : "consumer";

  // Check duplicate email
  const existing = await pool.query("SELECT id FROM users WHERE email = $1", [email]);
  if (existing.rows.length) {
    return NextResponse.json({ error: "Email ya registrado" }, { status: 409 });
  }

  let finalProviderId: number | null = provider_id ?? null;

  // If publisher selected "create new company"
  if (userRole === "publisher" && new_provider) {
    const mode = integration_mode === "external" ? "external" : "managed";
    const res = await pool.query(
      `INSERT INTO providers (subscriber_id, bpp_uri, organization, integration_mode)
       VALUES ($1, $2, $3, $4) RETURNING id`,
      [new_provider.subscriber_id, new_provider.bpp_uri, JSON.stringify(new_provider.organization), mode]
    );
    finalProviderId = res.rows[0].id;
  }

  const password_hash = await hashPassword(password);
  const subscriptionStatus = userRole === "publisher" ? "active" : "free";

  const result = await pool.query(
    `INSERT INTO users (email, password_hash, role, subscription_status, provider_id)
     VALUES ($1, $2, $3, $4, $5) RETURNING id, email, role, subscription_status, provider_id`,
    [email, password_hash, userRole, subscriptionStatus, finalProviderId]
  );

  const user = result.rows[0];
  const token = await signToken({
    id: user.id,
    email: user.email,
    role: user.role,
    subscription_status: user.subscription_status,
    provider_id: user.provider_id,
  });

  const response = NextResponse.json({ user, token });
  response.cookies.set("token", token, {
    httpOnly: true,
    secure: process.env.NODE_ENV === "production",
    sameSite: "lax",
    maxAge: 60 * 60 * 24,
    path: "/",
  });

  return response;
}
