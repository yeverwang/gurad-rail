# Web Contract Editor

A web-based interface for editing and managing Guardrail Engine contracts.

## Features

- 📝 **YAML Editor**: Syntax-highlighted editor with auto-validation
- ✅ **Real-time Validation**: Instant feedback on contract validity
- 👁️ **Live Preview**: See contract structure as you edit
- 📋 **Template System**: Start from pre-built contract templates
- 💾 **Save & Load**: Manage multiple contract files
- 🗑️ **Delete Contracts**: Remove outdated contracts safely

## Quick Start

### 1. Install Dependencies

```bash
pip install -r requirements.txt
```

### 2. Run the Web Server

```bash
python web_editor.py
```

### 3. Open in Browser

Navigate to: **http://localhost:5000**

## Usage

### Creating a New Contract

1. Click **"➕ New Contract"** on the main page
2. Enter a filename (e.g., `my_agent.yaml`)
3. Click **"📋 Load Template"** to start with a template
4. Edit the YAML content in the editor
5. Click **"✓ Validate"** to check for errors
6. Click **"💾 Save"** to save the contract

### Editing an Existing Contract

1. Click **"✏️ Edit"** on any contract card
2. Make your changes in the editor
3. Validation happens automatically as you type
4. Click **"💾 Save"** when done

### Keyboard Shortcuts

- **Ctrl/Cmd + S**: Save contract
- **Ctrl/Cmd + K**: Validate contract

## API Endpoints

The web editor exposes a REST API:

### GET `/api/contracts`
List all contracts

**Response:**
```json
[
  {
    "filename": "payment_agent.yaml",
    "contract_id": "fintech/payment-agent/v2.1.0",
    "version": "2.1.0",
    "status": "active",
    "path": "contracts/payment_agent.yaml"
  }
]
```

### GET `/api/contract/<filename>`
Get contract content

**Response:**
```json
{
  "filename": "payment_agent.yaml",
  "content": "metadata:\n  contract_id: ...",
  "data": { /* parsed YAML */ }
}
```

### POST `/api/contract/<filename>`
Save/update contract

**Request:**
```json
{
  "content": "metadata:\n  contract_id: ..."
}
```

**Response:**
```json
{
  "success": true,
  "message": "Contract saved successfully",
  "validation": {
    "valid": true,
    "contract_id": "...",
    "version": "...",
    "status": "..."
  }
}
```

### POST `/api/contract/new`
Create new contract

**Request:**
```json
{
  "filename": "new_contract.yaml",
  "content": "metadata:\n  ..."
}
```

### DELETE `/api/contract/<filename>`
Delete contract

**Response:**
```json
{
  "success": true,
  "message": "Contract deleted successfully"
}
```

### POST `/api/validate`
Validate contract without saving

**Request:**
```json
{
  "content": "metadata:\n  ..."
}
```

**Response:**
```json
{
  "valid": true,
  "message": "Contract is valid",
  "contract_id": "...",
  "version": "...",
  "status": "..."
}
```

### GET `/api/template`
Get contract template

**Response:**
```json
{
  "content": "metadata:\n  contract_id: example/new-agent/v1.0.0\n  ..."
}
```

## Architecture

```
web_editor.py (Flask App)
    ├── templates/
    │   ├── index.html      # Main contract list page
    │   └── editor.html     # Contract editor page
    ├── static/
    │   ├── css/
    │   │   └── style.css   # Styling
    │   └── js/
    │       └── main.js     # Client-side utilities
    └── contracts/          # Contract YAML files
```

## Technology Stack

- **Backend**: Flask (Python web framework)
- **Frontend**: Vanilla JavaScript + HTML5 + CSS3
- **YAML Editor**: CodeMirror 5
- **Validation**: Pydantic v2
- **Parsing**: PyYAML

## Configuration

Edit `web_editor.py` to customize:

```python
# Change contracts directory
CONTRACTS_DIR = Path("contracts")

# Change server port
app.run(debug=True, host='0.0.0.0', port=5000)
```

## Security Notes

⚠️ **Development Mode Only**

This web editor is designed for development and testing. For production use:

1. Disable Flask debug mode
2. Add authentication/authorization
3. Use a production WSGI server (gunicorn, uwsgi)
4. Add HTTPS/TLS
5. Implement CSRF protection
6. Add rate limiting

## Troubleshooting

### Port Already in Use

If port 5000 is busy, change the port:

```python
app.run(debug=True, host='0.0.0.0', port=8080)
```

### Contracts Not Loading

Check that the `contracts/` directory exists and contains valid YAML files.

### Validation Errors

Ensure your contract follows the schema defined in `guardrail/models.py`. Use the template as a reference.

## Integration with Guardrail Engine

Contracts edited in the web interface are immediately available to the Guardrail Engine:

```python
from guardrail import AgenticGateway

# Load contract edited in web UI
gateway = AgenticGateway.from_file("contracts/my_agent.yaml")

# Evaluate as normal
result = gateway.evaluate(context)
```

## Contributing

When adding features to the web editor:

1. Add API endpoints in `web_editor.py`
2. Update templates in `templates/`
3. Add styles in `static/css/style.css`
4. Add client-side logic in `static/js/main.js`
5. Update this README

---

**Main Documentation**: See `README.md` for Guardrail Engine documentation
**Development Guide**: See `CLAUDE.md` for detailed development instructions
