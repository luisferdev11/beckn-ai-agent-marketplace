import { NextRequest, NextResponse } from "next/server";
import { signToken, type Role } from "@/lib/auth";
import { allocateProviderId, create, getByEmail } from "@/lib/mock-users";

export async function POST(req: NextRequest) {
  const body = await req.json();
  const { email, password, role, provider_id, new_provider } = body as {
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

  if (getByEmail(email)) {
    return NextResponse.json({ error: "Email ya registrado" }, { status: 409 });
  }

  let finalProviderId: number | null = provider_id ?? null;
  let companyName: string | null = null;

  if (userRole === "publisher" && new_provider) {
    finalProviderId = allocateProviderId();
    companyName = new_provider.organization?.name ?? null;
  }

  const user = create({
    email,
    password,
    role: userRole,
    provider_id: finalProviderId,
    company_name: companyName,
  });

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
