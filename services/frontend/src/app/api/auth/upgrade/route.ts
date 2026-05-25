import { NextRequest, NextResponse } from "next/server";
import { requireAuth, signToken } from "@/lib/auth";
import { allocateProviderId, update } from "@/lib/mock-users";

export async function POST(req: NextRequest) {
  const user = await requireAuth(req);
  if (user instanceof Response) return user;

  const { provider_id, new_provider } = await req.json();

  let finalProviderId: number | null = provider_id ?? null;
  let companyName: string | null = null;

  if (new_provider) {
    finalProviderId = allocateProviderId();
    companyName = new_provider.organization?.name ?? null;
  }

  const updated = update(user.id, {
    role: "publisher",
    subscription_status: "active",
    provider_id: finalProviderId,
    company_name: companyName,
  });

  if (!updated) {
    return NextResponse.json({ error: "Usuario no encontrado" }, { status: 404 });
  }

  const token = await signToken({
    id: updated.id,
    email: updated.email,
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
