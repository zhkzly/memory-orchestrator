# Core Operation Spec

## Tools

### `capture_candidate`

Input:
- raw observation
- source
- session
- project

Output:
- candidate memory item

### `classify_candidate`

Input:
- candidate item

Output:
- `personal`
- `project`
- `evidence`
- `session`

### `verify_candidate`

Input:
- candidate item
- evidence set

Output:
- `verified`
- `rejected`
- `needs_more_evidence`

### `promote_item`

Input:
- verified item

Output:
- written markdown path

### `build_context_pack`

Input:
- task context
- session scope
- project scope

Output:
- minimal prompt context bundle

### `evaluate_rubric`

Input:
- rubric definition
- evidence set
- candidate system

Output:
- proxy scores
- criterion scores
- overall recommendation

### `clean_memory`

Input:
- target scope

Output:
- duplicates
- outdated items
- conflict markers

## Data Targets

- `people/`
- `projects/`
- `notes/`
- `sessions/`
- `rubrics/`

## Implementation Notes

- Use markdown as the durable store.
- Keep the CLI core stateless except for file-backed reads and writes.
- Require explicit evidence for promotions.
- Treat MCP as an optional adapter over the same core.
