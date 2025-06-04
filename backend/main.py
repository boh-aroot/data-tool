from fastapi import FastAPI, UploadFile, File, Form
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
import uuid
import os
import csv
import re
import json
from typing import List
from transformers import pipeline

app = FastAPI()

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, '..', 'data')
os.makedirs(DATA_DIR, exist_ok=True)

# initialize a zero-shot classifier for detecting command vs question
classifier = pipeline(
    "zero-shot-classification",
    model=os.environ.get("CLASSIFIER_MODEL", "facebook/bart-large-mnli"),
)

# candidate labels used for classification
CANDIDATE_LABELS = ["question", "command"]

app.mount('/static', StaticFiles(directory=os.path.join(BASE_DIR, '..', 'frontend')), name='static')

@app.get('/', response_class=HTMLResponse)
def root():
    with open(os.path.join(BASE_DIR, '..', 'frontend', 'index.html')) as f:
        return f.read()

@app.get('/migrations')
def list_migrations():
    migrations = []
    for m in os.listdir(DATA_DIR):
        if os.path.isdir(os.path.join(DATA_DIR, m)):
            migrations.append(m)
    return {'migrations': sorted(migrations)}

@app.post('/migrations')
async def create_migration(files: List[UploadFile] = File(...), description: str = Form(...)):
    migration_id = str(uuid.uuid4())
    mig_dir = os.path.join(DATA_DIR, migration_id)
    input_dir = os.path.join(mig_dir, 'input')
    output_dir = os.path.join(mig_dir, 'output')
    os.makedirs(input_dir)
    os.makedirs(output_dir)

    for f in files:
        contents = await f.read()
        path = os.path.join(input_dir, f.filename)
        with open(path, 'wb') as out:
            out.write(contents)

    # store description for later reference
    with open(os.path.join(mig_dir, 'description.txt'), 'w') as desc_file:
        desc_file.write(description)

    valid, response_text = process_prompt(mig_dir, description)

    return JSONResponse({'migration_id': migration_id,
                        'valid': valid,
                        'message': response_text})


@app.get('/migrations/{migration_id}')
def get_migration(migration_id: str):
    mig_dir = os.path.join(DATA_DIR, migration_id)
    input_dir = os.path.join(mig_dir, 'input')
    if not os.path.exists(mig_dir):
        return JSONResponse({'error': 'migration not found'}, status_code=404)
    inputs = os.listdir(input_dir) if os.path.exists(input_dir) else []
    desc_path = os.path.join(mig_dir, 'description.txt')
    description = ''
    if os.path.exists(desc_path):
        with open(desc_path) as f:
            description = f.read()
    hist_path = os.path.join(mig_dir, 'history.json')
    history = []
    if os.path.exists(hist_path):
        with open(hist_path) as h:
            history = json.load(h)
    return {'migration_id': migration_id, 'inputs': inputs, 'description': description, 'history': history}


@app.get('/migrations/{migration_id}/view', response_class=HTMLResponse)
def view_migration(migration_id: str):
    with open(os.path.join(BASE_DIR, '..', 'frontend', 'detail.html')) as f:
        return f.read()


@app.get('/migrations/{migration_id}/preview')
def preview_file(migration_id: str, file: str):
    path = os.path.join(DATA_DIR, migration_id, 'input', file)
    if not os.path.exists(path):
        return JSONResponse({'error': 'file not found'}, status_code=404)
    rows = []
    headers = []
    with open(path) as f:
        reader = csv.DictReader(f)
        headers = reader.fieldnames or []
        for i, row in enumerate(reader):
            rows.append(row)
            if i >= 4:
                break
    return {'headers': headers, 'rows': rows}


@app.post('/migrations/{migration_id}/files')
async def add_files(migration_id: str, files: List[UploadFile] = File(...)):
    input_dir = os.path.join(DATA_DIR, migration_id, 'input')
    if not os.path.exists(input_dir):
        return JSONResponse({'error': 'migration not found'}, status_code=404)
    for f in files:
        contents = await f.read()
        with open(os.path.join(input_dir, f.filename), 'wb') as out:
            out.write(contents)
    return {'status': 'ok'}


