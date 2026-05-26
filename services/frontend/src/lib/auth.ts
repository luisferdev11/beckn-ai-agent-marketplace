import { SignJWT, jwtVerify } from "jose";
import bcrypt from "bcryptjs";
import { NextRequest } from "next/server";

const JWT_SECRET = new TextEncoder().encode(
  process.env.JWT_SECRET || "beckn-marketplace-dev-secret-change-me"
);
const JWT_EXPIRES = "24h";
const SALT_ROUNDS = 12;

// -- Types ------------------------------------------------------------------

export type Role = "consumer" | "publisher" | "admin";

export interface JwtPayload {
  id: string;
  email: string;
  role: Role;
  subscription_status: string;
  provider_id: number | null;
}

// -- Password helpers -------------------------------------------------------

export function hashPassword(plain: string): Promise<string> {
  return bcrypt.hash(plain, SALT_ROUNDS);
}

export function verifyPassword(plain: string, hash: string): Promise<boolean> {
  return bcrypt.compare(plain, hash);
}

// -- JWT helpers ------------------------------------------------------------

export async function signToken(payload: JwtPayload): Promise<string> {
  return new SignJWT(payload as unknown as Record<string, unknown>)
    .setProtectedHeader({ alg: "HS256" })
    .setExpirationTime(JWT_EXPIRES)
    .sign(JWT_SECRET);
}

export async function verifyToken(token: string): Promise<JwtPayload | null> {
  try {
    const { payload } = await jwtVerify(token, JWT_SECRET);
    return payload as unknown as JwtPayload;
  } catch {
    return null;
  }
}

// -- Extract token from request ---------------------------------------------

export function getTokenFromRequest(req: NextRequest): string | null {
  const auth = req.headers.get("authorization");
  if (auth?.startsWith("Bearer ")) return auth.slice(7);
  return req.cookies.get("token")?.value ?? null;
}

export async function getUser(req: NextRequest): Promise<JwtPayload | null> {
  const token = getTokenFromRequest(req);
  if (!token) return null;
  return verifyToken(token);
}

// -- Role check helpers (for use inside API routes) -------------------------

export async function requireAuth(req: NextRequest): Promise<JwtPayload | Response> {
  const user = await getUser(req);
  if (!user) return new Response(JSON.stringify({ error: "No autenticado" }), { status: 401 });
  return user;
}

export async function requireRole(req: NextRequest, ...roles: Role[]): Promise<JwtPayload | Response> {
  const result = await requireAuth(req);
  if (result instanceof Response) return result;
  if (!roles.includes(result.role)) {
    return new Response(JSON.stringify({ error: "Sin permisos" }), { status: 403 });
  }
  return result;
}
