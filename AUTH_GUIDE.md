# FinRAG Authentication Guide

## Overview
FinRAG now has a complete authentication system with:
- **Manual Login** (email/password with JWT tokens)
- **Google OAuth** (Sign in with Google)
- **User Registration** with form validation
- **Protected Routes** requiring authentication

## Files Created/Modified

### Backend
| File | Purpose |
|------|---------|
| `backend/app/services/google_oauth_service.py` | Google OAuth integration |
| `backend/app/services/auth_service.py` | Added `get_or_create_oauth_user()` method |
| `backend/app/routes/auth.py` | Added `/auth/google/login` and `/auth/google/callback` endpoints |
| `backend/app/models/database.py` | Added `oauth_provider` and `oauth_provider_id` columns |
| `backend/.env.example` | Added Google OAuth configuration template |
| `backend/migrate_oauth.py` | Database migration script for OAuth columns |

### Frontend
| File | Purpose |
|------|---------|
| `frontend/login.html` | Modern login page with manual + Google login |
| `frontend/register.html` | User registration page |
| `frontend/app.js` | Added authentication state management |
| `frontend/index.html` | Added user profile dropdown with logout |

## Setup Instructions

### 1. Install Dependencies
```bash
cd backend
pip install python-jose[cryptography] authlib itsdangerous psycopg2-binary
```

### 2. Configure Google OAuth (Optional)
1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Create a new project or select existing
3. Go to "APIs & Services" > "Credentials"
4. Click "Create Credentials" > "OAuth client ID"
5. Configure consent screen (External for testing)
6. Add authorized redirect URI: `http://localhost:9000/auth/google/callback`
7. Copy Client ID and Client Secret to `.env`:

```bash
# backend/.env
GOOGLE_CLIENT_ID=your-client-id.apps.googleusercontent.com
GOOGLE_CLIENT_SECRET=your-client-secret
GOOGLE_REDIRECT_URI=http://localhost:9000/auth/google/callback
```

### 3. Run Database Migration
```bash
cd backend
python migrate_oauth.py
```

### 4. Start the System
```bash
# Start backend
cd backend
python -m uvicorn app.main:app --host 0.0.0.0 --port 9000

# In another terminal, start frontend
cd frontend
python -m http.server 8000
```

## Authentication Flow

### Manual Login
1. User visits `http://localhost:8000/login.html`
2. Enters username/email and password
3. Frontend calls `POST /auth/login`
4. Backend validates credentials and returns JWT tokens
5. Tokens stored in localStorage
6. User redirected to `index.html`

### Google OAuth
1. User clicks "Sign in with Google" on login page
2. Frontend calls `GET /auth/google/login`
3. Backend returns Google authorization URL
4. User redirected to Google consent screen
5. After approval, Google redirects to `/auth/google/callback`
6. Backend exchanges code for user info
7. User created/linked in database
8. JWT tokens returned and stored
9. User redirected to `index.html`

### Registration
1. User visits `http://localhost:8000/register.html`
2. Fills in form (full name, username, email, password)
3. Frontend calls `POST /auth/register`
4. User created in database
5. Success message shown, redirected to login

### Protected Routes
- All API calls now include `Authorization: Bearer <token>` header
- If token expires, user is redirected to login
- Manual logout clears all tokens and redirects to login

## API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/auth/register` | POST | Create new user account |
| `/auth/login` | POST | Login with credentials |
| `/auth/refresh` | POST | Refresh access token |
| `/auth/me` | GET | Get current user info |
| `/auth/google/login` | GET | Get Google OAuth URL |
| `/auth/google/callback` | GET | OAuth callback handler |
| `/auth/init-admin` | POST | Create default admin user |

## Default Credentials
If no users exist, an admin user is auto-created:
- **Username**: `admin`
- **Password**: `admin123`
- **Email**: `admin@finrag.com`

⚠️ **Change this in production!**

## Security Features
- Passwords hashed with SHA-256
- JWT tokens with 30-minute expiry
- Refresh tokens with 7-day expiry
- Automatic token refresh handling
- Protected routes requiring valid tokens
- CSRF protection on OAuth flow

## Testing

### Test Manual Login
1. Register at `http://localhost:8000/register.html`
2. Login at `http://localhost:8000/login.html`
3. Verify you're redirected to `index.html`
4. Check user avatar shows in header
5. Click avatar to see dropdown with logout
6. Click logout and verify redirect to login

### Test Google OAuth (if configured)
1. Login page > Click "Sign in with Google"
2. Complete Google authentication
3. Verify redirect to app with new user created

## Troubleshooting

### "Token expired" errors
- Tokens auto-refresh, but if refresh fails, user is logged out
- Clear localStorage and login again

### Google OAuth not working
- Check GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET in .env
- Verify redirect URI matches Google Console settings
- Ensure backend is running on port 9000

### Database errors
- Run `python migrate_oauth.py` to add OAuth columns
- Check DATABASE_URL is set correctly in .env

## Next Steps
- Add email verification for new registrations
- Implement password reset via email
- Add more OAuth providers (GitHub, Microsoft)
- Add user roles and permissions
- Implement session management UI
