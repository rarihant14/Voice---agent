# VOXA Flow Diagram

This document describes how the frontend, backend, and agents work together.

## Flow Diagram

```mermaid
flowchart TD
    A[User in Browser UI] --> B[frontend/index.html]
    B --> C[frontend/main.js]
    C --> D[FastAPI app]
    D --> Q[Session Memory Store]

    D --> E{Input Type}
    E -->|Audio| F[STT Agent]
    E -->|Text| G[Intent Agent]

    F --> G
    G --> H[Execution Agent]

    H --> I{Intent Route}
    I -->|write_code| J[code_tools.py]
    I -->|create_file| K[file_tools.py]
    I -->|summarize_text| L[LLM Summary Path]
    I -->|general_chat| M[LLM Chat Path]

    J --> N[output/]
    K --> N
    L --> O[JSON Response]
    M --> O
    N --> O
    O --> Q
    Q --> O
    O --> C
    C --> P[Rendered UI]
```

## Endpoint Summary

- `GET /` serves the main page
- `GET /frontend/*` serves frontend assets
- `GET /health` reports backend status
- `POST /process/audio` handles audio uploads and STT
- `POST /process/text` handles direct text input
- `GET /output/files` lists generated files
- `GET /output/*` serves generated output files

## Notes

- Audio requests go through STT before intent classification.
- Text requests start directly at the intent agent.
- The frontend renders a single structured response from the backend pipeline.
- Session memory is stored in-memory per browser session and is reused for context-aware chat and summarization.
