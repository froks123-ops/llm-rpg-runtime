# Local enhanced mode

Local mode is planned, not implemented in v0.1.

Candidate additions:

- `sqlite-vec` for semantic archive retrieval;
- local ONNX embeddings;
- DeepDiff for richer nested state comparison;
- NetworkX or a purpose-built relationship/knowledge graph;
- Promptfoo or an equivalent regression/evaluation harness;
- full Questforge-style filesystem manifests/checkpoint packaging.

The local layer should remain optional. Core campaign semantics must not depend on a specific vector database or model provider.
