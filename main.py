import os
from html import escape
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse
from azure.core.exceptions import ResourceNotFoundError, AzureError
from azure.storage.blob import BlobServiceClient

load_dotenv(dotenv_path=Path(__file__).with_name(".env"))

app = FastAPI(title="API Fichiers Azure", port=8000)

CONTAINER_NAME = "fichiers-api"


def get_container_client(create_if_missing: bool = False):
    connection_string = os.getenv("AZURE_STORAGE_CONNECTION_STRING")

    if not connection_string:
        raise HTTPException(
            status_code=500,
            detail="La variable AZURE_STORAGE_CONNECTION_STRING est manquante."
        )

    try:
        blob_service_client = BlobServiceClient.from_connection_string(connection_string)
        container_client = blob_service_client.get_container_client(CONTAINER_NAME)

        if create_if_missing and not container_client.exists():
            container_client.create_container()

        return container_client

    except AzureError as error:
        raise HTTPException(
            status_code=500,
            detail=f"Erreur de connexion à Azure Blob Storage : {str(error)}"
        )


def upload_to_blob(file: UploadFile) -> dict:
    if not file.filename:
        raise HTTPException(status_code=400, detail="Nom de fichier invalide.")

    try:
        container_client = get_container_client(create_if_missing=True)

        blob_client = container_client.get_blob_client(file.filename)

        blob_client.upload_blob(
            file.file,
            overwrite=True
        )

        return {
            "message": "Fichier envoyé avec succès.",
            "filename": file.filename
        }

    except AzureError as error:
        raise HTTPException(
            status_code=500,
            detail=f"Erreur lors de l'envoi du fichier : {str(error)}"
        )


def delete_blob(filename: str) -> dict:
    if not filename:
        raise HTTPException(status_code=400, detail="Nom de fichier manquant.")

    try:
        container_client = get_container_client()
        blob_client = container_client.get_blob_client(filename)

        blob_client.delete_blob()

        return {
            "message": "Fichier supprimé avec succès.",
            "filename": filename
        }

    except ResourceNotFoundError:
        raise HTTPException(
            status_code=404,
            detail=f"Le fichier '{filename}' est introuvable."
        )

    except AzureError as error:
        raise HTTPException(
            status_code=500,
            detail=f"Erreur lors de la suppression du fichier : {str(error)}"
        )


@app.get("/", response_class=HTMLResponse)
def upload_page(status: str = "", filename: str = "") -> str:
    try:
        container_client = get_container_client(create_if_missing=True)
        files = [blob.name for blob in container_client.list_blobs()]
    except HTTPException:
        files = []

    safe_status = escape(status)
    safe_filename = escape(filename)

    files_html = ""

    if files:
        for file_name in files:
            safe_file_name = escape(file_name)
            files_html += f"""
            <li>
                <span>{safe_file_name}</span>
                <form method="post" action="/delete" style="display:inline;">
                    <input type="hidden" name="filename" value="{safe_file_name}">
                    <button type="submit">Supprimer</button>
                </form>
            </li>
            """
    else:
        files_html = "<li>Aucun fichier trouvé.</li>"

    message_html = ""
    if safe_status:
        message_html = f"""
        <p><strong>{safe_status}</strong> {safe_filename}</p>
        """

    return f"""
    <!DOCTYPE html>
    <html lang="fr">
    <head>
        <meta charset="UTF-8">
        <title>API Fichiers Azure</title>
        <style>
            body {{
                font-family: Arial, sans-serif;
                max-width: 800px;
                margin: 40px auto;
                padding: 20px;
                background-color: #f5f5f5;
            }}

            h1, h2 {{
                color: #333;
            }}

            form {{
                margin-bottom: 20px;
            }}

            input, button {{
                padding: 8px;
                margin: 4px;
            }}

            button {{
                cursor: pointer;
            }}

            ul {{
                background: white;
                padding: 20px;
                border-radius: 8px;
            }}

            li {{
                margin-bottom: 10px;
            }}
        </style>
    </head>
    <body>
        <h1>Gestion des fichiers Azure Blob Storage</h1>

        {message_html}

        <h2>Uploader un fichier</h2>
        <form method="post" action="/" enctype="multipart/form-data">
            <input type="file" name="file" required>
            <button type="submit">Envoyer</button>
        </form>

        <h2>Fichiers présents dans le conteneur</h2>
        <ul>
            {files_html}
        </ul>

        <h2>Routes API disponibles</h2>
        <ul>
            <li><code>GET /files</code> : liste les fichiers</li>
            <li><code>POST /upload</code> : upload un fichier</li>
            <li><code>DELETE /remove?filename=nom_du_fichier</code> : supprime un fichier</li>
        </ul>
    </body>
    </html>
    """


@app.post("/")
def upload_from_root(file: UploadFile = File(...)):
    result = upload_to_blob(file)

    return RedirectResponse(
        url=f"/?status=Fichier uploadé :&filename={result['filename']}",
        status_code=303
    )


@app.get("/files")
def list_files() -> dict:
    try:
        container_client = get_container_client(create_if_missing=True)

        files = [blob.name for blob in container_client.list_blobs()]

        return {
            "container": CONTAINER_NAME,
            "count": len(files),
            "files": files
        }

    except AzureError as error:
        raise HTTPException(
            status_code=500,
            detail=f"Erreur lors de la récupération des fichiers : {str(error)}"
        )


@app.post("/delete")
def delete_from_root(filename: str = Form(...)):
    result = delete_blob(filename)

    return RedirectResponse(
        url=f"/?status=Fichier supprimé :&filename={result['filename']}",
        status_code=303
    )


@app.post("/upload")
def upload_file(file: UploadFile = File(...)) -> dict:
    return upload_to_blob(file)


@app.delete("/remove")
def remove_file(filename: str) -> dict:
    return delete_blob(filename)