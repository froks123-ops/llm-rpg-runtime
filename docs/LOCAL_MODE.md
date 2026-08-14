# Local enhanced mode

Local enhanced mode is intentionally optional and is not required by v0.2 cloud semantics.

Planned additions after the cloud state model is stable:

- `sqlite-vec` for semantic archive retrieval;
- local ONNX embeddings;
- DeepDiff for richer nested state comparison;
- NetworkX or a purpose-built relationship/knowledge graph if the simpler model stops scaling;
- Promptfoo or equivalent regression/evaluation tooling;
- filesystem-backed campaign snapshots compatible with Questforge-style portable saves.

The local layer must not redefine canonical campaign semantics. It accelerates retrieval, replay, testing and tooling around the same manifest/fact/event model used by cloud mode.
