import { NextResponse } from "next/server";
import pool from "@/lib/db";

export async function GET() {
  const result = await pool.query(
    "SELECT id, subscriber_id, bpp_uri, organization, status, integration_mode FROM providers WHERE status = 'active' ORDER BY id"
  );
  return NextResponse.json(result.rows);
}
