# SRR Chatbot — UI Design Prototype

## Design System

### Color Palette
| Token | Value | Usage |
|---|---|---|
| Primary gradient | `#667eea → #764ba2` | Header, user bubbles, primary buttons |
| Background | `#f8f9fa` | Chat area, page background |
| Surface | `#ffffff` | Message bubbles, modals, cards |
| Text primary | `#333333` | Body text |
| Text secondary | `#666666` | Subtitles, metadata |
| Border | `#e0e0e0` | Dividers, input borders |
| Success | `#28a745` | Completion states |
| Warning | `#ffc107` | Needs review, partial states |
| Error | `#dc3545` | Error states |

### Typography
| Element | Size | Weight |
|---|---|---|
| Page title | 24px | 700 |
| Section heading | 18px | 700 |
| Card heading | 16px | 500 |
| Body | 14px | 400 |
| Caption / metadata | 12px | 400 |
| Font stack | `-apple-system, BlinkMacSystemFont, 'Segoe UI', 'Roboto'` | — |

### Spacing & Shape
- Grid: 8px base unit (8 / 12 / 16 / 20 / 24px)
- Border radius: 20px (modal/card outer), 10px (inner cards), 25px (pill buttons/inputs)
- Shadow: `0 20px 40px rgba(0,0,0,0.1)` (cards), `0 20px 40px rgba(0,0,0,0.3)` (modals)

---

## Overall Layout

The interface uses a **sidebar + main chat** split layout with authentication.

```
┌──────────────────────────────────────────────────────────────────┐
│  Login / Register Page (full screen, purple gradient bg)         │
│  → On success → Main App Layout                                  │
└──────────────────────────────────────────────────────────────────┘

Main App Layout (post-login):
┌──────────────┬───────────────────────────────────────────────────┐
│              │  Header: SRR Case Processing Assistant             │
│   Sidebar    ├───────────────────────────────────────────────────┤
│              │                                                   │
│ • Chat       │          Chat Area (main)                         │
│ • Cases      │          Messages + ThinkingChain + RAGEvalPanel  │
│ • KB         │                                                   │
│ • User       ├───────────────────────────────────────────────────┤
│              │  Input Bar + Action Buttons                        │
└──────────────┴───────────────────────────────────────────────────┘
```

### Sidebar (`Sidebar.tsx`)
- Width: ~220px, collapsible on mobile
- Navigation items: Chat · Cases · Knowledge Base · User Info
- Purple gradient accent for active item
- Bottom: Logout button

---

## Auth Pages

### Login Page (`LoginPage.tsx`)
```
┌─────────────────────────────────────────┐
│       [Logo]  SRR System                │
│                                         │
│  Phone number  ________________________ │
│  Password      ________________________ │
│                                         │
│           [Sign In]                     │
│      Don't have an account? Register    │
└─────────────────────────────────────────┘
```
- Full-screen purple gradient background
- Card centered, max-width 400px, white surface, 20px radius
- Logos displayed above the form

### Register Page (`RegisterPage.tsx`)
- Same layout as Login; adds Name and Confirm Password fields

---

## Chat Interface (`ChatbotInterface.tsx`)

### Header
- Background: purple gradient
- Title: "SRR Case Processing Assistant" (24px bold, white)
- Subtitle: "Intelligent File Processing & Case Query System" (14px, 90% opacity)
- Height: 80px

### Message Area
- Background: `#f8f9fa`
- Auto-scrolls to newest message
- Supports Markdown rendering in bot messages

#### Bot Message
```
┌─────────────────────────────────────────┐
│ 🤖  ┌─────────────────────────────────┐ │
│     │ Hello! Upload case files (ICC   │ │
│     │ TXT, TMO/RCC PDF, images, ZIP)  │ │
│     └─────────────────────────────────┘ │
│     [ThinkingChain panel — collapsible] │
│     [RAGEvalPanel — collapsible]        │
└─────────────────────────────────────────┘
```
- Avatar: circular, gray bg, bot icon
- Bubble: white bg, 1px border, bottom-left flat radius
- Max-width: 70%, left-aligned

