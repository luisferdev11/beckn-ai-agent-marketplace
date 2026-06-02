import { NextRequest, NextResponse } from "next/server";
import { requireRole } from "@/lib/auth";
import { MOCKNET_URL } from "@/lib/services";

// POST /api/admin/admission/{id}/retry-conformance — re-run the kit.
export async function POST(
  req: NextRequest,
  { params }: { params: Promise<{ id: string }> },
) {
  const user = await requireRole(req, "admin");
  if (user instanceof Response) return user;

  const { id } = await params;
  try {
    const r = await fetch(
      `${MOCKNET_URL}/registry/admission-requests/${id}/retry-conformance`,
      { method: "POST" },
    );
    return NextResponse.json(await r.json(), { status: r.status });
  } catch (e) {
    return NextResponse.json(
      { error: "registry_unreachable", detail: String(e) },
      { status: 502 },
    );
  }
}
