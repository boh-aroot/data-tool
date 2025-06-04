from fastapi import FastAPI, UploadFile, File, Form
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
import uuid
import os
import csv
import re
from typing import List

app = FastAPI()

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, '..', 'data')
os.makedirs(DATA_DIR, exist_ok=True)

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

    headers = []
    for f in files:
        contents = await f.read()
        path = os.path.join(input_dir, f.filename)
        with open(path, 'wb') as out:
            out.write(contents)
        csv_reader = csv.reader(contents.decode('utf-8').splitlines())
        try:
            headers.append(next(csv_reader))
        except StopIteration:
            headers.append([])

    # store description for later reference
    with open(os.path.join(mig_dir, 'description.txt'), 'w') as desc_file:
        desc_file.write(description)

    # simple validation based on description
    result = validate_description(description, headers)

    return JSONResponse({'migration_id': migration_id,
                        'valid': result['valid'],
                        'message': result['message']})


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
    return {'migration_id': migration_id, 'inputs': inputs, 'description': description}

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