@app.post('/migrations/{migration_id}/prompt')
async def prompt_migration(migration_id: str, prompt: str = Form(...)):
    mig_dir = os.path.join(DATA_DIR, migration_id)
    if not os.path.exists(mig_dir):
        return JSONResponse({'error': 'migration not found'}, status_code=404)
    valid, response_text = process_prompt(mig_dir, prompt)
    return {'valid': valid, 'message': response_text}

def validate_description(desc: str, headers: List[List[str]]):
    all_headers = {h for header in headers for h in header}
    join_match = re.search(r"join.*on column (\w+) and (\w+)", desc, re.IGNORECASE)
    output_match = re.search(r"have cols ([\w, ]+)", desc, re.IGNORECASE)

    if join_match:
        left_col, right_col = join_match.group(1), join_match.group(2)
        if left_col not in headers[0] or right_col not in headers[-1]:
            return {'valid': False, 'message': f'Join columns {left_col}, {right_col} not found in inputs'}
    if output_match:
        cols = [c.strip() for c in output_match.group(1).split(',')]
        missing = [c for c in cols if c not in all_headers]
        if missing:
            return {'valid': False, 'message': f'Output columns {missing} not found in inputs'}
    return {'valid': True, 'message': 'Description looks valid'}



def classify_prompt(prompt: str) -> str:
    """Use a zero-shot classifier to label the prompt as question or command."""
    result = classifier(prompt, CANDIDATE_LABELS)
    return result['labels'][0]


def answer_question(prompt: str) -> str:
    """Return a canned answer for demonstration purposes."""
    if 'column' in prompt.lower():
        return 'Please refer to the uploaded CSV headers for column details.'
    return 'This system currently only supports simple join commands.'


def perform_transformation(desc: str, input_dir: str, output_dir: str):
    files = sorted(os.listdir(input_dir))
    if len(files) < 2:
        return None, 'Need at least two input files for transformation.'

    left_path = os.path.join(input_dir, files[0])
    right_path = os.path.join(input_dir, files[1])

    join_match = re.search(r"join.*on column (\w+) and (\w+)", desc, re.IGNORECASE)
    output_match = re.search(r"have cols ([\w, ]+)", desc, re.IGNORECASE)

    if not (join_match and output_match):
        return None, 'Could not understand command. Please clarify.'

    left_col, right_col = join_match.group(1), join_match.group(2)
    out_cols = [c.strip() for c in output_match.group(1).split(',')]

    with open(left_path) as f1, open(right_path) as f2:
        r1 = csv.DictReader(f1)
        r2 = csv.DictReader(f2)
        table1 = {row[left_col]: row for row in r1 if left_col in row}
        rows = []
        for row in r2:
            key = row.get(right_col)
            if key in table1:
                merged = {**table1[key], **row}
                rows.append({c: merged.get(c, '') for c in out_cols})

    if not rows:
        return None, 'No rows joined; check your join columns.'

    out_file = os.path.join(output_dir, 'result.csv')
    with open(out_file, 'w', newline='') as out:
        w = csv.DictWriter(out, fieldnames=out_cols)
        w.writeheader()
        for row in rows:
            w.writerow(row)

    return out_file, f'Output file generated at {out_file}.'


def process_prompt(mig_dir: str, prompt: str):
    """Handle a new user prompt and update history."""
    input_dir = os.path.join(mig_dir, 'input')
    output_dir = os.path.join(mig_dir, 'output')

    headers = []
    for fname in os.listdir(input_dir):
        with open(os.path.join(input_dir, fname)) as f:
            r = csv.reader(f)
            try:
                headers.append(next(r))
            except StopIteration:
                headers.append([])

    result = validate_description(prompt, headers)

    history_path = os.path.join(mig_dir, 'history.json')
    history = []
    if os.path.exists(history_path):
        with open(history_path) as h:
            history = json.load(h)

    history.append({'role': 'user', 'content': prompt})

    response_text = ''
    prompt_type = classify_prompt(prompt)
    if prompt_type == 'question':
        response_text = answer_question(prompt)
        history.append({'role': 'assistant', 'content': response_text})
    else:
        if result['valid']:
            _, response_text = perform_transformation(prompt, input_dir, output_dir)
            history.append({'role': 'assistant', 'content': response_text})
        else:
            response_text = result['message'] + ' Please clarify.'
            history.append({'role': 'assistant', 'content': response_text})

    with open(history_path, 'w') as h:
        json.dump(history, h, indent=2)

    return result['valid'], response_text
