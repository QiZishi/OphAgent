# Tool constraints

- No mock, random value, canned diagnosis or fake coordinate in production.
- Inputs and outputs must be Pydantic validated.
- Network calls require timeout and bounded retry.
- Do not log credentials, complete patient text or raw model chain-of-thought.
- Search results are evidence candidates and never auto-promote into the guideline corpus.
