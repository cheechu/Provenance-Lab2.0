const tabs = ["Overview", "Sequence", "Provenance", "Compare", "Export"];

export default async function RunDetailPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;

  return (
    <div className="p-6 space-y-6">
      <div>
        <h1 className="text-2xl font-semibold" style={{ color: "#000000" }}>
          Run {id}
        </h1>
        <p className="mt-1 text-sm text-slate-500">
          Placeholder run detail page
        </p>
      </div>

      <div className="border-b border-slate-200">
        <div className="flex gap-6">
          {tabs.map((tab, index) => (
            <button
              key={tab}
              className={`pb-3 text-sm font-medium transition-colors ${
                index === 0
                  ? "border-b-2 border-teal-600 text-slate-900"
                  : "text-slate-500 hover:text-slate-800"
              }`}
            >
              {tab}
            </button>
          ))}
        </div>
      </div>

      <div className="rounded-lg border border-slate-200 bg-white p-5">
        <h2 className="text-lg font-medium">Overview</h2>
        <p className="mt-2 text-sm text-slate-500">
          Run metadata and summary info will appear here.
        </p>
      </div>
    </div>
  );
}