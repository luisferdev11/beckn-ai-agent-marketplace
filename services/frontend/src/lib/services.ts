export const BAP_URL = process.env.BAP_URL ?? 'http://localhost:3001';
export const BPP_URL = process.env.BPP_URL ?? 'http://localhost:3002';
// Mock-network = CDS + Registry (admission/conformance/probe). Only reached
// server-side from Next.js route handlers, so it defaults to the docker
// service hostname; override with MOCKNET_URL for other deployments.
export const MOCKNET_URL = process.env.MOCKNET_URL ?? 'http://mock-network:8090';
