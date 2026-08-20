# 🚀 Dracara Growth OS

> A purpose-built Deal Flow Command Center engineered for high-value software project sales cycles.

![License](https://img.shields.io/badge/license-MIT-blue.svg)
![Next.js](https://img.shields.io/badge/Next.js-16-black?logo=next.js)
![FastAPI](https://img.shields.io/badge/FastAPI-0.100+-009688?logo=fastapi)
![Supabase](https://img.shields.io/badge/Supabase-DB-3ECF8E?logo=supabase)

Dracara Growth OS is not a generic CRM. While platforms like Salesforce, HubSpot, or Zoho are designed for volume B2C sales, Growth OS is specifically tailored for software services and consulting agencies. It manages everything from the first cold outreach to final delivery handoff and upsell, replacing fragmented spreadsheets, WhatsApp notes, and calendar hacks.

## ✨ Key Features

- **🎯 9-Stage Lead Pipeline:** Kanban board tailored for software services (Prospect → Delivery Transition).
- **🧠 Founder CRM Profile:** Comprehensive business intelligence including pain points, tech stack, budget hints, and decision makers.
- **⚡ Follow-Up Engine:** Intelligent daily queues, overdue alerts, and a 14-day no-touch rule to ensure zero lead slippage.
- **📅 Google Calendar Integration:** Two-way sync with auto-follow-up triggers based on meeting outcomes.
- **🤝 Multi-Agent Management:** Role-based access (Admin, SDR, Sales Partner) with performance tracking and audit trails.
- **📄 Proposal & Requirements Tracker:** Versioned scope documents, Figma/GitHub links, and PDF proposal storage.
- **📈 Opportunity Scoring:** Configurable weighted scoring (0-100) to prioritize high-value deals.
- **📊 Founder Dashboard:** Cockpit view of pipeline value, revenue forecasts, and urgent tasks.

## 🏗️ Architecture & Tech Stack

This project uses a decoupled client-server architecture within a **Turborepo** monorepo:

### Frontend (`apps/web`)
- **Framework:** Next.js 16 (App Router)
- **Language:** TypeScript
- **Styling:** Tailwind CSS + shadcn/ui
- **State Management:** TanStack Query v5

### Backend (`apps/api` & `apps/worker`)
- **Framework:** FastAPI (Python 3.12)
- **Background Jobs:** Celery + Redis
- **Database:** Supabase (PostgreSQL 15) with Row-Level Security (RLS)
- **Storage:** Supabase Storage
- **Auth:** Supabase Auth (JWT, OAuth)

## 📂 Repository Structure

```text
crm-lite/
├── apps/
│   ├── web/          # Next.js frontend application
│   ├── api/          # FastAPI backend REST API
│   └── worker/       # Celery background workers
├── packages/
│   ├── types/        # Shared TypeScript types & Pydantic schemas
│   └── ui/           # Shared shadcn/ui React components
├── supabase/
│   └── migrations/   # Database schemas and RLS policies
└── scripts/          # Utility and database seeding scripts
```

## 🚀 Getting Started

### Prerequisites
- Node.js (v18+)
- pnpm (v8+)
- Python (3.12+)
- Supabase CLI
- Redis (for Celery)

### 1. Clone the repository
```bash
git clone https://github.com/danushtom/crm-lite.git
cd crm-lite
```

### 2. Install Dependencies
```bash
# Install frontend & monorepo dependencies
pnpm install

# Install backend dependencies
cd apps/api
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 3. Environment Setup
Copy the `.env.example` files to `.env` in the root and respective app directories. Update the variables with your Supabase and Google Calendar API credentials.
```bash
cp .env.example .env
cp apps/web/.env.example apps/web/.env
```

### 4. Database Initialization
Use the Supabase CLI to start the local database and apply migrations:
```bash
supabase start
supabase db reset
```

### 5. Run the Application
Start the development servers across the monorepo:
```bash
pnpm dev
```
Start the backend server (in a separate terminal):
```bash
cd apps/api
source .venv/bin/activate
uvicorn app.main:app --reload
```

## 📜 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## 🤝 Contributing

Contributions are welcome! Whether it's reporting a bug, discussing a feature, or submitting a pull request, we appreciate your input.