#### User Message
```
┌─────────────────────────────────────────┐
│ ┌─────────────────────────────────────┐ │
│ │ What is the slope number for this   │ 👤│
│ │ case?                               │  │
│ └─────────────────────────────────────┘  │
└─────────────────────────────────────────┘
```
- Avatar: circular, purple bg
- Bubble: purple gradient, white text, bottom-right flat radius
- Max-width: 70%, right-aligned

### Input Bar
```
┌────────────────────────────────────────────────────────────┐
│ Ask questions about the case...     [📁] [💬] [📤 Send]   │
└────────────────────────────────────────────────────────────┘
```

#### Action Buttons (context-aware)
| Button | Shows when |
|---|---|
| 📁 Upload Files | Always visible |
| ⚡ Process Files | Files selected but not yet processed |
| 📊 View Details | Processing complete |
| 💬 Generate Reply | Case loaded, reply not yet generated |
| 📤 Send | Always visible |

### Suggested Questions (`SuggestedQuestions.tsx`)
Appears above input bar when no query is active. Shows 3–4 clickable question chips based on context.

---

## ThinkingChain (`ThinkingChain.tsx`)

Collapsible reasoning panel attached below each bot message. Shows the agent's step-by-step processing.

```
┌─────────────────────────────────────────────────────┐
│ [Reasoning summary]              [Show 5 step(s) ▼] │
├─────────────────────────────────────────────────────┤
│ 1. Intent        classify_intent → create_case  2ms │
│ 2. Decompose     1 retrieval unit prepared      1ms │
│ 3. Retrieve      historical_cases=3 kb_docs=2  45ms │
│ 4. Synthesize    Generating with reasoning...       │
│ 5. Evaluate      faithfulness=0.82 quality=0.79     │
└─────────────────────────────────────────────────────┘
```

Step types: `intent` · `decompose` · `retrieve` · `synthesize` · `evaluate`

---

## RAGEvalPanel (`RAGEvalPanel.tsx`)

Collapsible quality panel showing retrieval and generation quality metrics.

```
┌─────────────────────────────────────────────────────┐
│ Response Quality: 0.79             [Show details ▼] │
├─────────────────────────────────────────────────────┤
│ Context Relevance   ████████░░  82%                 │
│ Faithfulness        ████████░░  79%                 │
│ Coverage            ███████░░░  74%                 │
│                                                     │
│ Sources retrieved: historical_cases=3 kb_docs=2     │
│ Eval method: keyword_overlap | RAGAS                │
│ Latency: retrieval 43ms · generation 1820ms         │
└─────────────────────────────────────────────────────┘
```

---

## File Upload Modal (`FileUploadModal.tsx`)

```
┌─────────────────────────────────────────────────────┐
│  File Upload                                    [✕] │
├─────────────────────────────────────────────────────┤
│ ┌─────────────────────────────────────────────────┐ │
│ │              📤                                 │ │
│ │     Click or drag files here                    │ │
│ │  ICC TXT · TMO/RCC PDF · Images · ZIP           │ │
│ └─────────────────────────────────────────────────┘ │
│                                                     │
│ Selected (2)                           [Clear All]  │
│  📄 3-3XYHOGP.txt                           [✕]   │
│  📄 2025A.Jan030.pdf                        [✕]   │
│                                                     │
│                   [Process Files]                   │
└─────────────────────────────────────────────────────┘
```

Supported: ICC `.txt` · TMO/RCC `.pdf`/`.docx` · `.jpg`/`.png` (location maps, site photos) · `.zip` (auto-extracted)

---

## Case Detail Modal (`CaseDetailModal.tsx`)

Shows extracted A–Q fields, AI summary, similar cases, and reply draft after processing.

```
┌─────────────────────────────────────────────────────┐
│  Case Detail                                    [✕] │
├─────────────────────────────────────────────────────┤
│  [Fields]  [Summary]  [Similar Cases]  [Reply]      │
├─────────────────────────────────────────────────────┤
│  📅 A. Date Received      21-Jan-2025               │
│  📋 B. Source             ICC                       │
│  🔢 C. Case Number        3-3XYHOGP001              │
│  ⚡ D. Type               Urgent                    │
│  👤 E. Caller Name        Chan Tai Man              │
│  📱 F. Contact No         91234567                  │
│  🏗️  G. Slope No          11SW-D/CR995              │
│  📍 H. Location           Broadwood Road            │
│  …                                                  │
│                                                     │
│  [✏️ Correct field]  → opens CorrectionModal        │
└─────────────────────────────────────────────────────┘
```

