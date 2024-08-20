import logging
import os
import sys
import time
from enum import Enum
from html import escape
from pathlib import Path
from typing import Annotated
from uuid import uuid4

import msal
import requests
import starlette.status as status
import uvicorn
from azure.identity import ClientSecretCredential
from azure.servicebus import ServiceBusClient, ServiceBusMessage
from azure.servicebus.exceptions import ServiceBusError
from dotenv import load_dotenv
from fastapi import Depends, FastAPI, Form, Security
from fastapi.requests import Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.security import SecurityScopes
from fastapi.templating import Jinja2Templates
from requests.exceptions import ConnectionError, HTTPError
from starlette.middleware.sessions import SessionMiddleware

logger = logging.Logger(__name__)
logger.setLevel(logging.DEBUG)
logger.addHandler(logging.StreamHandler(sys.stdout))

app = FastAPI()
app.add_middleware(SessionMiddleware, secret_key="super secret key")
templates = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))

load_dotenv()
client_id = os.environ.get("CLIENT_ID", "")
client_secret = os.environ.get("CLIENT_SECRET", "")
tenant_id = os.environ.get("TENANT_ID", "")
admin_scope = os.environ.get("ADMIN_SCOPE", "")

# Use MSAL to authenticate the user logging into the application
msal_app = msal.ConfidentialClientApplication(
    client_id=client_id,
    client_credential=client_secret,
    authority="https://login.microsoftonline.com/" + tenant_id,
)

sessions: dict = dict()
auth_flows: dict = dict()


class Scopes(Enum):
    UserRead = "User.Read"
    EventHarnessAdmin = admin_scope


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


async def get_user(request: Request) -> dict:
    session_id = request.session.get("id")
    if session_id:
        user = sessions.get(session_id)
        if user:
            accounts = msal_app.get_accounts(username=user.get("preferred_username"))
            if accounts:
                chosen = accounts[0]
                result = msal_app.acquire_token_silent(
                    scopes=[Scopes.UserRead.value], account=chosen
                )
                if result:
                    return user
    return {}


async def is_authorized(
    request: Request, scopes: SecurityScopes, user: dict = Depends(get_user)
) -> bool:
    if not user:
        return False
    roles = user["id_token_claims"].get("roles", {})
    for scope in scopes.scopes:
        if scope not in roles:
            return False
    return True


@app.get("/login")
async def login(request: Request):
    scopes = [Scopes.UserRead.value]
    flow = msal_app.initiate_auth_code_flow(
        scopes=scopes,
        redirect_uri="https://" + str(request.base_url.hostname) + "/token",
        response_mode="form_post",
    )
    if "error" in flow:
        return JSONResponse(status_code=500, content={"error": flow.get("error")})
    auth_flows[flow["state"]] = flow
    return RedirectResponse(flow["auth_uri"])


@app.get("/logout")
async def logout(request: Request, user: dict = Depends(get_user)) -> RedirectResponse:
    sessions.pop(request.session["id"])
    request.session.clear()
    logout_url = f"https://login.microsoftonline.com/{tenant_id}/oauth2/v2.0/logout?post_logout_redirect_uri={request.base_url}"
    return RedirectResponse(url=logout_url)


@app.post("/token", response_class=RedirectResponse)
async def token(
    request: Request,
):
    form = await request.form()
    state = form.get("state")
    try:
        result = msal_app.acquire_token_by_auth_code_flow(
            auth_flows.get(state), dict(form)
        )
        access_token = result.get("access_token")
        if not access_token:
            logger.debug(result.get("error"))
        else:
            sessions[state] = result
            request.session["id"] = state
    except ValueError as e:
        logger.debug(e)
        pass
    return RedirectResponse("/", status_code=status.HTTP_302_FOUND)


@app.get("/")
async def index(
    request: Request,
    user: dict = Depends(get_user),
    authorized: bool = Security(is_authorized, scopes=[Scopes.EventHarnessAdmin.value]),
):
    logger.debug(f"session id: {request.session.get('id')}")
    return templates.TemplateResponse(
        "producer-index.html",
        {
            "request": request,
            "user": user,
            "authorized": authorized,
            "client_id": client_id[:9] + "..." + client_id[-9:],
            "client_secret": client_secret[:9] + "..." + client_secret[-9:],
            "tenant_id": tenant_id[:9] + "..." + tenant_id[-9:],
            "admin_scope": admin_scope,
        },
    )


@app.post("/sb-msg")
async def sb_msg(
    request: Request,
    authorized: bool = Security(is_authorized, scopes=[Scopes.EventHarnessAdmin.value]),
    sb_auth_method: AuthMethod = Form(),
    sb_namespace: str = Form(default=""),
    sb_conn_str: str = Form(default=""),
    sb_topic: str = Form(),
    msg_subject: str = Form(),
    msg_body: str = Form(),
):
    if not authorized:
        return JSONResponse(status_code=status.HTTP_401_UNAUTHORIZED, content="Unauthorized")
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
    request: Request,
    authorized: bool = Security(is_authorized, scopes=[Scopes.EventHarnessAdmin.value]),
    sparql_endpoint: str = Form(),
    query_str: str = Form(),
):
    if not authorized:
        return JSONResponse(status_code=status.HTTP_401_UNAUTHORIZED, content="Unauthorized")
    try:
        response = requests.get(
            sparql_endpoint,
            params={"query": query_str},
            headers={"Accept": "application/json"},
        )
        response.raise_for_status()
    except ConnectionError as e:
        return JSONResponse(
            status_code=500,
            content={"error": str(type(e)), "message": str(e.args[0])},
        )
    except HTTPError as e:
        return JSONResponse(
            status_code=response.status_code,
            content={"error": str(type(e)), "message": str(e.args[0])},
        )

    return JSONResponse(status_code=response.status_code, content=response.json())


if __name__ == "__main__":
    uvicorn.run("producer:app", host="127.0.0.1", port=8000, reload=True)
