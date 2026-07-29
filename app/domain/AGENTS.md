# Domain module constraints

- `ClinicalState` is the single source of clinical facts.
- Never infer confirmed facts from model prose.
- Keep red flags, medications, allergies and unresolved questions lossless.
- Schema changes must remain backward compatible or include a migration.
