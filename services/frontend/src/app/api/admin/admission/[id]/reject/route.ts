import { NextRequest, NextResponse } from "next/server";
import { requireRole } from "@/lib/auth";
import { MOCKNET_URL } from "@/lib/services";

// POST /api/admin/admission/{id}/reject  body: { reason }
export async function POST(
  req: NextRequest,
  { params }: { params: Promise<{ id: string }> },
) {
  const user = await requireRole(req, "admin");
  if (user instanceof Response) return user;

  const { id } = await params;
  const body = await req.json().catch(() => ({}));
  const reason = (body?.reason || "").trim();
  if (!reason) {
    return NextResponse.json({ error: "reason_required" }, { status: 400 });
  }
  try {
    const r = await fetch(
      `${MOCKNET_URL}/registry/admission-requests/${id}/reject`,
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ reason }),
      },
    );
    return NextResponse.json(await r.json(), { status: r.status });
  } catch (e) {
    return NextResponse.json(
      { error: "registry_unreachable", detail: String(e) },
      { status: 502 },
    );
  }
}
