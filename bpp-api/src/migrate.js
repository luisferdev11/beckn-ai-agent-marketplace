const fs = require("fs");
const path = require("path");
const pool = require("./db");

async function migrate() {
  const migrationsDir = path.join(__dirname, "..", "migrations");
  const files = fs.readdirSync(migrationsDir).filter(f => f.endsWith(".sql")).sort();

  for (const file of files) {
    const filePath = path.join(migrationsDir, file);
    const sql = fs.readFileSync(filePath, "utf8");
    console.log(`[migrate] Running ${file}...`);
    try {
      await pool.query(sql);
      console.log(`[migrate] ${file} — OK`);
    } catch (err) {
      console.error(`[migrate] ${file} — FAILED:`, err.message);
    }
  }

  await pool.end();
  console.log("[migrate] Done.");
}

migrate();
