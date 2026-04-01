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

// Minimal valid RunRequest payload for test runs.
// guide_rna.sequence must be exactly 20 ACGT chars; editor_config.editor_type is required.
export async function createRun() {
  const res = await fetch(`${API_BASE_URL}/runs`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      guide_rna: {
        sequence: "ATGCATGCATGCATGCATGC",
        pam: "NGG",
        target_gene: "BRCA1",
        chromosome: "chr17",
        position_start: 41196312,
        position_end: 41196331,
        strand: "+",
      },
      editor_config: {
        editor_type: "CBE",
        cas_variant: "nCas9",
        editing_window_start: 4,
        editing_window_end: 8,
        algorithms: ["CFD", "MIT"],
      },
      track: "genomics_research",
      random_seed: 42,
      benchmark_mode: false,
    }),
  });
  if (!res.ok) throw new Error("Failed to create run");
  return res.json();
}

export async function getRunById(id: string) {
  const res = await fetch(`${API_BASE_URL}/runs/${id}`);
  if (!res.ok) throw new Error("Failed to fetch run");
  return res.json();
}
