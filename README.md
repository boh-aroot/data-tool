## Running with Docker

```bash
docker build -t data-tool .
docker run -p 8000:8000 -v $(pwd)/data:/app/data data-tool
```

Then open `http://localhost:8000` in your browser.

## Direct Python execution

If you have Python 3 installed, install the dependencies from `requirements.txt` first:

```bash
pip install -r requirements.txt
```

Then you can start the server with:

```bash
uvicorn backend.main:app --reload
```

Uploaded data will be stored under the `data/` directory with each migration in its own subfolder containing `input/`, `output/`, `description.txt` and `history.json`. When a join command is clearly described, an output CSV is generated automatically and all conversation messages are saved in the history file.

The backend now uses a zero-shot text classifier from the `transformers` library
to decide whether a description is a question or a command. To use a different
model, set the `CLASSIFIER_MODEL` environment variable before starting the
server.

You can click any migration from the main page to open a detail view. The detail
page shows a preview of the first few rows of each uploaded CSV using
DataTables, allows additional input files to be uploaded and provides a chat box
for further questions or commands. All conversation history is stored in
`history.json` under each migration.

The HTML pages include the **Lux** theme from [Bootswatch](https://bootswatch.com/)
to give the interface a clean administrative appearance.