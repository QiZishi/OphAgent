# Plugin constraints

- Public plugin IDs are `lesion_localizer`, `aux_diagnosis`, and `report_generator`.
- General question answering and knowledge retrieval are core capabilities, not public plugins.
- A plugin may compose capabilities but may not contain canned diagnoses.
- Lesion coordinates must pass `ImageRegion` validation and originate in model output.
- Every diagnostic or knowledge answer must expose uncertainty and evidence gaps.
