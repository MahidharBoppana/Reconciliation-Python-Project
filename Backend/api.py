
import subprocess
import sys
import uuid
from pathlib import Path

from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from starlette.background import BackgroundTask


def delete_file(path: Path):
    path.unlink(missing_ok=True)

app = FastAPI(title="Payout Reconciliation API")

# Allow React development server to communicate with FastAPI
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

BASE_DIR = Path(__file__).resolve().parent

ENGINE = BASE_DIR / "reconciliation_script.py"
UPLOAD_DIR = BASE_DIR / "uploads"
RESULT_DIR = BASE_DIR / "results"

UPLOAD_DIR.mkdir(exist_ok=True)
RESULT_DIR.mkdir(exist_ok=True)



@app.get("/")
def home():
    return {"message": "Payout Reconciliation API is running"}



@app.post("/api/reconcile")
async def reconcile(
    system_file: UploadFile = File(...),
    bank_file: UploadFile = File(...)
):
    if not system_file.filename.lower().endswith(".csv"):
        raise HTTPException(400, "System file must be CSV")

    if not bank_file.filename.lower().endswith(".csv"):
        raise HTTPException(400, "Bank file must be CSV")

    report_id = str(uuid.uuid4())

    system_path = UPLOAD_DIR / f"{report_id}_system.csv"
    bank_path = UPLOAD_DIR / f"{report_id}_bank.csv"

    output_path = RESULT_DIR / f"{report_id}_reconciliation.xlsx"

    try:
        system_path.write_bytes(await system_file.read())
        bank_path.write_bytes(await bank_file.read())

        command = [
            sys.executable,
            str(ENGINE),
            str(system_path),
            str(bank_path),
            "-o",
            str(output_path),
        ]

        process = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=600
        )

        if process.returncode != 0:
            raise RuntimeError(
                process.stderr or process.stdout or "Reconciliation failed"
            )

        if not output_path.exists():
            raise RuntimeError("Excel report was not generated")

        return FileResponse(
            path=output_path,
            filename="payout_reconciliation.xlsx",
            media_type=(
                "application/vnd.openxmlformats-officedocument."
                "spreadsheetml.sheet"
            ),
            headers={
                "X-Report-ID": report_id
            },
            background=BackgroundTask(delete_file, output_path)
        )

    except subprocess.TimeoutExpired:
        output_path.unlink(missing_ok=True)
        raise HTTPException(504, "Reconciliation timed out")

    except Exception as error:
        output_path.unlink(missing_ok=True)
        raise HTTPException(500, str(error))

    finally:
        system_path.unlink(missing_ok=True)
        bank_path.unlink(missing_ok=True)
        await system_file.close()
        await bank_file.close()

