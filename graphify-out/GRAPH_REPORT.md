# Graph Report - lti-chat-scala  (2026-09-03)

## Corpus Check
- cluster-only mode — file stats not available

## Summary
- 273 nodes · 434 edges · 44 communities (10 shown, 20 thin omitted)
- Extraction: 91% EXTRACTED · 9% INFERRED · 0% AMBIGUOUS · INFERRED: 37 edges (avg confidence: 0.95)
- Token cost: 0 input · 0 output

## Graph Freshness
- Built from commit: `8381de99`
- Run `git rev-parse HEAD` and compare to check if the graph is stale.
- Run `graphify update .` after code changes (no API cost).

## Community Hubs (Navigation)
- chat/views.py
- lti_tool/admin.py
- seed_demo.py
- lti_tool/views.py
- TokenUsageLedger
- canvas_pages.py
- renderChatUI
- ClaraError
- grades.py
- Handler
- LtiFrameAncestorsMiddleware
- settings.py
- ChatConfig
- LtiToolConfig
- main
- chat/migrations/0001_initial.py
- 0002_initial.py
- 0003_claramoment_claramessage.py
- 0004_claramoment_tokens_used_alter_claramoment_limite_and_more.py
- 0005_alter_claramomentlimit_closing_message_and_more.py
- 0006_claramoment_porcentaje_usado_claramoment_presupuesto_and_more.py
- 0007_claramoment_page_unlocked_at.py
- lti_tool/migrations/0001_initial.py
- 0002_courseenrollment_section_ids_student_email_and_more.py
- 0003_course_ags_lineitem_url_course_ags_lineitems_url_and_more.py
- 0004_course_show_course_token_usage_and_more.py
- 0005_coursepagegate.py
- asgi.py
- wsgi.py
- deploy.sh

## God Nodes (most connected - your core abstractions)
1. `launch()` - 14 edges
2. `ClaraMoment` - 13 edges
3. `PromptTemplate` - 12 edges
4. `CourseEnrollment` - 11 edges
5. `TokenUsageLedger` - 11 edges
6. `renderChatUI()` - 11 edges
7. `ClaraMessage` - 10 edges
8. `submitToClara()` - 10 edges
9. `ChatMessage` - 9 edges
10. `ChatSession` - 9 edges

## Surprising Connections (you probably didn't know these)
- `ChatMessageInline` --uses--> `ChatMessage`  [INFERRED]
  apps/chat/admin.py → apps/chat/models.py
- `ClaraMessageInline` --uses--> `ClaraMessage`  [INFERRED]
  apps/chat/admin.py → apps/chat/models.py
- `launch()` --uses--> `ClaraMoment`  [INFERRED]
  apps/lti_tool/views.py → apps/chat/models.py
- `Command` --uses--> `PromptTemplate`  [INFERRED]
  apps/chat/management/commands/seed_demo.py → apps/chat/models.py
- `ClaraMomentView` --uses--> `ClaraError`  [INFERRED]
  apps/chat/views.py → apps/chat/services/clara_client.py

## Import Cycles
- None detected.

## Communities (44 total, 20 thin omitted)

### Community 0 - "chat/views.py"
Cohesion: 0.09
Nodes (36): APIView, ChatMessageInline, ClaraMessageInline, ChatMessage, ChatSession, ClaraMessage, ClaraMoment, Meta (+28 more)

### Community 1 - "lti_tool/admin.py"
Cohesion: 0.10
Nodes (18): action, CourseAdmin, CourseEnrollmentAdmin, CoursePageGateAdmin, LtiLaunchLogAdmin, register, StudentAdmin, Course (+10 more)

### Community 2 - "seed_demo.py"
Cohesion: 0.11
Nodes (13): decode_launch_token(), _EnrollmentPrincipal, LaunchTokenAuthentication, Autenticación del widget de chat dentro del iframe. El chat vive en un <iframe>…, Envoltorio mínimo para que DRF (IsAuthenticated) acepte la matrícula como…, Command, BaseCommand, Datos de ejemplo para probar la API del chat SIN pasar por un lanzamiento real… (+5 more)

