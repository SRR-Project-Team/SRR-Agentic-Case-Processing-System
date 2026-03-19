# SRR System — Features Reference

## Core Architecture

**7-layer Agentic Processor** with 17 pluggable atomic abilities, condition-driven orchestration, and 3-layer memory.

- **Backend**: FastAPI (Python 3.11) + PostgreSQL 15 + pgvector
- **Frontend**: React 18 + TypeScript
- **Deployment**: Google Cloud Run (`srr-pipeline`, us-central1)
- **LLM**: OpenAI GPT-4o (generation) + text-embedding-3-small (embeddings)

---

## File Processing (Layer 1 — Input Adapter)

### Supported Input
| Channel | Format | Extractor |
|---|---|---|
| ICC (1823) | `.txt` structured email | `extractFromTxt` |
| TMO | PDF/DOCX — Form1, Form2, Hazardous Tree Referral | `extractFromTMO` |
| RCC | Scanned PDF (OCR) | `extractFromRCC` |
| Location maps | JPG/PNG with slope annotations | Vision image parser |
| Site photos | JPG/PNG site conditions | Vision image parser |
| ZIP archives | Any of the above compressed | Auto-extracted recursively |

### File Sorter (`file_sorter.py`)
Recursively traverses case folders, classifies each file into 6 types (`icc_mail`, `tmo_rcc_form`, `location_plan`, `site_photo`, `zip`, `unknown`), and routes to the correct extractor. Output is a unified `ParsedDocument` with `source_type`, `attachments`, and `file_manifest`.

---

## 17 Atomic Abilities

All abilities implement `AbilityInterface` and are registered in `ABILITY_REGISTRY`.

### Field Extraction Group
| Ability | Status | Description |
|---|---|---|
| `extract_fields` | ✅ | Schema-driven LLM extraction of A–Q fields, routes by source_type |
| `fill_missing` | ✅ | Multi-file fallback using Vision attachments, location maps, referral forms |
| `check_completeness` | ✅ | Format rules + cross-field semantic consistency (e.g. D=Urgent → N≤A+1) |

### Retrieval & Routing Group
| Ability | Status | Description |
|---|---|---|
| `search_similar_cases` | ✅ | Hybrid vector + weighted rerank: location 50% / slope 30% / caller 20% |
| `search_tree` | ✅ | Exact tree/slope ID lookup + vector fallback |
| `search_knowledge` | ✅ | pgvector KB retrieval with `doc_type` filter |
| `route_department` | ✅ | SMRIS lookup, slope normalization, multi-dept split |
| `detect_duplicate` | ✅ | Email title new/repeat parsing, prior case linking |
| `annotate_referral` | ✅ | Assignment History + Contact History extraction and summary |

### External Query Group
| Ability | Status | Description |
|---|---|---|
| `call_external` | ✅ | Parallel SMRIS / GeoInfo / HKO with local fallback |

### Generation Group
| Ability | Status | Description |
|---|---|---|
| `generate_summary` | ✅ | 100–150 char Chinese case summary |
| `gen_reply` | ✅ | Reply Slip V02: type selection (ACK/INT/SUB) + bilingual body |
| `calculate_deadlines` | ✅ | K/N/O1 by code; ICC L/M preserved from extraction or fallback A+10/21 |
| `chat_answer` | ✅ | RAG Q&A SSE stream |

### Quality Control Group
| Ability | Status | Description |
|---|---|---|
| `eval_quality` | ✅ | 3-layer funnel: L1 keyword → L2 rule validator → L3 RAGAS LLM-as-Judge |
| `self_repair` | ✅ | Best-of-N comparison, 4-type differential rollback |
| `user_feedback` | ✅ | Save corrections to `knowledge_docs` (domain memory) |

---

## A–Q Field Reference

| Field | Name | Notes |
|---|---|---|
| A | Date Received | Extracted from file metadata or email header |
| B | Source | ICC / TMO / RCC / OTHER |
| C | Case Number | `3-XXXXXXXXXX` / `ASD-HKE-YYYYNNN-XX` / 8-digit |
| D | Type | Urgent / Priority / Routine |
| E | Caller Name | Surname for ICC; "{Name} of TMO (DEVB)" for TMO; Full name for RCC |
| F | Contact No | Phone/email; "TMO (DEVB)" for TMO |
| G | Slope No | Normalized, fuzzy-matched |
| H | Location | GeoInfo-standardized |
| I | Nature of Request | AI-generated summary |
| J | Subject Matter | 17-category classification |
| K | 10-Day Rule Due Date | Code-calculated |
| L | ICC Interim Due | Extracted from "I. DUE DATE:" or A+10 fallback |
| M | ICC Final Due | Extracted from "I. DUE DATE:" or A+21 fallback |
| N | Works Completion Due | Code-calculated |
| O1 | Fax to Contractor | Date of dispatch |
| O2 | Email Send Time | Timestamp |
| P | Fax Pages | Count |
| Q | Case Details | 100–150 char AI summary |

---

## Similarity Search

Powered by `HybridSearchService` + pgvector:

| Criterion | Weight |
|---|---|
| Location (H_location) | 50% |
| Slope / Tree number (G_slope_no) | 30% |
| Caller info (E/F) | 20% |

Duplicate threshold: ≥ 70% similarity score.

---

## Quality Evaluation (3-Layer Funnel)

| Layer | Evaluator | Trigger | Cost |
|---|---|---|---|
| L1 | `KeywordEvaluator` (keyword overlap) | Always | Zero |
| L2 | Rule validator (field completeness, date logic, slope format) | L1 score 0.3–0.5 | Zero |
| L3 | RAGAS LLM-as-Judge (faithfulness + coverage) | L1+L2 indeterminate | ~3s LLM call |

Self-repair triggers when `0.3 ≤ quality_score < 0.5`. Score `< 0.3` → `needs_human_review` directly.

---

## Memory

| Layer | Storage | Scope |
|---|---|---|
| Task memory | `TaskState` (in-memory) | Single `process_case()` run |
| Case memory | `chat_sessions.session_state` (PostgreSQL) | Per session, cross-request |
| Domain memory | `knowledge_docs` (`doc_type="correction"`) | All cases, permanent |

---

## API Endpoints (Key)

| Endpoint | Method | Description |
|---|---|---|
| `/api/cases/create` | POST | Upload case files → run `process_case()` |
| `/api/cases/{id}` | GET | Retrieve case record |
| `/api/cases` | GET | List cases |
| `/api/chat` | POST | SSE chat stream (RAG Q&A) |
| `/api/knowledge-base/upload` | POST | Upload KB documents |
| `/api/knowledge-base/docs` | GET | List KB documents |
| `/api/user-feedback` | POST | Submit field correction |
| `/health` | GET | Health check |

Full route definitions: `backend/src/api/routes/`

---

## R1–R18 Status Summary

| ✅ Implemented | ⚠️ Partial |
|---|---|
| R1 orchestration · R2 external data · R4 referral annotation · R5 user feedback · R8 self-repair · R10 department routing · R11 similar cases · R12 multi-slope split · R13 Reply Slip V02 · R16 TMO form differentiation · R18 duplicate detection | R3 multi-channel adapter · R6 memory depth · R7 eval coverage · R9 reply governance · R14 KB approval · R15 observability · R17 test coverage |

---

**Last Updated**: 2026-03-17
