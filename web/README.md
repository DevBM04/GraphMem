# GraphMem Web UI

A React + JavaScript frontend for GraphMem repository issue localization, built with Vite.

## Requirements

- Node.js and npm
- GraphMem FastAPI backend

## Installation

From the repository root:

```bash
cd web
npm install
```

## Configuration

Create a `web/.env` file:

```dotenv
VITE_API_URL=http://127.0.0.1:8000
VITE_USE_MOCK=false
```

The frontend uses the live API by default.

## Run the frontend

```bash
npm run dev
```

Open the URL printed by Vite, normally http://localhost:5173.

## Run the backend

From the repository root, in a separate terminal:

```bash
source venv/bin/activate
pip install -e .
uvicorn graphmem.api.main:app --reload
```

The API runs at http://127.0.0.1:8000.

## API endpoints

- `GET /repos`
- `GET /configs`
- `POST /localize`
- `GET /code`

## Production build

```bash
npm run build
```

Production assets are generated in `dist/`.

## Troubleshooting

- Ensure the backend is running if API requests fail.
- Verify `VITE_API_URL` matches the backend address.
- The backend allows the frontend origin `http://localhost:5173`.
- Restart Vite after changing environment variables.
- Check the browser console and terminal for errors.
