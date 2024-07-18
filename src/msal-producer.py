import logging
from html import escape
import os
import sys
from enum import Enum
from pathlib import Path

import msal
import requests
import uvicorn
from azure.identity import ClientSecretCredential
from azure.servicebus import ServiceBusClient, ServiceBusMessage, ServiceBusReceiver
from azure.servicebus.exceptions import ServiceBusError
from dotenv import load_dotenv
from fastapi import Depends, FastAPI, Form, Security
from fastapi.requests import Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.security import SecurityScopes
from fastapi.templating import Jinja2Templates
from jinja2 import Template

logger = logging.Logger(__name__)
logger.setLevel(logging.DEBUG)
logger.addHandler(logging.StreamHandler(sys.stdout))

app = FastAPI()
templates = Jinja2Templates(directory=Path(__file__).parent / "templates")

load_dotenv()
client_id = os.environ.get("CLIENT_ID")
client_secret = os.environ.get("CLIENT_SECRET")
tenant_id = os.environ.get("TENANT_ID")
admin_app_role_id = os.environ.get("ADMIN_APP_ROLE_ID")
host_domain = os.environ.get("HOST_DOMAIN")

# Use MSAL to authenticate the user logging into the application
msal_app = msal.ConfidentialClientApplication(
    client_id=client_id,
    authority="https://login.microsoftonline.com/" + tenant_id,
)

session: dict = dict()


class AppRole(Enum):
    EventHarnessAdmin = admin_app_role_id


class AuthMethod(Enum):
    AAD = "1"
    SAS = "2"


async def get_sb_client(
    auth_method: AuthMethod, namespace: str | None, conn_str: str | None
) -> ServiceBusClient:
    if auth_method == AuthMethod.AAD:
        credential = ClientSecretCredential(
            tenant_id,
            client_id,
            client_secret,
            scopes=["https://servicebus.azure.net/.default"],
        )
        sb_client = ServiceBusClient(
            fully_qualified_namespace=f"https://{namespace}.servicebus.windows.net",
            credential=credential,
        )
    elif auth_method == AuthMethod.SAS:
        sb_client = ServiceBusClient.from_connection_string(conn_str=conn_str)
    else:
        raise ValueError(f"Invalid authentication method: {auth_method}")
    return sb_client


async def get_token() -> str | None:
    scopes = ["AppRoleAssignment.ReadWrite.All"]
    accounts = msal_app.get_accounts()
    result = None
    if accounts:
        chosen = accounts[0]  # default to first account if there are multiple
        result = msal_app.acquire_token_silent(scopes=scopes, account=chosen)
    if not result:
        flow = msal_app.initiate_auth_code_flow(
            scopes=scopes, redirect_uri=f"{host_domain}/token"
        )
        if "error" in flow:
            logging.DEBUG(flow.get("error"))
        session["auth_flow"] = flow
        return None
    token = result["access_token"]
    return token


@app.get("/token", response_class=RedirectResponse)
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


async def get_username(token: str) -> str:
    if not token:
        return None
    headers = {"Authorization": f"Bearer {token}"}
    response = requests.get(
        "https://graph.microsoft.com/v1.0/me",
        headers=headers,
    )
    response.raise_for_status()
    return response.json().get("displayName")


async def get_approle_ids(token: str) -> list[str]:
    if not token:
        return None
    headers = {"Authorization": f"Bearer {token}"}
    response = requests.get(
        "https://graph.microsoft.com/v1.0/me/appRoleAssignments",
        headers=headers,
    )
    response.raise_for_status()
    ids = [approle.get("appRoleId") for approle in response.json().get("value")]
    return ids


async def is_authorized(
    scopes: SecurityScopes, token: str = Depends(get_token)
) -> bool:
    """Check if a user is authorized against a set of scopes

    :param scopes: A list of scopes (App Role ID's)
    :param token: an Oauth2 token
    :return: True or False
    """
    # user is not authenticated
    if not token:
        return False
    # user is authenticated and no scopes required
    if not scopes:
        return True
    approle_ids = await get_approle_ids(token)
    # scopes are required but no approles are assigned to the user
    if not approle_ids:
        return False
    for scope in scopes.scopes:
        # required scope is not assigned to the user
        if scope not in approle_ids:
            return False
    # all required scopes are assigned to the user
    return True


@app.get("/")
async def index(
    request: Request,
    token: str = Depends(get_token),
    authorized: bool = Security(
        is_authorized, scopes=[AppRole.EventHarnessAdmin.value]
    ),
):
    authenticated = True if token else False
    auth_uri = session.get("auth_flow").get("auth_uri")
    username = await get_username(token)
    if authenticated and not authorized:
        return HTMLResponse(content="error: Unauthorized access", status_code=401)
    return templates.TemplateResponse(
        "producer-index.html",
        {
            "request": request,
            "authenticated": authenticated,
            "auth_uri": auth_uri,
            "username": username,
            "client_id": client_id[:9] + "..." + client_id[-9:],
            "client_secret": client_secret[:9] + "..." + client_secret[-9:],
            "tenant_id": tenant_id[:9] + "..." + tenant_id[-9:],
            "admin_app_role_id": admin_app_role_id,
            "host_domain": host_domain
        },
    )


@app.post("/sb-msg")
async def sb_msg(
    authorized: bool = Security(
        is_authorized, scopes=[AppRole.EventHarnessAdmin.value]
    ),
    sb_auth_method: AuthMethod = Form(),
    sb_namespace: str = Form(default=""),
    sb_conn_str: str = Form(default=""),
    sb_topic: str = Form(),
    msg_subject: str = Form(),
    msg_body: str = Form(),
):
    if not authorized:
        return HTMLResponse(content="error: Unauthorized access", status_code=401)
    if sb_auth_method == AuthMethod.AAD and not sb_namespace:
        return HTMLResponse(
            status_code=400, content="Namespace required for Azure AD authentication"
        )
    if sb_auth_method == AuthMethod.SAS and not sb_conn_str:
        return HTMLResponse(
            status_code=400,
            content="Connection string required for Shared Access Key authentication",
        )
    sb_client = await get_sb_client(
        auth_method=sb_auth_method, namespace=sb_namespace, conn_str=sb_conn_str
    )
    msg = ServiceBusMessage(subject=msg_subject, body=msg_body)
    try:
        sb_topic_sender = sb_client.get_topic_sender(topic_name=sb_topic)
        sb_topic_sender.send_messages(message=msg)
        sb_client.close()
    except (ServiceBusError, ValueError) as e:
        return JSONResponse(
            status_code=500, content={"error": str(type(e)), "message": e.args[0]}
        )
    return JSONResponse(
        status_code=200,
        content={
            "auth_method": sb_auth_method.name,
            "topic": sb_topic,
            "subject": msg_subject,
            "body": escape(msg_body),
            "status": "Success",
        },
    )


@app.post("/query")
async def query(
    authorized: bool = Security(
        is_authorized, scopes=[AppRole.EventHarnessAdmin.value]
    ),
    sparql_endpoint: str = Form(),
    query_str: str = Form(),
):
    if not authorized:
        return HTMLResponse(content="error: Unauthorized access", status_code=401)
    response = requests.get(
        sparql_endpoint,
        params={"query": query_str},
        headers={"Accept": "application/json"},
    )
    response.raise_for_status()
    return JSONResponse(status_code=200, content=response.json())


if __name__ == "__main__":
    uvicorn.run("msal-producer:app", host="127.0.0.1", port=8000, reload=True)
