# Runtime constraints

- Never emit hidden chain-of-thought. Events expose concise public summaries only.
- All nodes honor cancellation and budget limits.
- Persist run state after every node transition.
- External failures are `unavailable` or typed failures, never canned medical output.
- A resumed run may execute only pending/failed nodes whose dependencies are complete.
