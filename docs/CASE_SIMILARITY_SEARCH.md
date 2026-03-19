# Case Similarity Search

## Overview

The similarity search system matches new SRR cases against historical cases using a hybrid vector + weighted rerank approach, backed by PostgreSQL + pgvector. It powers the `search_similar_cases` atomic ability and the `HybridSearchService`.

---

## Scoring Weights

| Criterion | Weight | Matching Method |
|---|---|---|
| **Location** (`H_location`) | **50%** | Vector similarity + fuzzy string match |
| **Slope / Tree number** (`G_slope_no`) | **30%** | Normalized exact match + vector fallback |
| **Caller info** (`E_caller_name` / `F_contact_no`) | **20%** | Fuzzy name (≥ 80%) / exact phone (last 8 digits) |

**Duplicate threshold**: ≥ 70% total similarity score.

---

## How It Works

### 1. Vector Recall (pgvector)

Case fields are embedded (OpenAI `text-embedding-3-small` or Ollama `nomic-embed-text`) and stored in `knowledge_docs_vectors`. At query time, the new case embedding is compared via cosine distance (`<=>` operator) to retrieve top candidates.

```sql
SELECT * FROM knowledge_docs_vectors
WHERE metadata->>'knowledge_type' = 'case'
ORDER BY embedding <=> $query_embedding
LIMIT 20;
```

### 2. Weighted Rerank

Candidates are re-scored by combining:
- Location fuzzy match (`difflib.SequenceMatcher`, threshold 70%)
- Slope/tree exact match after normalization
- Caller name fuzzy match (threshold 80%) and phone exact match

Final score = 0.5 × location + 0.3 × slope_tree + 0.2 × caller

### 3. Duplicate Detection

Cases scoring ≥ 70% are flagged `is_potential_duplicate`. The `detect_duplicate` ability additionally parses the 1823 email title for explicit "新案件 / 重複案件" markers and links prior case IDs from `case memory`.

---

## Slope Number Normalization

Handles format variations before comparison:
- `11SW-B/F199` → `11SWB/F199` → normalized key
- Handles missing brackets, space variants, leading-zero differences (e.g. `1SW` vs `11SW`)

---

## API

### Create Case (triggers similarity search automatically)

```
POST /api/cases/create
Content-Type: multipart/form-data

files: <case files>
```

Similarity results are returned in the `process_case` response under `similar_cases`.

### Chat Query (ad hoc similarity search)

```
POST /api/chat
Content-Type: application/json

{
  "query": "任何有關 Broadwood Road 11SW-D/CR995 的歷史個案嗎？",
  "session_id": "..."
}
```

Returns similar cases via RAG context in the SSE stream.

---

## Frequent Complaint Detection

A location or slope is flagged as a frequent complaint hotspot if it appears in **≥ 3 historical cases**. This is surfaced in the AI summary and shown in the frontend case detail panel.

---

## Technical Details

- **Database**: PostgreSQL 15 + pgvector (`knowledge_docs_vectors` table)
- **Embedding model**: OpenAI `text-embedding-3-small` (default) or Ollama `nomic-embed-text`
- **String similarity**: `difflib.SequenceMatcher`
- **Service**: `backend/src/services/hybrid_search_service.py`
- **Ability**: `backend/src/agent/abilities/search_similar.py`

---

**Last Updated**: 2026-03-17
