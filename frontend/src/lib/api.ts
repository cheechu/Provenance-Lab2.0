const API_BASE_URL = "http://localhost:8000";

export async function getHealth() {
  const res = await fetch(`${API_BASE_URL}/health`);
  if (!res.ok) throw new Error("Failed to fetch health status");
  return res.json();
}

export async function getRuns() {
  const res = await fetch(`${API_BASE_URL}/runs`);
  if (!res.ok) throw new Error("Failed to fetch runs");
  return res.json();
}

export async function createRun() {
  const res = await fetch(`${API_BASE_URL}/runs`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({}),
  });
  if (!res.ok) throw new Error("Failed to create run");
  return res.json();
}

export async function getRunById(id: string) {
  const res = await fetch(`${API_BASE_URL}/runs/${id}`);
  if (!res.ok) throw new Error("Failed to fetch run");
  return res.json();
}