# Agent Router

Pilih agent atau skill yang paling sesuai untuk setiap bagian pekerjaan.

## Workflow

```
Request
  ↓
Understand Intent
  ↓
Identify Work Type
  ↓
Check Available Agents
  ↓
Select Agent
  ↓
Assign Task
```

## Routing

Gunakan agent terspecialisasi bila tersedia.

```
Research      → Research Agent
Planning      → Planner Agent
UI/UX         → Design Agent
Frontend      → Frontend Agent
Backend       → Backend Agent
Coding        → Coding Agent
Debugging     → Debug Agent
Testing       → Testing Agent
Review        → Review Agent
Security      → Security Agent
Deployment    → Deployment Agent
```

## Rules

- Prefer agent terspecialisasi yang paling mampu.
- JANGAN buat agent baru bila yang sudah ada bisa mengerjakan task.
- JANGAN route hanya berdasar keyword.
- Pertimbangkan dependencies dan konteks project.
- Jaga routing tetap sederhana untuk request sederhana.
- Gunakan multiple agent hanya bila parallel work memberikan nilai nyata.

## Fallback

Jika tidak ada agent terspecialisasi:

```
Specialized Agent
  ↓
General Coding Agent
```

## Final Principle

Gunakan jumlah agent yang mampu sesedikit mungkin untuk menyelesaikan pekerjaan.
