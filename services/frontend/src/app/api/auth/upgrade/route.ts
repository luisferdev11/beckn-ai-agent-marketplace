import { NextRequest, NextResponse } from "next/server";
import pool from "@/lib/db";
import { requireAuth, signToken } from "@/lib/auth";

export async function POST(req: NextRequest) {
  const user = await requireAuth(req);
  if (user instanceof Response) return user;

  const { provider_id, new_provider, integration_mode } = await req.json();

  let finalProviderId: number | null = provider_id ?? null;

  if (new_provider) {
    const mode = integration_mode === "external" ? "external" : "managed";
    const res = await pool.query(
      `INSERT INTO providers (subscriber_id, bpp_uri, organization, integration_mode)
       VALUES ($1, $2, $3, $4) RETURNING id`,
      [new_provider.subscriber_id, new_provider.bpp_uri, JSON.stringify(new_provider.organization), mode]
    );
    finalProviderId = res.rows[0].id;
  }

  await pool.query(
    `UPDATE users SET role = 'publisher', subscription_status = 'active', provider_id = $1, updated_at = NOW() WHERE id = $2`,
    [finalProviderId, user.id]
  );

  const token = await signToken({
    id: user.id,
    email: user.email,
    role: "publisher",
    subscription_status: "active",
    provider_id: finalProviderId,
  });

  const response = NextResponse.json({ ok: true, token });
  response.cookies.set("token", token, {
    httpOnly: true,
    secure: process.env.NODE_ENV === "production",
    sameSite: "lax",
    maxAge: 60 * 60 * 24,
    path: "/",
  });

  return response;
}
