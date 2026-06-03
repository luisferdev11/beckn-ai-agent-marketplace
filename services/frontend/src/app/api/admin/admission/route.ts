import { NextRequest, NextResponse } from "next/server";
import { requireRole } from "@/lib/auth";
import { MOCKNET_URL } from "@/lib/services";

// GET /api/admin/admission?decision=pending
// Proxies the mock-network Registry admission queue. Admin-only; the
// browser never talks to mock-network directly.
export async function GET(req: NextRequest) {
  const user = await requireRole(req, "admin");
  if (user instanceof Response) return user;

  const decision = req.nextUrl.searchParams.get("decision");
  const qs = decision ? `?decision=${encodeURIComponent(decision)}` : "";
  try {
    const r = await fetch(`${MOCKNET_URL}/registry/admission-requests${qs}`, {
      cache: "no-store",
    });
    return NextResponse.json(await r.json(), { status: r.status });
  } catch (e) {
    return NextResponse.json(
      { error: "registry_unreachable", detail: String(e) },
      { status: 502 },
    );
  }
}
