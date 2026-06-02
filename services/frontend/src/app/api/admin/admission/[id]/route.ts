import { NextRequest, NextResponse } from "next/server";
import { requireRole } from "@/lib/auth";
import { MOCKNET_URL } from "@/lib/services";

// GET /api/admin/admission/{id} — full request detail incl. subscriber
// status + latest conformance run.
export async function GET(
  req: NextRequest,
  { params }: { params: Promise<{ id: string }> },
) {
  const user = await requireRole(req, "admin");
  if (user instanceof Response) return user;

  const { id } = await params;
  try {
    const r = await fetch(`${MOCKNET_URL}/registry/admission-requests/${id}`, {
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
