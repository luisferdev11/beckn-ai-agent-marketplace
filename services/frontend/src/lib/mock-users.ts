import type { Role } from "@/lib/auth";

export interface MockUser {
  id: string;
  email: string;
  password: string;
  role: Role;
  subscription_status: string;
  provider_id: number | null;
  company_name: string | null;
}

const SEED: MockUser[] = [
  {
    id: "u-admin-1",
    email: "admin@demo.com",
    password: "demo",
    role: "admin",
    subscription_status: "active",
    provider_id: null,
    company_name: null,
  },
  {
    id: "u-publisher-1",
    email: "publisher@demo.com",
    password: "demo",
    role: "publisher",
    subscription_status: "active",
    provider_id: 1,
    company_name: "Demo Agents Inc.",
  },
  {
    id: "u-consumer-1",
    email: "consumer@demo.com",
    password: "demo",
    role: "consumer",
    subscription_status: "free",
    provider_id: null,
    company_name: null,
  },
];

const store: Map<string, MockUser> = (globalThis as unknown as { __mockUsers?: Map<string, MockUser> }).__mockUsers
  ?? new Map(SEED.map((u) => [u.email, u]));
(globalThis as unknown as { __mockUsers?: Map<string, MockUser> }).__mockUsers = store;

let nextProviderId = 100;

export function getByEmail(email: string): MockUser | null {
  return store.get(email) ?? null;
}

export function getById(id: string): MockUser | null {
  for (const u of store.values()) if (u.id === id) return u;
  return null;
}

export function create(input: {
  email: string;
  password: string;
  role: Role;
  provider_id?: number | null;
  company_name?: string | null;
  subscription_status?: string;
}): MockUser {
  const user: MockUser = {
    id: `u-${Date.now()}`,
    email: input.email,
    password: input.password,
    role: input.role,
    subscription_status: input.subscription_status ?? (input.role === "publisher" ? "active" : "free"),
    provider_id: input.provider_id ?? null,
    company_name: input.company_name ?? null,
  };
  store.set(user.email, user);
  return user;
}

export function update(id: string, patch: Partial<Omit<MockUser, "id" | "email">>): MockUser | null {
  const existing = getById(id);
  if (!existing) return null;
  const updated = { ...existing, ...patch };
  store.set(updated.email, updated);
  return updated;
}

export function allocateProviderId(): number {
  return nextProviderId++;
}
