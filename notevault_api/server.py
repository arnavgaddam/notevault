from fastapi import FastAPI, UploadFile, File, BackgroundTasks
from fastapi.responses import FileResponse
import uvicorn
from processing.extractor import PageExtractor
from processing.preprocessors import *
from processing.corner_detector import HoughLineCornerDetector
import tempfile
import uuid
from google.cloud import storage
from google.oauth2 import service_account
import firebase_admin
from firebase_admin import firestore
from firebase_admin import credentials

app = FastAPI()

credentials = service_account.Credentials.from_service_account_file("./notevault-414100-1196f2a9bf0b.json")
project_id = "notevault-414100"
storage_client = storage.Client(credentials=credentials, project=project_id)
bucket = storage_client.get_bucket("notevault-usersaves")
firebase = firebase_admin.initialize_app(credential=firebase_admin.credentials.Certificate("./notevault-firebase-key.json"))
db = firestore.client()





extractor = PageExtractor(
        preprocessors = [RotationCorrector(), Resizer(780), FastDenoiser(strength=7)],
        corner_detector = HoughLineCornerDetector(rho_acc=1, theta_acc=180, thresh=100, output_process=False))


def save_upload(file, process):
    # add process to database
    docref = db.collection("processes").document(f"{process}")
    docref.set({"status": False, "url": None})

    buffer = tempfile.NamedTemporaryFile(delete=False)

    with open(buffer.name, 'wb') as outfile:
        outfile.write(file)

    extracted = extractor(buffer.name)
    buffer.close()
    outfile = tempfile.NamedTemporaryFile(delete=False, suffix=".jpg")
    # write extracted file to temporary location 
    cv2.imwrite(outfile.file.name, extracted)
    # upload processed file to bucket
    blob = bucket.blob(f"scans/{process}")
    blob.upload_from_filename(outfile.file.name)
    # update database with url as blob.public_url


    # TODO: now we need to update the process status to complete and return the storage URL 
    docref.update({"status": True, "url": blob.public_url})



@app.post('/api/scan')
async def predict_image(background_tasks: BackgroundTasks, processID: str = uuid.uuid4(), file: UploadFile = File(...)):
    # add processing task as a background task
    background_tasks.add_task(save_upload, await file.read(), process=processID)
    # return process ID of process
    return({"processID": processID})

@app.get('/api/status')
def poll_status(processID: str):
    docref = db.collection("processes").document(f"{processID}")
    status = docref.get().to_dict()["status"]
    return ({"processID": processID, "status": status})

@app.get('/api/url')
def poll_status(processID: str):
    docref = db.collection("processes").document(f"{processID}")
    url = docref.get().to_dict()["url"]
    return ({"processID": processID, "url": url})


    

if __name__ == "__main__":
    uvicorn.run(app)