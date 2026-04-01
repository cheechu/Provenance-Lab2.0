"""
CasAI Provenance Lab — Export Service
Generates lab-ready ZIP Export Packs per GET /runs/{id}/export.zip
"""

from __future__ import annotations

import hashlib
import io
import json
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID

from app.models.schemas import BaseEditorType, RunManifest, RunTrack


def _sha256(data: str | bytes) -> str:
    if isinstance(data, str):
        data = data.encode()
    return hashlib.sha256(data).hexdigest()


def _generate_oligos(guide_seq: str, editor_type: BaseEditorType) -> dict:
    """
    Generate forward/reverse oligo sequences for sgRNA cloning.
    Adds BsmBI-compatible sticky ends (CACC / AAAC for pYTK050-style vectors).
    """
    fwd = f"CACC G{guide_seq}"
    rev_comp = guide_seq[::-1].translate(str.maketrans("ACGT", "TGCA"))
    rev = f"AAAC C{rev_comp}"
    return {
        "forward_oligo": fwd,
        "reverse_oligo": rev,
        "vector_compatibility": "BsmBI-digested (pYTK050-style)",
        "editor_type": editor_type.value,
        "note": "Add phosphate group to 5' end before annealing.",
    }


def _generate_primers(guide_seq: str, chromosome: str, position_start: int | None) -> dict:
    """Mock flanking PCR primer design for target validation."""
    # Real implementation would call primer3 or equivalent
    pos = position_start or 1000
    return {
        "left_primer": f"GCATGCAATGCTAGCATGCA",   # mock
        "right_primer": f"TGCATGCTAGCATTGCATGC",  # mock
        "amplicon_size_bp": 750,
        "target_chromosome": chromosome or "unknown",
        "target_position_approx": pos,
        "recommended_use": "Sanger or NGS amplicon sequencing",
    }


def _generate_fasta(guide_seq: str, target_gene: str) -> str:
    return f">sgRNA_{target_gene}_protospacer\n{guide_seq}\n"


def _generate_report_txt(manifest: RunManifest) -> str:
    req = manifest.run_request
    guide = req.guide_rna
    editor = req.editor_config
    pred = manifest.prediction

    lines = [
        "=" * 72,
        "CasAI PROVENANCE LAB — DESIGN REPORT",
        "=" * 72,
        f"Run ID         : {manifest.run_id}",
        f"Status         : {manifest.status.value}",
        f"Track          : {manifest.track.value}",
        f"Start Time     : {manifest.start_time.isoformat()}",
        f"End Time       : {manifest.end_time.isoformat() if manifest.end_time else 'N/A'}",
        f"Duration       : {manifest.duration_seconds:.2f}s" if manifest.duration_seconds else "Duration       : N/A",
        f"Git SHA        : {manifest.git_sha}",
        f"Docker Image   : {manifest.docker_image}",
        f"Inputs Digest  : {manifest.inputs_digest}",
        "",
        "GUIDE RNA",
        "-" * 40,
        f"Sequence       : {guide.sequence}",
        f"PAM            : {guide.pam}",
        f"Target Gene    : {guide.target_gene}",
        f"Chromosome     : {guide.chromosome or 'N/A'}",
        f"Position       : {guide.position_start or 'N/A'} – {guide.position_end or 'N/A'}",
        f"Strand         : {guide.strand or 'N/A'}",
        "",
        "EDITOR CONFIG",
        "-" * 40,
        f"Editor Type    : {editor.editor_type.value}",
        f"Cas Variant    : {editor.cas_variant}",
        f"Deaminase      : {editor.deaminase or 'N/A'}",
        f"Editing Window : positions {editor.editing_window_start}–{editor.editing_window_end}",
        f"Algorithms     : {', '.join(a.value for a in editor.algorithms)}",
        "",
    ]

    if pred:
        lines += [
            "SCORING RESULTS",
            "-" * 40,
        ]
        for s in pred.scores:
            lines += [
                f"  [{s.algorithm.value}]",
                f"    On-target efficiency : {s.on_target_score:.4f}",
                f"    Off-target risk      : {s.off_target_risk:.4f}",
                f"    95% CI (on-target)   : [{s.confidence_interval_95_low:.4f}, {s.confidence_interval_95_high:.4f}]",
                f"    Standard error       : {s.standard_error:.4f}",
            ]
        lines += [
            "",
            f"Editing Window Bases : {pred.editing_window_bases}",
            f"Target Base Count    : {pred.target_base_count}",
        ]
        if pred.structural_variation_risk:
            lines.append(f"Structural Var. Risk : {pred.structural_variation_risk}")
        if pred.genome_coverage is not None:
            lines.append(f"Sub-genome Coverage  : {pred.genome_coverage:.2%}")

        if pred.bystander_edits:
            lines += ["", "BYSTANDER EDIT PREDICTIONS", "-" * 40]
            for b in pred.bystander_edits:
                lines.append(f"  Position {b.position_in_window}: {b.original_base}→{b.edited_base}  probability={b.probability:.2f}  risk={b.risk_level}")

        if pred.explanations:
            lines += ["", "INTERPRETABILITY (SHAP/LIME)", "-" * 40]
            for e in pred.explanations:
                lines += [
                    f"  Metric  : {e.metric}",
                    f"  Value   : {e.value:.4f}",
                    f"  Insight : {e.plain_text}",
                    f"  Caveats : {e.caveats}",
                    "",
                ]

    lines += [
        "=" * 72,
        "DISCLAIMER",
        "-" * 40,
        "All outputs are IN-SILICO HYPOTHESES only. This report does not",
        "constitute clinical or regulatory advice. Experimental wet-lab",
        "validation is required before any therapeutic or agricultural use.",
        "=" * 72,
    ]
    return "\n".join(lines)


