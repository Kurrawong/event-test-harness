import logging
import os
import sys

import msal
import requests
import uvicorn
from enum import Enum
from dotenv import load_dotenv
from fastapi import Depends, FastAPI, Security
from fastapi.requests import Request
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse

logger = logging.Logger("msalfapi")
logger.setLevel(logging.DEBUG)
logger.addHandler(logging.StreamHandler(sys.stdout))

app = FastAPI()

load_dotenv()
client_id = os.environ.get("CLIENT_ID")
tenant_id = os.environ.get("TENANT_ID")
admin_app_role_id = os.environ.get("ADMIN_APP_ROLE_ID")


class AppRoles(Enum):
    EventHarnessAdmin = admin_app_role_id


msal_app = msal.ConfidentialClientApplication(
    client_id=client_id,
    authority="https://login.microsoftonline.com/" + tenant_id,
)

session: dict = dict()


async def get_token() -> str | None:
    scopes = ["AppRoleAssignment.ReadWrite.All"]
    accounts = msal_app.get_accounts()
    result = None
    if accounts:
        chosen = accounts[0]  # default to first account if there are multiple
        result = msal_app.acquire_token_silent(scopes=scopes, account=chosen)
    if not result:
        flow = msal_app.initiate_auth_code_flow(
            scopes=scopes, redirect_uri="http://localhost:8000/token"
        )
        if "error" in flow:
            logging.DEBUG(flow.get("error"))
        session["auth_flow"] = flow
        return None
    token = result["access_token"]
    return token


@app.get("/login")
async def login():
    content = f"""
    <a href="{session['auth_flow'].get('auth_uri')}">Login</a>
    """
    return HTMLResponse(content=content)


@app.get("/token")
async def token(request: Request):
    token = None
    try:
        result = msal_app.acquire_token_by_auth_code_flow(
            session.get("auth_flow"), dict(request.query_params)
        )
        if "access_token" in result:
            token = result["access_token"]
        else:
            logger.debug(result.get("error"))
    except ValueError as e:
        logger.debug(e)
        pass
    return RedirectResponse("/")


async def get_username(token: str):
    headers = {"Authorization": f"Bearer {token}"}
    response = requests.get(
        "https://graph.microsoft.com/v1.0/me",
        headers=headers,
    )
    response.raise_for_status()
    return response.json().get("displayName")


async def get_approles(token: str):
    headers = {"Authorization": f"Bearer {token}"}
    response = requests.get(
        "https://graph.microsoft.com/v1.0/me/appRoleAssignments",
        headers=headers,
    )
    response.raise_for_status()
    return response.json().get("value")


@app.get("/")
async def root(token: str = Depends(get_token)):
    if not token:
        return RedirectResponse("/login")
    username = await get_username(token)
    approles = await get_approles(token)
    if AppRoles.EventHarnessAdmin.value not in [role.get("appRoleId") for role in approles]:
        return JSONResponse(content={"error": "Unauthorized access"}, status_code=403)
    return {"username": username, "approles": approles}


if __name__ == "__main__":
    uvicorn.run("msalfapi:app", host="127.0.0.1", port=8000, reload=True)