---

## Correction Modal (`CorrectionModal.tsx`)

Triggered by clicking the correct-field button on any A–Q field. Submits to `user_feedback` ability (domain memory).

```
┌─────────────────────────────────────────────────────┐
│  Correct Field: J. Subject Matter               [✕] │
├─────────────────────────────────────────────────────┤
│  Incorrect value:  Others                           │
│  Correct value:    [Tree Trimming          ]        │
│  Note (optional):  [                      ]        │
│                                                     │
│  Scope:  ● This case  ○ All future cases            │
│                                                     │
│              [Cancel]  [Submit Correction]          │
└─────────────────────────────────────────────────────┘
```

Scope `global` → saved as `doc_type="correction"` in knowledge_docs, injected as `correction_hints` in future extractions.

---

## Knowledge Base Panel (`KnowledgeBasePanel.tsx`)

Accessible via Sidebar → Knowledge Base.

```
┌─────────────────────────────────────────────────────┐
│  Knowledge Base                    [Upload Doc]     │
├─────────────────────────────────────────────────────┤
│  Filter: [All ▾]         Search: [          ]       │
├─────────────────────────────────────────────────────┤
│  📄 TRAM Framework.pdf         kb_doc   2026-01-10  │
│  📄 Reply Slip V02.pdf         kb_doc   2026-01-15  │
│  ✏️  J field correction         correction 2026-03-10│
│  …                                                  │
└─────────────────────────────────────────────────────┘
```

Includes KB file preview modal (`KBFilePreviewModal.tsx`) and upload modal (`KBFileUploadModal.tsx`).

---

## Interactive States

| State | Color | Indicator |
|---|---|---|
| Loading / streaming | Purple spinner | "Reasoning in progress..." in ThinkingChain |
| Success | `#28a745` green | ✅ icon, green badge |
| Needs review | `#ffc107` amber | ⚠️ `needs_human_review` flag |
| Error | `#dc3545` red | ❌ icon, error message with retry option |
| Empty / N/A | Italic gray | "Not provided" |

---

## Component Architecture

### Component List
| Component | Role |
|---|---|
| `ChatbotInterface` | Main chat shell, message rendering, SSE stream handling |
| `Sidebar` | Navigation (Chat / Cases / KB / User) |
| `Header` | Top bar with title and logos |
| `ThinkingChain` | Collapsible reasoning steps per bot message |
| `RAGEvalPanel` | Collapsible RAG quality metrics per bot message |
| `SuggestedQuestions` | Context-aware clickable question chips |
| `ExtractedInfoDisplay` | A–Q field structured display |
| `CaseDetailModal` | Full case detail with tabs |
| `CorrectionModal` | Field correction submission → user_feedback |
| `FileUploadModal` | File picker + drop zone |
| `FileInfoModal` | File metadata after upload |
| `FileManagement` | File management panel |
| `CaseFilesPanel` | Case-attached files list |
| `KnowledgeBasePanel` | KB document management |
| `KBFileUploadModal` | KB document upload |
| `KBFilePreviewModal` | KB document preview |
| `LoginPage` / `RegisterPage` | Auth pages |
| `UserInfoModal` | User profile |
| `GradientButton` | Reusable styled button |

### State Management
- **Global**: `ChatContext.tsx` (React Context) — chat messages, session, case state, KB state
- **Component**: `useState` for modal open/close, form inputs, expand/collapse
- **API layer**: `src/services/api.ts` — typed fetch wrappers + SSE stream parsing

### Responsive Breakpoints
| Breakpoint | Layout |
|---|---|
| < 768px | Sidebar hidden (hamburger), modals full-screen |
| 768–1024px | Sidebar collapsed to icons only |
| > 1024px | Full sidebar + chat layout |

---

**Last Updated**: 2026-03-17
