# Test Fixtures

Sample data files for testing and development.

## Contents

- `sample.pdb` - Example PDB protein structure file
- `test_data.json` - Sample run configuration
- (Add more fixtures as needed)

## Usage

Place test PDB files and sample data here for local testing:

```bash
curl -X POST http://localhost:8000/runs \
  -H "Content-Type: application/json" \
  -d '{
    "mode": "therapeutic",
    "pdb_filename": "test-fixtures/sample.pdb",
    "config": {}
  }'
```
