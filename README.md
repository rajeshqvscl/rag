# FinRAG - Venture Intelligence Platform

A fully functional AI-powered financial analysis and venture capital intelligence platform with comprehensive RAG capabilities, document analysis, and portfolio management features.

## 🚀 Features

### Core Functionality
- **Document Analysis**: Upload and analyze pitch decks, financial models, and documents with AI-powered insights
- **RAG Intelligence**: Query financial data with semantic search and symbol-filtered results
- **Portfolio Management**: Track portfolio performance, benchmarks, and company data
- **Compliance & ESG**: Monitor ESG metrics and compliance status
- **Integrations**: Manage connections to HubSpot, Salesforce, Slack, Gmail, GitHub
- **Settings**: Configure API keys and models

### Technical Capabilities
- **Enhanced PDF/Document Extraction**: Support for PDF, DOCX, XLSX, CSV, TXT files
- **Comprehensive Financial Analysis**: Revenue extraction, growth metrics, business model detection
- **Technical KPI Extraction**: User metrics, churn rates, conversion rates, ARPU, LTV/CAC ratios
- **Market Analysis**: TAM/SAM/SOM extraction, competitive landscape analysis
- **Risk Assessment**: Burn rate, runway, debt structure analysis
- **Fallback Analysis**: Robust analysis even when external APIs are unavailable

## 🏗️ Architecture

### Backend (FastAPI)
- **Port**: 9000
- **Authentication**: X-API-KEY header (default: `finrag_at_2026`)
- **Framework**: FastAPI with Uvicorn
- **AI Model**: Anthropic Claude with enhanced fallback analysis

### Frontend (Vanilla JS)
- **Framework**: Vanilla JavaScript with modern UI
- **Styling**: Custom CSS with Lucide icons and Chart.js
- **Architecture**: Single-page application with section-based navigation

### Data Storage
- **Vector Store**: FAISS for semantic search
- **File Storage**: JSON-based for settings, library, chat memory
- **Document Storage**: Local file system with PDF/DOCX extraction

## 📦 Installation

### Prerequisites
- Python 3.10+
- pip
- Modern web browser

### Backend Setup

```bash
cd backend
pip install -r requirements.txt
```

### Environment Variables
Create a `.env` file in the backend directory:

```env
ANTHROPIC_API_KEY=your_anthropic_api_key_here
CLAUDE_MODEL=claude-3-sonnet-20240229
```

### Frontend Setup
The frontend is served directly by the backend, no additional setup needed.

## 🚀 Running the Application

### Start Backend Server

```bash
cd backend
python -m uvicorn app.main:app --host 127.0.0.1 --port 9000 --reload
```

### Access Application
Open your browser and navigate to:
```
http://localhost:9000
```

## 📡 API Endpoints

### Document Analysis
- `POST /email-webhook` - Upload and analyze documents
- `GET /query` - Query RAG system with optional symbol filtering

### Financial Data
- `GET /fin/ingest?symbol={symbol}` - Ingest financial data for a symbol

### Library Management
- `GET /library` - Get all processed documents
- `POST /library/add` - Add document to library
- `DELETE /library/{company}` - Remove document from library

### Portfolio Management
- `GET /portfolio/stats` - Get portfolio statistics
- `GET /portfolio/benchmarks` - Get portfolio benchmarks
- `GET /portfolio/companies` - Get portfolio companies

### Compliance
- `GET /compliance/esg` - Get ESG compliance report
- `GET /compliance/legal` - Get legal compliance status

### Integrations
- `GET /integrations` - Get all integration statuses
- `GET /integrations/{name}` - Get specific integration status
- `POST /integrations/{name}/connect` - Connect integration
- `POST /integrations/{name}/disconnect` - Disconnect integration

### Settings
- `GET /settings` - Get all settings
- `POST /settings/update` - Update settings

### AI Agent
- `GET /agent/chat?q={query}&session_id={id}` - Chat with AI agent

## 🔒 Authentication

All API endpoints require API key authentication via the `X-API-KEY` header:
```http
X-API-KEY: finrag_at_2026
```

## 📊 Data Persistence

### Storage Locations
- **Settings**: `backend/app/data/settings.json`
- **Library**: `backend/app/data/library.json`
- **Chat Memory**: `backend/app/data/chat_memory.json`
- **Projections**: `backend/app/data/projections.json`
- **Documents**: `backend/app/data/documents/`
- **Uploads**: `backend/app/data/uploads/`
- **Vector Index**: `backend/app/data/faiss_index/`

## 🛠️ Configuration

### API Keys
Update API keys in the Settings section or directly in `backend/app/data/settings.json`

### Model Configuration
Configure the active Claude model in Settings or via environment variable:
```env
CLAUDE_MODEL=claude-3-sonnet-20240229
```

## 🧪 Testing

### Test All Endpoints
```bash
cd backend
python -c "
import requests
headers = {'X-API-KEY': 'finrag_at_2026'}
endpoints = ['/library', '/portfolio/stats', '/compliance/esg', '/integrations', '/settings']
for endpoint in endpoints:
    response = requests.get(f'http://localhost:9000{endpoint}', headers=headers)
    print(f'{endpoint}: {response.status_code}')
"
```

### Test Document Upload
```bash
curl -X POST http://localhost:9000/email-webhook \
  -H "X-API-KEY: finrag_at_2026" \
  -F "company=TestCompany" \
  -F "files=@test_document.pdf"
```

## 🐛 Troubleshooting

### Common Issues

**Claude API 404 Errors**
- Ensure ANTHROPIC_API_KEY is set correctly
- Check if the model name is correct in settings
- The system has fallback analysis enabled

**File Upload Issues**
- Verify file format is supported (PDF, DOCX, XLSX, CSV, TXT)
- Check file size limits
- Ensure backend server is running

**CORS Errors**
- Verify CORS is configured in `backend/app/main.py`
- Check API key is included in headers

**Data Persistence Issues**
- Ensure `backend/app/data/` directory exists
- Check file permissions
- Verify JSON file formatting

## 📈 Performance

### System Requirements
- **CPU**: 2+ cores recommended
- **RAM**: 4GB minimum, 8GB recommended
- **Storage**: 500MB minimum for data storage

### Optimization Tips
- Use mock data fallback for rate-limited APIs
- Implement caching for frequently accessed data
- Monitor memory usage with large document uploads

## 🔧 Development

### Project Structure
```
fin_rag/
├── backend/
│   ├── app/
│   │   ├── main.py              # FastAPI application
│   │   ├── routes/              # API endpoints
│   │   ├── services/            # Business logic
│   │   └── data/                # Data storage
│   └── requirements.txt         # Python dependencies
├── frontend/
│   ├── index.html              # Main UI
│   ├── app.js                  # Frontend logic
│   └── style.css               # Styling
└── README.md                   # This file
```

### Adding New Features
1. Create route in `backend/app/routes/`
2. Add service logic in `backend/app/services/`
3. Update frontend in `frontend/app.js`
4. Register route in `backend/app/main.py`
5. Test endpoints with API key authentication

## 📝 License

This project is proprietary and confidential.

## 👥 Support

For issues and questions, contact the development team.

---

**FinRAG v4.6** - Venture Intelligence Platform
Built with FastAPI, Claude AI, and Modern Web Technologies
