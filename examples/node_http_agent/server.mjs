import express from "express";

import { handleAnvil } from "./agent.mjs";

const app = express();
const port = Number(process.env.PORT ?? "8081");

app.use(express.json());

app.post("/anvil", (request, response) => {
  response.json(handleAnvil(request.body ?? {}));
});

app.get("/health", (_request, response) => {
  response.json({ status: "ok" });
});

app.listen(port, "127.0.0.1", () => {
  console.log(`Agent Anvil Node HTTP agent listening on http://127.0.0.1:${port}`);
});
