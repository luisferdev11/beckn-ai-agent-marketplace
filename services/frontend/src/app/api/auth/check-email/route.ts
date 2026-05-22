import { NextRequest, NextResponse } from "next/server";
import { getByEmail } from "@/lib/mock-users";

export async function POST(req: NextRequest) {
  const { email } = await req.json();
  if (!email) return NextResponse.json({ error: "Email requerido" }, { status: 400 });

  return NextResponse.json({ exists: getByEmail(email) !== null });
}
