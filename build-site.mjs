import { mkdir, readFile, rm, writeFile, cp } from "node:fs/promises";

const html = await readFile("site/index.html", "utf8");
const css = await readFile("site/assets/styles.css", "utf8");
const js = await readFile("site/assets/app.js", "utf8");
const image = await readFile("site/assets/agent-workflow.png");

await rm("dist", { recursive: true, force: true });
await mkdir("dist/server", { recursive: true });
await mkdir("dist/.openai", { recursive: true });
await cp(".openai/hosting.json", "dist/.openai/hosting.json");

const worker = `const HTML = ${JSON.stringify(html)};
const CSS = ${JSON.stringify(css)};
const JS = ${JSON.stringify(js)};
const IMAGE_BASE64 = ${JSON.stringify(image.toString("base64"))};

function bytesFromBase64(value) {
  const binary = atob(value);
  const bytes = new Uint8Array(binary.length);
  for (let i = 0; i < binary.length; i += 1) bytes[i] = binary.charCodeAt(i);
  return bytes;
}

function response(body, contentType) {
  return new Response(body, {
    headers: {
      "content-type": contentType,
      "cache-control": "public, max-age=300",
      "x-agent-showcase": "static-simulation"
    }
  });
}

export default {
  async fetch(request) {
    const url = new URL(request.url);
    if (url.pathname === "/" || url.pathname === "/index.html") return response(HTML, "text/html; charset=utf-8");
    if (url.pathname === "/assets/styles.css") return response(CSS, "text/css; charset=utf-8");
    if (url.pathname === "/assets/app.js") return response(JS, "application/javascript; charset=utf-8");
    if (url.pathname === "/assets/agent-workflow.png") return response(bytesFromBase64(IMAGE_BASE64), "image/png");
    return new Response("Not found", { status: 404, headers: { "content-type": "text/plain; charset=utf-8" } });
  }
};
`;

await writeFile("dist/server/index.js", worker, "utf8");
console.log("built static worker to dist/server/index.js");
