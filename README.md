# Provisions Link

B2B marketplace connecting UK food suppliers with restaurants. Features location-based group buying, real-time updates via WebSockets, FSA integration, and automated vendor payments through Stripe Connect.

**Author**: Vincent Sam Ngobeh  
**GitHub**: [github.com/Vincent-Ngobeh/provisions-link](https://github.com/Vincent-Ngobeh/provisions-link)

---

## 🚀 Live Demo

### Production Deployment

- **Frontend**: [https://provisions-link-frontend.vercel.app/](https://provisions-link-frontend.vercel.app/)
- **Backend API**: [https://provisions-link-production.up.railway.app/](https://provisions-link-production.up.railway.app/)

### API Documentation

- **Swagger UI**: [https://provisions-link-production.up.railway.app/api/docs/](https://provisions-link-production.up.railway.app/api/docs/)
- **ReDoc**: [https://provisions-link-production.up.railway.app/api/redoc/](https://provisions-link-production.up.railway.app/api/redoc/)
- **OpenAPI Schema**: [https://provisions-link-production.up.railway.app/api/schema/](https://provisions-link-production.up.railway.app/api/schema/)

### Test Credentials

**Super Admin**:

```
Email: admin@test.com
Password: SecurePass123!
```

**Vendor Login**:

```
Email: borough.market@vendor.test
Password: vendor123
```

**Buyer Login (Option 1)**:

```
Email: james.chen@buyer.test
Password: buyer123
```

**Buyer Login (Option 2)**:

```
Email: sarah@gmail.com
Password: @Diamond67
```

### Stripe Test Cards

| Scenario          | Card Number           | Expiry          | CVC          |
| ----------------- | --------------------- | --------------- | ------------ |
| **Success**       | `4242 4242 4242 4242` | Any future date | Any 3 digits |
| **Decline**       | `4000 0000 0000 0002` | Any future date | Any 3 digits |
| **Requires Auth** | `4000 0025 0000 3155` | Any future date | Any 3 digits |

---

## ✨ Features

- **Location-Based Group Buying**: Restaurants can join buying groups based on proximity to maximize bulk purchase discounts
- **Real-time Updates**: WebSocket integration for live order updates, group status changes, and notifications
- **FSA Integration**: Automated food hygiene ratings verification for UK vendors
- **Stripe Connect**: Automated vendor payment processing with platform fees
- **PostGIS**: Geographical queries for location-based group matching
- **Product Management**: Full CRUD operations with image upload to AWS S3
- **Vendor Profiles**: Complete vendor onboarding with compliance verification
- **Order Management**: Track orders from creation to delivery with real-time status updates
- **Analytics Dashboard**: Sales metrics, revenue tracking, and performance analytics
- **Unsplash Integration**: Dynamic product image sourcing

---

## 🛠️ Tech Stack

### Backend

- **Framework**: Django 5.1 with Django REST Framework
- **Database**: PostgreSQL with PostGIS extension
- **WebSockets**: Django Channels with Redis
- **Authentication**: JWT (Simple JWT)
- **Task Queue**: Celery with Redis broker + Celery Beat for scheduled tasks
- **File Storage**: AWS S3
- **Payments**: Stripe Connect
- **API Documentation**: drf-spectacular (OpenAPI/Swagger)
- **Server**: Daphne (ASGI)
- **Containerization**: Docker & Docker Compose

### Frontend

- **Framework**: React 19.2 with TypeScript
- **Build Tool**: Vite
- **UI Library**: Radix UI with Tailwind CSS
- **State Management**: TanStack Query (React Query)
- **Forms**: React Hook Form with Zod validation
- **HTTP Client**: Axios
- **Charts**: Recharts
- **Payments**: Stripe.js & Stripe React Components
- **Routing**: React Router DOM

---

## 📋 Prerequisites

- **Docker** & **Docker Compose** (recommended for local development)
- **Python** 3.11+ (if running without Docker)
- **Node.js** 18+ (for frontend development)
- **PostgreSQL** 14+ with PostGIS extension (if running without Docker)
- **Redis** 6+ (if running without Docker)
- **AWS Account** (for S3 storage)
- **Stripe Account** (for payments)

---

## 🏃 Local Development Setup

### Option 1: Docker Setup (Recommended)

This is the **easiest** way to run the project locally. Docker Compose will automatically start:

- PostgreSQL with PostGIS
- Redis
- Django backend with auto-migrations
- Celery worker
- Celery beat scheduler

**1. Clone the repository**:

```bash
git clone https://github.com/Vincent-Ngobeh/provisions-link.git
cd provisions-link
```

**2. Set up environment variables**:

```bash
# Copy the example env file
cp backend/.env.example backend/.env

# Edit backend/.env and add your API keys:
# - AWS credentials (for S3)
# - Stripe keys (use test keys)
# - Other optional services
```

**3. Start all services**:

```bash
# Build and start all containers
docker compose down
docker compose build
docker compose up
```

The backend will be available at `http://localhost:8000`

**4. Seed the database** (in a new terminal):

Run these commands **in order** to populate demo data:

```bash
# 1. Create users (buyers and vendors)
docker compose exec backend python manage.py seed_users

# 2. Create vendor profiles
docker compose exec backend python manage.py seed_vendors

# 3. Create product categories
docker compose exec backend python manage.py seed_categories

# 4. Create products
docker compose exec backend python manage.py seed_products

# 5. Add product images
docker compose exec backend python manage.py seed_product_images

# 6. Create buying groups
docker compose exec backend python manage.py seed_buying_groups

# 7. Create sample orders
docker compose exec backend python manage.py seed_orders
```

**Optional**: Clear existing data before seeding:

```bash
docker compose exec backend python manage.py seed_users --clear
docker compose exec backend python manage.py seed_vendors --clear
# ... etc
```

### Additional Utility Commands

**Update FSA Ratings** (for vendors with online FSA establishment IDs):

```bash
# Update all vendors with FSA IDs
docker compose exec backend python manage.py update_fsa_ratings

# Update a specific vendor by ID
docker compose exec backend python manage.py update_fsa_ratings --vendor-id 1

# Force update even if recently checked
docker compose exec backend python manage.py update_fsa_ratings --force

# Show detailed output
docker compose exec backend python manage.py update_fsa_ratings --verbose
```

**Reseed a Specific Product Image**:

```bash
# Reseed with default search query
docker compose exec backend python manage.py reseed_product_image --product-name "Jerk Chicken Pieces"

# Reseed with custom search query
docker compose exec backend python manage.py reseed_product_image --product-name "Jerk Chicken Pieces" --search-query "jerk chicken caribbean grilled"
```

**5. Create a superuser** (optional):

```bash
docker compose exec backend python manage.py createsuperuser
```

**6. Access the application**:

- **Django Admin**: http://localhost:8000/admin/
- **Swagger UI**: http://localhost:8000/api/docs/
- **ReDoc**: http://localhost:8000/api/redoc/
- **OpenAPI Schema**: http://localhost:8000/api/schema/

---

### Option 2: Manual Setup (Without Docker)

<details>
<summary>Click to expand manual setup instructions</summary>

#### Backend Setup

**1. Create and activate virtual environment**:

```bash
cd backend
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

**2. Install dependencies**:

```bash
pip install -r requirements.txt
```

**3. Set up environment variables**:

- Copy `backend/.env.example` to `backend/.env`
- Update database and Redis connection details
- Add your API keys

**4. Set up PostGIS database**:

```bash
# Create database
createdb provisions_link

# Enable PostGIS extension
psql provisions_link -c "CREATE EXTENSION postgis;"
```

**5. Run migrations**:

```bash
python manage.py migrate
```

**6. Create superuser**:

```bash
python manage.py createsuperuser
```

**7. Run development server**:

```bash
python manage.py runserver
```

**8. In separate terminals, run**:

```bash
# Terminal 2: Redis
redis-server

# Terminal 3: Celery worker
celery -A provisions_link worker -l info

# Terminal 4: Celery beat
celery -A provisions_link beat -l info
```

**9. Seed the database** (in order):

```bash
python manage.py seed_users
python manage.py seed_vendors
python manage.py seed_categories
python manage.py seed_products
python manage.py seed_product_images
python manage.py seed_buying_groups
python manage.py seed_orders
```

</details>

---

### Frontend Setup

**1. Navigate to frontend directory**:

```bash
cd frontend
```

**2. Install dependencies**:

```bash
npm install
```

**3. Set up environment variables**:

```bash
# Copy the example env file
cp .env.example .env
```

Edit `frontend/.env`:

```bash
# For local development with Docker
VITE_API_BASE_URL=http://localhost:8000/api/v1
VITE_WS_BASE_URL=ws://localhost:8000/ws

# For testing against production backend
# VITE_API_BASE_URL=https://provisions-link-production.up.railway.app/api/v1
# VITE_WS_BASE_URL=wss://provisions-link-production.up.railway.app/ws
```

**4. Run development server**:

```bash
npm run dev
```

The frontend will be available at `http://localhost:5173`

---

## 🌐 Deployment

### Backend (Railway)

The backend is deployed on **Railway** using Docker.

**Environment Variables** (set in Railway dashboard):

```bash
# Django
SECRET_KEY=<generate-secure-key>
DJANGO_SETTINGS_MODULE=provisions_link.settings.production
DEBUG=False

# Database (Railway provides this automatically)
DATABASE_URL=postgresql://user:password@host:port/database

# Redis (Railway provides this automatically)
REDIS_URL=redis://default:password@host:port

# CORS & Security
ALLOWED_HOSTS=provisions-link-production.up.railway.app
CORS_ALLOWED_ORIGINS=https://provisions-link-frontend.vercel.app

# AWS S3
AWS_ACCESS_KEY_ID=<your-key>
AWS_SECRET_ACCESS_KEY=<your-secret>
AWS_STORAGE_BUCKET_NAME=provisions-link-media
AWS_STATIC_BUCKET_NAME=provisions-link-static
AWS_S3_REGION_NAME=eu-west-2

# Stripe
STRIPE_PUBLISHABLE_KEY=pk_live_...
STRIPE_SECRET_KEY=sk_live_...
STRIPE_WEBHOOK_SECRET=whsec_...
STRIPE_PLATFORM_ACCOUNT_ID=acct_...
FRONTEND_URL=https://provisions-link-frontend.vercel.app

# External APIs
MAPBOX_API_TOKEN=<your-token>
UNSPLASH_ACCESS_KEY=<your-key>
UNSPLASH_SECRET_KEY=<your-secret>

# Optional
SENTRY_DSN=<your-sentry-dsn>
```

**Deployment Steps**:

1. Connect Railway to your GitHub repository
2. Railway auto-detects `Dockerfile` (in root directory) and `railway.json`
3. Add PostgreSQL and Redis services
4. Set environment variables
5. Deploy

**Auto-Deployment**:
Railway automatically redeploys when you push to the main branch. To trigger a redeployment:

```bash
git push origin main
```

**Post-Deployment**:

```bash
# Run migrations (using Railway CLI)
railway run python manage.py migrate

# Create superuser
railway run python manage.py createsuperuser

# Run seed commands (optional for demo data)
railway run python manage.py seed_users
railway run python manage.py seed_vendors
# ... etc
```

---

### Frontend (Vercel)

The frontend is deployed on **Vercel**.

**Environment Variables** (set in Vercel dashboard):

```bash
VITE_API_BASE_URL=https://provisions-link-production.up.railway.app/api/v1
VITE_WS_BASE_URL=wss://provisions-link-production.up.railway.app/ws
```

**Deployment Steps**:

1. Connect Vercel to your GitHub repository
2. Set root directory to `frontend`
3. Vercel auto-detects Vite configuration
4. Add environment variables
5. Deploy

**Auto-Deployment**:
Vercel automatically redeploys the frontend when you push to the main branch. To trigger a redeployment:

```bash
git push origin main
```

The `frontend/vercel.json` configuration ensures proper SPA routing.

---

## 📁 Project Structure

```
provisions-link/
├── backend/
│   ├── apps/
│   │   ├── core/              # User authentication, base models
│   │   ├── vendors/           # Vendor management, FSA integration
│   │   ├── products/          # Product catalog, categories
│   │   ├── buying_groups/     # Group buying functionality
│   │   ├── orders/            # Order management
│   │   ├── payments/          # Stripe Connect integration
│   │   └── integrations/      # FSA, Unsplash APIs
│   ├── provisions_link/
│   │   ├── settings/          # Environment-specific settings
│   │   │   ├── base.py
│   │   │   ├── development.py
│   │   │   └── production.py
│   │   ├── asgi.py            # ASGI configuration
│   │   └── urls.py            # URL routing
│   ├── requirements.txt
│   ├── .env.example
│   └── manage.py
├── frontend/
│   ├── src/
│   │   ├── components/        # Reusable UI components
│   │   ├── pages/             # Route pages
│   │   ├── services/          # API services
│   │   ├── hooks/             # Custom React hooks
│   │   ├── lib/               # Utilities
│   │   └── types/             # TypeScript types
│   ├── vercel.json            # Vercel deployment config
│   ├── vite.config.ts
│   └── package.json
├── Dockerfile                 # Railway deployment (root directory)
├── docker-compose.yml         # Local development
└── README.md
```

---

## 🧪 Testing

### Backend Tests

```bash
# Using Docker
docker compose exec backend python manage.py test

# Without Docker
cd backend
python manage.py test
```

### Frontend Tests

```bash
cd frontend
npm run test
```

### Linting

```bash
# Backend
cd backend
flake8 .

# Frontend
cd frontend
npm run lint
```

---

## 📚 API Documentation

### Local Development

- **Swagger UI (interactive)**: http://localhost:8000/api/docs/
- **ReDoc (beautiful layout)**: http://localhost:8000/api/redoc/
- **OpenAPI Schema (raw JSON)**: http://localhost:8000/api/schema/

### Production

- **Swagger UI**: https://provisions-link-production.up.railway.app/api/docs/
- **ReDoc**: https://provisions-link-production.up.railway.app/api/redoc/
- **OpenAPI Schema**: https://provisions-link-production.up.railway.app/api/schema/

---

## 🔒 Security Features

- JWT-based authentication with token refresh
- CORS configuration
- CSRF protection
- HTTPS enforcement in production
- HSTS headers
- Secure cookie settings
- SQL injection protection (Django ORM)
- XSS protection
- Rate limiting
- Secure password hashing (PBKDF2)

---

## 🎯 Key Integrations

### Food Standards Agency (FSA)

- Automatic vendor hygiene rating verification
- Real-time rating updates
- UK-specific food safety compliance

### Stripe Connect

- Platform-level payment processing
- Automated vendor payouts
- Commission-based revenue model
- Test mode for development

### AWS S3

- Scalable media storage
- Static file hosting
- Secure file access

### Unsplash

- High-quality product images
- Dynamic image sourcing

---

## 🐳 Docker Services

When running `docker compose up`, the following services start:

| Service           | Description                     | Port        |
| ----------------- | ------------------------------- | ----------- |
| **db**            | PostgreSQL 14 with PostGIS      | 5433 → 5432 |
| **redis**         | Redis 7 (for Channels & Celery) | 6379        |
| **backend**       | Django + Daphne ASGI server     | 8000        |
| **celery_worker** | Celery worker for async tasks   | N/A         |
| **celery_beat**   | Celery beat for scheduled tasks | N/A         |

---

## 🚧 Troubleshooting

### Docker Issues

**Issue**: Containers won't start

```bash
# Stop and remove all containers
docker compose down -v

# Rebuild from scratch
docker compose build --no-cache
docker compose up
```

**Issue**: Database connection errors

```bash
# Check if db service is healthy
docker compose ps

# Check logs
docker compose logs db
```

### Migration Issues

**Issue**: Migration conflicts

```bash
docker compose exec backend python manage.py migrate --fake
docker compose exec backend python manage.py migrate
```

### Port Conflicts

**Issue**: Port 8000 already in use

```bash
# Kill existing process on port 8000
# Linux/Mac:
lsof -ti:8000 | xargs kill -9

# Windows:
netstat -ano | findstr :8000
taskkill /PID <PID> /F
```

---

## 📝 License

This project is proprietary software.

---

## 👥 Contributing

This is a portfolio project. For inquiries, please contact Vincent Sam Ngobeh via GitHub.

---

## 📧 Contact & Support

**Author**: Vincent Sam Ngobeh  
**GitHub**: [github.com/Vincent-Ngobeh/provisions-link](https://github.com/Vincent-Ngobeh/provisions-link)

For issues or questions, please open an issue on GitHub.

---

## 🙏 Acknowledgments

- Built with Django REST Framework and React
- Deployed on Railway (backend) and Vercel (frontend)
- Integrates with Stripe, AWS S3, FSA API, and Unsplash
