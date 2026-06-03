import { NextRequest, NextResponse } from "next/server";
import { requireRole } from "@/lib/auth";
import { MOCKNET_URL } from "@/lib/services";

// POST /api/admin/admission/{id}/approve — gated server-side by the
// Registry on conformance must_passed (returns 422 if not).
export async function POST(
  req: NextRequest,
  { params }: { params: Promise<{ id: string }> },
) {
  const user = await requireRole(req, "admin");
  if (user instanceof Response) return user;

  const { id } = await params;
  try {
    const r = await fetch(
      `${MOCKNET_URL}/registry/admission-requests/${id}/approve`,
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ reviewed_by: user.email }),
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
