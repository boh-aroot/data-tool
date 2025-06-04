# Data Migration Tool

This project contains a simple web application for experimenting with small data migrations.

## Running with Docker

```bash
docker build -t data-tool .
docker run -p 8000:8000 -v $(pwd)/data:/app/data data-tool
```

Then open `http://localhost:8000` in your browser.

## Direct Python execution


If you have Python 3 and the packages in `requirements.txt` installed you can run:

```bash
uvicorn backend.main:app --reload
```

Uploaded data will be stored under the `data/` directory with each migration in its own subfolder containing `input/`, `output/` and `description.txt`.
