// Plain-language explanations for "the server couldn't answer", shared by the banner and error cards.

import type { ConnectionProblem } from "../api/client";

export const PROBLEM_TEXT: Record<ConnectionProblem, { title: string; body: string; devHint: string }> = {
  offline: {
    title: "You're offline",
    body: "Check your internet connection. FoodLoop will reconnect by itself.",
    devHint: "",
  },
  server_unreachable: {
    title: "Can't connect to the FoodLoop server",
    body: "FoodLoop will reconnect by itself as soon as the server is back.",
    devHint:
      "Running FoodLoop on your computer? The backend isn't running. Double-click “Start FoodLoop” in the project " +
      "folder, or run `uvicorn app.main:app --reload` in the backend folder.",
  },
  database_unavailable: {
    title: "FoodLoop's database isn't reachable",
    body: "FoodLoop will reconnect by itself as soon as the database is back.",
    devHint:
      "Running FoodLoop on your computer? Open Docker Desktop and run `docker compose up -d` in the project folder " +
      "(or start your PostgreSQL service).",
  },
};
