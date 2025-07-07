export { Sandbox } from "@cloudflare/sandbox";

import { getSandbox, Sandbox } from "@cloudflare/sandbox";
import { ExecuteResponse } from "@cloudflare/sandbox/client";

async function runCommand(sandbox: DurableObjectStub<Sandbox>, command: string, args: string[]): Promise<void> {
    const result = await sandbox.exec(command, args) as ExecuteResponse;
    if (!result.success || result.exitCode != 0) {
        throw new Error(`Command failed: ${command} ${args.join(" ")}\nstdout: ${result.stdout}\nstderr: ${result.stderr}`);
    }
}

export default {
    async fetch(request: Request, env: Env, ctx: ExecutionContext): Promise<Response> {
        if (request.method !== "POST") {
            return new Response("Method Not Allowed", { status: 405 });
        }

        const url = new URL(request.url);
        if (url.pathname !== "/") {
            return new Response("Not Found", { status: 404 });
        }

        const sandboxId = env.Sandbox.newUniqueId();
        const sandbox = getSandbox(env.Sandbox, sandboxId.toString());

        try {
            const pyprojectToml = await request.text();
            await sandbox.writeFile("pyproject.toml", pyprojectToml);

            await runCommand(sandbox, "pywrangler", ["--debug", "sync"]);

            // Create a tarball of the generated vendor directory
            await runCommand(sandbox, "tar", ["-czf", "/app/vendor.tar.gz", "-C", "/app/src/vendor", "."]);

            const archive = await sandbox.readFile("/app/vendor.tar.gz", { encoding: "binary" });
            if (!archive.success) {
                throw new Error(`Failed to read vendor.tar.gz: ${archive}`);
            }

            // The `Response` constructor encodes strings as UTF-8 by default. For binary data,
            // this can lead to corruption and size changes. To send the raw bytes correctly,
            // we must first convert the "binary" string into an ArrayBuffer.
            const buffer = new Uint8Array(archive.content.length);
            for (let i = 0; i < archive.content.length; i++) {
                buffer[i] = archive.content.charCodeAt(i);
            }

            return new Response(buffer, {
                headers: {
                    "Content-Type": "application/gzip",
                    "Content-Disposition": 'attachment; filename="vendor.tar.gz"',
                },
            });
        } catch (error: any) {
            console.error(error.stack);
            return new Response(error.message, { status: 500 });
        }
    },
} satisfies ExportedHandler<Env>;
