# Dreamserver

Dreamserver is a personal, single-user dream journal. It provides:

- A FastAPI backend for audio and text dream entries.
- Background French transcription with Faster Whisper.
- Optional Ollama/Mistral correction and interpretation.
- Search, tags, statistics, weekly digests, and a Dream Map.
- A React/Vite Progressive Web App (PWA) for recording and reviewing dreams.
- Optional Web Push notifications when transcription finishes.

The intended companion device is [DreamCatcher](https://github.com/B-Moth/Dreamcatcher), an alarm clock that records audio and uploads it to Dreamserver. This repository contains the server and PWA, not the DreamCatcher hardware or firmware.

## How the system works

1. DreamCatcher or the PWA uploads audio to `POST /upload`, or the user creates a text entry in the PWA.
2. Dreamserver stores each entry as a directory containing `meta.json`, audio, and transcript files.
3. A background worker transcribes audio with Faster Whisper and optionally runs correction with Ollama.
4. The PWA reads the entry, lets the user edit and tag it, and requests interpretations or weekly summaries when needed.
5. Derived data such as interpretations, digest summaries, semantic groups, the vocabulary, and the user profile is stored on the server filesystem.

This is a file-backed personal service, not a multi-user application. The API key, CORS policy, and default paths should be hardened before exposing it outside a trusted network.

## Repository and deployment layout

The source checkout is the development and review base. The current application expects the deployed tree at `~/dreamserver`:

```text
~/dreamserver/
	api/
	config/
		mistral_inputs.yaml
	notifications/
	pipeline/
	pwa/
		dist/
	config.yaml
	storage/
```

Copy or install the repository into that location for the current path conventions to work. The checked-in `config.yaml` is a public example template; replace its `/srv/dreamserver` paths and placeholder credentials with values for the target server.

## Server installation

The target server needs Python, `ffmpeg`/`ffprobe`, enough CPU/RAM for the selected Whisper model, and a local Ollama installation if correction or LLM interpretation is enabled.

From the deployed repository:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
```

Copy and edit the repository configuration before starting the service. Do not commit the customized deployment configuration or private VAPID key:

- `config.yaml` controls the server, storage, Whisper, Ollama, digest, correction, maintenance, and push settings.
- `config/mistral_inputs.yaml` contains editable interpretation, Dream Map, and digest prompts.
- `vocabulary.txt` improves transcription of recurring names and places.

Start the API with:

```bash
source .venv/bin/activate
uvicorn api.server:app --host 0.0.0.0 --port 8765
```

The health endpoint is available at `GET /health`. The PWA is served at `/app` when a production build exists at `pwa/dist`.

The checked-in configuration uses placeholders rather than working credentials. Set a private API key and place the service behind HTTPS. The PWA currently connects to `https://<server-host>:8765`, so TLS or a compatible reverse proxy is required for browser recording and push features.

The PWA reads the API key from browser `localStorage` under `api_key`; configure that value to match the server before using a deployment with authentication enabled.

## Using the PWA

Build the PWA from the repository root:

```bash
cd pwa
npm install
npm run build
```

The build output must be available as `~/dreamserver/pwa/dist` in the deployed tree. Open `https://<server-host>:8765/app` in a browser and install it as a PWA if desired.

The PWA supports manual text entries, audio recording, transcript editing, tags, interpretations, weekly digests, statistics, Dream Map browsing, profile settings, vocabulary settings, and push notification registration.

For frontend-only development:

```bash
cd pwa
npm run dev
```

## Development and tests

Install runtime and development dependencies:

```bash
python -m pip install -r requirements-dev.txt
python -m pytest
```

The tests focus on pure prompt, digest, configuration, and profile behavior so they can run without Whisper, Ollama, audio files, or the deployed storage tree. Before a release, also verify the full server in the target environment with `/health`, an audio upload, transcription, and PWA access.

Optional Dream Map accuracy improvements are documented in [SPACY_INSTALL.md](SPACY_INSTALL.md). The service falls back to heuristics when spaCy or its French model is not installed.

