import { NextRequest, NextResponse } from "next/server";
import { getUser } from "@/lib/auth";
import { getById } from "@/lib/mock-users";

export async function GET(req: NextRequest) {
  const tokenUser = await getUser(req);
  if (!tokenUser) {
    return NextResponse.json({ error: "No autenticado" }, { status: 401 });
  }

  const user = getById(tokenUser.id);
  if (!user) {
    return NextResponse.json({ error: "Usuario no encontrado" }, { status: 404 });
  }

  return NextResponse.json({
    id: user.id,
    email: user.email,
    role: user.role,
    subscription_status: user.subscription_status,
    provider_id: user.provider_id,
    company_name: user.company_name,
  });
}
