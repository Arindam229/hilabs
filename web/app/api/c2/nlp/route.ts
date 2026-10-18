
import { NextResponse } from "next/server";
import { execFileSync } from "node:child_process";
import { existsSync } from "node:fs";
import path from "node:path";

export const runtime = "nodejs";

export async function GET() {
  // Set PTD_REPO_ROOT to the repository root.
  // The fallback assumes the Next.js app is in a subdirectory
  // immediately inside the repository.
  const repoRoot = process.env.PTD_REPO_ROOT
    ? path.resolve(process.env.PTD_REPO_ROOT)
    : path.resolve(process.cwd(), "..");

  const parquet = path.join(
    repoRoot,
    "data",
    "stage",
    "c2",
    "plan_network.parquet"
  );

  const script = path.join(
    repoRoot,
    "scripts",
    "export_c2_nlp.py"
  );

  if (!existsSync(parquet)) {
    return NextResponse.json(
      { error: "Parquet file not found", path: parquet },
      { status: 404 }
    );
  }

  if (!existsSync(script)) {
    return NextResponse.json(
      { error: "Python script not found", path: script },
      { status: 404 }
    );
  }

  // Try uv run python3 first (has pyarrow/pandas from venv).
  // Fall back to PYTHON_BIN or plain python3 if uv is not available.
  const uvBin = process.env.UV_BIN || "uv";
  const fallbackPython = process.env.PYTHON_BIN || "python3";

  const attempts: Array<{ bin: string; args: string[] }> = [
    { bin: uvBin, args: ["run", "python3", script, parquet] },
    { bin: fallbackPython, args: [script, parquet] },
  ];

  let lastError: Error | null = null;
  for (const attempt of attempts) {
    try {
      const stdout = execFileSync(attempt.bin, attempt.args, {
        cwd: repoRoot,
        encoding: "utf8",
        timeout: 120_000,
        maxBuffer: 10 * 1024 * 1024,
      });
      const result = JSON.parse(stdout);
      return NextResponse.json(result);
    } catch (error) {
      lastError = error as Error;
      const e = error as NodeJS.ErrnoException & {
        stderr?: Buffer | string;
        stdout?: Buffer | string;
      };
      // Only continue to next attempt on "not found" / import errors.
      const stderr = e.stderr?.toString() ?? "";
      const isEnvError =
        e.code === "ENOENT" ||
        stderr.includes("ModuleNotFoundError") ||
        stderr.includes("No module named");
      if (!isEnvError) {
        console.error("C2 NLP export failed:", {
          bin: attempt.bin,
          message: e.message,
          stderr,
          stdout: e.stdout?.toString()?.slice(0, 2000),
        });
        return NextResponse.json(
          {
            error: "Failed to export C2 NLP data",
            detail:
              process.env.NODE_ENV === "development"
                ? stderr || e.message
                : undefined,
          },
          { status: 500 }
        );
      }
    }
  }

  const errMsg = lastError?.message ?? "unknown";
  console.error("C2 NLP export: all Python attempts failed.", errMsg);
  return NextResponse.json(
    {
      error: "Failed to export C2 NLP data — no suitable Python runtime found",
      detail: process.env.NODE_ENV === "development" ? errMsg : undefined,
    },
    { status: 500 }
  );
}
