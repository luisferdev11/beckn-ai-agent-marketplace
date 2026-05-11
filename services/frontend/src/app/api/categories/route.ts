import { NextResponse } from "next/server";
import pool from "@/lib/db";

export async function GET() {
  const result = await pool.query(
    "SELECT id, name, display_name, description FROM categories WHERE is_active = true ORDER BY id"
  );
  return NextResponse.json(result.rows);
}
