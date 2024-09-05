import logging
import os
import sys
from enum import Enum
from html import escape
from pathlib import Path

import msal
import requests
import starlette.status as status
import uvicorn
from azure.identity import DefaultAzureCredential
from azure.servicebus import ServiceBusClient, ServiceBusMessage, TransportType
from azure.servicebus.exceptions import ServiceBusError
from dotenv import load_dotenv
from fastapi import Depends, FastAPI, Form, Security
from fastapi.requests import Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
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
group_id = os.environ.get("GROUP_ID", "")
local_dev = os.environ.get("LOCAL_DEV", "")

# Use MSAL to authenticate the user logging into the application
msal_app = msal.ConfidentialClientApplication(
    client_id=client_id,
    client_credential=client_secret,
    authority="https://login.microsoftonline.com/" + tenant_id,
)

sessions: dict = dict()
auth_flows: dict = dict()


class AuthMethod(Enum):
    SMI = "1"  # conect using the system managed identity of the web app
    SAS = "2"  # connect using a shared access key


async def get_sb_client(
    auth_method: AuthMethod, namespace: str | None, conn_str: str | None
) -> ServiceBusClient:
    if auth_method == AuthMethod.SMI:
        credential = DefaultAzureCredential()
        sb_client = ServiceBusClient(
            fully_qualified_namespace=f"https://{namespace}.servicebus.windows.net",
            credential=credential,
            transport_type=TransportType.AmqpOverWebsocket,
        )
    elif auth_method == AuthMethod.SAS:
        sb_client = ServiceBusClient.from_connection_string(
            conn_str=conn_str, transport_type=TransportType.AmqpOverWebsocket
        )
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
                    scopes=["User.Read"], account=chosen
                )
                if result:
                    return user
    return {}


async def is_authorized(request: Request, user: dict = Depends(get_user)) -> bool:
    if user:
        groups = user["id_token_claims"].get("groups", [])
        if group_id in groups:
            return True
    return False


@app.get("/login")
async def login(request: Request):
    scopes = ["User.Read"]
    if not local_dev:
        redirect_uri = str(request.base_url).replace("http", "https") + "token"
    else:
        redirect_uri = "http://localhost:8000/token"
    flow = msal_app.initiate_auth_code_flow(
        scopes=scopes,
        redirect_uri=redirect_uri,
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
    authorized: bool = Security(is_authorized),
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
            "group_id": group_id,
        },
    )


@app.post("/sb-msg")
async def sb_msg(
    request: Request,
    authorized: bool = Security(is_authorized),
    sb_auth_method: AuthMethod = Form(),
    sb_namespace: str = Form(default=""),
    sb_conn_str: str = Form(default=""),
    sb_topic: str = Form(),
    msg_subject: str = Form(),
    msg_body: str = Form(),
):
    if not authorized:
        return JSONResponse(
            status_code=status.HTTP_401_UNAUTHORIZED, content="Unauthorized"
        )
    if sb_auth_method == AuthMethod.SMI and not sb_namespace:
        return HTMLResponse(
            status_code=400,
            content="Namespace required for authentication with System Managed Identity",
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
    authorized: bool = Security(is_authorized),
    sparql_endpoint: str = Form(),
    query_str: str = Form(),
):
    if not authorized:
        return JSONResponse(
            status_code=status.HTTP_401_UNAUTHORIZED, content="Unauthorized"
        )
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
