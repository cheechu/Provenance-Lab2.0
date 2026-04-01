# PDB Validation Spec

This document defines what a valid PDB file looks like, what we auto-extract on upload, and when to reject a file. It also explains CBE vs ABE base editor modes.
kavin
## 1. What does a valid PDB file look like?

A valid PDB record is plain text structured by column-based record types. At minimum a valid file for this system should include:

- `HEADER` line (or lines)
  - Typically contains global metadata: macromolecule name, deposit date, PDB ID.
  - Example: `HEADER    PLANT PROTEIN                           30-APR-81   1CRN`.
- `ATOM` / `HETATM` block(s)
  - Each atom line defines 3D coordinate data, residue ID, chain, element, occupancy, B-factor.
  - Example atom line: `ATOM      1  N   THR A   1      17.047  14.099   3.625  1.00 13.79           N`.
- `END` line
  - Marks the logical end of coordinates and the structure record set.

### Why these lines matter

- `HEADER`: tells the dataset type + source + date, and often allows a quick species/protein lookup.
- `ATOM`: this is the structure payload. Without it there is no geometry to model.
- `END`: ensures the parser does not continue into truncated or extra garbage.

Optional but useful records:

- `TITLE` / `TITLE 2 ...`: human-readable project title.
- `COMPND`, `SOURCE`, `AUTHOR`: protein name, organism, engineering notes, literature context.
- `REMARK 2`, `REMARK 3` etc: refinement details, resolution.
- `SEQRES`: full sequence details.
- `SHEET`, `HELIX`, `SSBOND`: secondary structure and disulfide connectivity.

## 2. Auto-extracted fields on upload

When the user uploads a PDB file, the system should auto-extract and display:

- Protein name (from `HEADER`, `TITLE`, `COMPND` or `DBREF`/`SEQRES` if available)
- Chain IDs (from `ATOM` records `chain identifier` column, e.g. A/B/C)
- Resolution (if found in `REMARK 2` or `REMARK 3`; numeric angstrom value)
- Organism (from `SOURCE` lines, or fallback via UniProt cross-ref in `DBREF`)
- Residue count (unique residue numbers in `ATOM`/`HETATM` by chain)
- Atom count (number of `ATOM` / `HETATM` lines)
- PDB ID (from `HEADER` end of line, e.g. `1CRN`)
- Secondary structure summary (helix/sheet counts, if present)

This should behave like image metadata (“dimensions, camera”) but for protein structure.

## 3. Reject conditions (invalid / unusable files)

Reject upload with clear error when:

- Missing `ATOM` records entirely (no 3D coordinates)
- Missing `END` record (potentially truncated file)
- Absent `HEADER` or invalid `HEADER` format (not syntactically PDB)
- Faulty records: field columns out of expected range (bad numeric fields, wrong columns)
- Unexpected file type (non-plain-text / binary / compressed .jpg etc)
- File is corrupt: broken lines too short, unparseable whitespace, invalid non-ASCII control characters
- Atom lines with invalid chain/residue numbering if they prevent model building
- PDB ID mismatch (declared ID not consistent with metadata, optional sanity check)

## 4. CBE vs ABE (base-editor modes)

- CBE (cytosine base editor) changes C•G to T•A in the target DNA window, and is often used when the desired edit is a C-to-T transition in an editable range. It is best when you need to install stop codons, splice-site point mutations or reversion of pathogenic C variants.
- ABE (adenine base editor) changes A•T to G•C, and is used when the desired edit is an A-to-G transition. It is best for missense corrections that require A->G transitions or when a nearby adenine is in the editing window and cytosine is not.

In short: choose CBE for C->T edits, ABE for A->G edits. A scientist chooses based on the exact base change required and which editable positions are available in the protospacer window (typically 4-8 nt in the PAM-proximal region). CBE and ABE differ by their deaminase chemistry and by the positive/negative editing window; the decision is made in a single high-level sentence: if the causal variant is C->T (or G->A on opposite strand) use CBE, otherwise if it is A->G (T->C on opposite strand) use ABE.