### Community 3 - "lti_tool/views.py"
Cohesion: 0.17
Nodes (20): encode_launch_token(), extract_course_fields(), extract_enrollment_fields(), extract_momento(), extract_student_fields(), get_launch_data_storage(), get_tool_conf(), is_instructor() (+12 more)

### Community 4 - "TokenUsageLedger"
Cohesion: 0.15
Nodes (15): ChatSessionAdmin, ClaraMomentAdmin, N8nFlowAdmin, PromptTemplateAdmin, register, TokenUsageLedgerAdmin, Registro append-only del consumo de tokens. Nunca se actualiza ni se borra una…, TokenUsageLedger (+7 more)

### Community 5 - "canvas_pages.py"
Cohesion: 0.15
Nodes (15): _date_details_url(), find_stale_retrieve_urls(), _headers(), list_page_urls(), lock_page(), Desbloqueo de páginas de Canvas por estudiante vía "Asignar acceso" (assignment…, Setup inicial de un CoursePageGate: deja la página oculta a todos…, Slugs ('url') de todas las páginas del curso, paginando la respuesta de Canvas. (+7 more)

### Community 6 - "renderChatUI"
Cohesion: 0.25
Nodes (15): api(), boot(), escapeHtml(), formatAssistantText(), refreshUsageBar(), renderBlockedNotice(), renderChatUI(), appendBubble() (+7 more)

### Community 7 - "ClaraError"
Cohesion: 0.20
Nodes (12): chat_exception_handler(), Convierte N8nError/ClaraError (y cualquier otra excepción no manejada) en un…, call_apertura(), ClaraError, _post(), Exception, Cliente HTTP hacia los webhooks fijos de Clara en n8n: `/clara/apertura`…, Cualquier fallo hablando con los webhooks de Clara: timeout, HTTP >=400, o… (+4 more)

### Community 8 - "grades.py"
Cohesion: 0.53
Nodes (5): _ags_service_for_course(), _get_or_create_lineitem_url(), mark_activity_completed(), Nota de completitud al gradebook de Canvas vía LTI Assignment and Grade…, Manda 100% (completo/incompleto) a Canvas para este estudiante. Nunca propaga…

### Community 9 - "Handler"
Cohesion: 0.33
Nodes (3): BaseHTTPRequestHandler, Handler, Servidor mínimo para simular el webhook /clara de n8n durante pruebas locales.

## Knowledge Gaps
- **13 isolated node(s):** `Migration`, `Migration`, `Migration`, `Migration`, `Migration` (+8 more)
  These have ≤1 connection - possible missing edges or undocumented components. (Counts symbols only; 139 node(s) total have ≤1 connection when file, concept and rationale nodes are included.)
- **20 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `ClaraMoment` connect `chat/views.py` to `lti_tool/views.py`?**
  _High betweenness centrality (0.057) - this node is a cross-community bridge._
- **Why does `PromptTemplate` connect `chat/views.py` to `seed_demo.py`?**
  _High betweenness centrality (0.038) - this node is a cross-community bridge._
- **Why does `CourseEnrollment` connect `seed_demo.py` to `lti_tool/admin.py`, `lti_tool/views.py`?**
  _High betweenness centrality (0.026) - this node is a cross-community bridge._
- **Are the 5 inferred relationships involving `ClaraMoment` (e.g. with `ClaraMomentSerializer` and `ClaraReplyCreateSerializer`) actually correct?**
  _`ClaraMoment` has 5 INFERRED edges - model-reasoned connections that need verification._
- **Are the 4 inferred relationships involving `PromptTemplate` (e.g. with `Command` and `PromptTemplateSerializer`) actually correct?**
  _`PromptTemplate` has 4 INFERRED edges - model-reasoned connections that need verification._
- **Are the 4 inferred relationships involving `TokenUsageLedger` (e.g. with `TokenUsageLedgerAdmin` and `get_usage_status()`) actually correct?**
  _`TokenUsageLedger` has 4 INFERRED edges - model-reasoned connections that need verification._
- **What connects `Migration`, `Migration`, `Migration` to the rest of the system?**
  _13 weakly-connected nodes found - possible documentation gaps or missing edges._