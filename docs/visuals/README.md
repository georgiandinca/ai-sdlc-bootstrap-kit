# Visuals

Framework diagrams for the AI-SDLC Bootstrap Kit.

| File | What it shows |
|---|---|
| [`ai-sdlc-framework.excalidraw`](./ai-sdlc-framework.excalidraw) · [PNG](./ai-sdlc-framework.png) | The hero diagram — the seven-pillar architecture and how the pieces connect. |
| [`board-to-kit.excalidraw`](./board-to-kit.excalidraw) · [PNG](./board-to-kit.png) | The *AUTOMATIZARE* whiteboard mapped to where each idea lives in `template/`. |

**Editing `.excalidraw` files:** open them at [excalidraw.com](https://excalidraw.com) (File → Open) or with the *Excalidraw* VS Code extension. The PNGs are exports for quick viewing — re-export after editing.

The GitHub-native Mermaid versions below render inline without opening Excalidraw.

## Seven-pillar architecture

```mermaid
flowchart TB
    subgraph P5["5 · Knowledge layer"]
        SRC(["Sources"]) -->|ingest| KB["KG / RAG / Vector store"]
    end
    SET(["1 · Setup<br/>bootstrap.sh"])
    ONB(["2 · Onboarding<br/>USER.md"])
    subgraph P6["6 · Roles × Skills × MCP"]
        direction LR
        A["Architect<br/>Skill + MCP"]
        E["EM<br/>Skill + MCP"]
        P["Product<br/>Skill + MCP"]
        D["Developer<br/>Skill + MCP"]
        Q["QA<br/>Skill + MCP"]
    end
    G["3 · Governance & rules<br/>AGENTS.md · trust tiers · scoped-write MCP"]
    CI["4 · CI/CD gates — rules as scripts<br/>validate-skills · validate-frontmatter · commit hook"]
    subgraph P7["7 · Human — methodology & continuous improvement"]
        direction LR
        DASH["Dashboard (DB + web)"] --> RETRO["Retro → improve<br/>rules / skills / knowledge"]
    end

    KB -->|ground on| P6
    ONB -.-> P6
    P6 -->|act under| G
    SET -.-> G
    G -->|enforced by| CI
    CI -->|feeds| DASH
    RETRO -.->|improves| G
    RETRO -.->|improves| KB
```

## From whiteboard to kit

```mermaid
flowchart LR
    subgraph BOARD["Whiteboard · AUTOMATIZARE"]
        direction TB
        b1["Sources → KG / RAG / VectorDB"]
        b2["Rol × Skill × MCP (the matrix)"]
        b3["① Onboarding"]
        b4["② Governance & internal rules"]
        b5["③ CI/CD for AI — rules (scripts)"]
        b6["④ Dashboard utilization (DB + web)"]
        b7["⑤ HUMAN — Methodology / Cost"]
        b8["⑥ Setup"]
        b9["Repo → Edit → Pull Request"]
    end
    subgraph KIT["Kit · template/"]
        direction TB
        k1["docs/knowledge/ + scripts/knowledge/ingest.py"]
        k2[".claude/skills/playbook-* + .mcp.json"]
        k3["ONBOARDING.md → USER.md"]
        k4["AGENTS.md · WORKING-AGREEMENT.md · ai-context/"]
        k5[".github/workflows/ + scripts/validate-*.py"]
        k6["dashboard/ — Streamlit + SQLite"]
        k7["docs/methodology/continuous-improvement.md"]
        k8["scripts/bootstrap.sh"]
        k9["scripts/session/ + git/commit_msg_ticket.py"]
    end
    b1 --> k1
    b2 --> k2
    b3 --> k3
    b4 --> k4
    b5 --> k5
    b6 --> k6
    b7 --> k7
    b8 --> k8
    b9 --> k9
```