def build_export_zip(manifest: RunManifest) -> bytes:
    """
    Build a lab-ready Export Pack ZIP in memory.
    Contents:
      - run.manifest.json         (W3C PROV JSON-LD)
      - report.txt                (human-readable summary)
      - guide_rna_input.json      (frozen input)
      - prediction.json           (scoring output)
      - cloning_oligos.json       (sgRNA cloning oligos)
      - validation_primers.json   (PCR primer design)
      - protospacer.fasta         (FASTA for guide)
      - provenance_passport.md    (lab notebook markdown)
    """
    buf = io.BytesIO()
    req = manifest.run_request
    guide = req.guide_rna
    editor = req.editor_config

    with zipfile.ZipFile(buf, mode="w", compression=zipfile.ZIP_DEFLATED) as zf:
        # 1. RunManifest JSON-LD
        zf.writestr("run.manifest.json", json.dumps(manifest.as_json_ld(), indent=2, default=str))

        # 2. Human-readable report
        zf.writestr("report.txt", _generate_report_txt(manifest))

        # 3. Frozen guide RNA input
        zf.writestr("guide_rna_input.json", req.guide_rna.model_dump_json(indent=2))

        # 4. Prediction JSON
        if manifest.prediction:
            zf.writestr("prediction.json", manifest.prediction.model_dump_json(indent=2))

        # 5. Cloning oligos
        oligos = _generate_oligos(guide.sequence, editor.editor_type)
        zf.writestr("cloning_oligos.json", json.dumps(oligos, indent=2))

        # 6. Validation primers
        primers = _generate_primers(guide.sequence, guide.chromosome or "", guide.position_start)
        zf.writestr("validation_primers.json", json.dumps(primers, indent=2))

        # 7. FASTA
        zf.writestr("protospacer.fasta", _generate_fasta(guide.sequence, guide.target_gene))

        # 8. Provenance passport markdown
        passport = _generate_passport_md(manifest, oligos, primers)
        zf.writestr("provenance_passport.md", passport)

    buf.seek(0)
    return buf.read()


def _generate_passport_md(manifest: RunManifest, oligos: dict, primers: dict) -> str:
    req = manifest.run_request
    guide = req.guide_rna
    return f"""# CasAI Provenance Passport

## Run Identity
| Field | Value |
|---|---|
| Run ID | `{manifest.run_id}` |
| Inputs Digest | `{manifest.inputs_digest}` |
| Git SHA | `{manifest.git_sha}` |
| Docker Image | `{manifest.docker_image}` |
| Track | {manifest.track.value} |
| Generated | {datetime.now(timezone.utc).isoformat()} |

## Guide RNA
| Field | Value |
|---|---|
| Sequence | `{guide.sequence}` |
| PAM | `{guide.pam}` |
| Target Gene | {guide.target_gene} |
| Chromosome | {guide.chromosome or 'N/A'} |
| Strand | {guide.strand or 'N/A'} |

## Cloning Oligos
```
Forward: {oligos['forward_oligo']}
Reverse: {oligos['reverse_oligo']}
Vector:  {oligos['vector_compatibility']}
```

## Validation Primers
```
Left:    {primers['left_primer']}
Right:   {primers['right_primer']}
Amplicon size: {primers['amplicon_size_bp']} bp
```

## Reproducibility
To reproduce this exact run:
```
POST /runs/rerun/{manifest.run_id}
```
Or provide inputs_digest `{manifest.inputs_digest}` to verify input integrity.

---
*All outputs represent in-silico hypotheses. Wet-lab validation required.*
"""
