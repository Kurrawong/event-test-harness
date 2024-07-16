import os
from enum import Enum

import requests
from azure.identity import ClientSecretCredential, InteractiveBrowserCredential
from azure.servicebus import ServiceBusClient
from dotenv import load_dotenv


load_dotenv()
client_id = os.environ.get("CLIENT_ID")
client_secret = os.environ.get("CLIENT_SECRET")
tenant_id = os.environ.get("TENANT_ID")
app_registration_id = os.environ.get("APP_REGISTRATION_ID")
admin_app_role_id = os.environ.get("ADMIN_APP_ROLE_ID")


class AppRoles(Enum):
    EventHarnessAdmin = admin_app_role_id


def login():
    scopes = "AppRoleAssignment.ReadWrite.All"
    user_credential = InteractiveBrowserCredential(client_id=client_id)
    headers = {"Authorization": f"Bearer {user_credential.get_token(scopes).token}"}
    params = {f"filters": "resourceId eq {app_registration_id}"}
    response = requests.get(
        "https://graph.microsoft.com/v1.0/me/appRoleAssignments", headers=headers
    )
    response.raise_for_status()
    for app_role in response.json().get("value"):
        if app_role.get("appRoleId") == AppRoles.EventHarnessAdmin.value:
            print(
                f"User: {app_role.get('principalDisplayName')}, Logged in and authenticated successfully."
            )
            return
    print("Unauthorized access")


def connect_to_service_bus():
    application_credential = ClientSecretCredential(
        tenant_id,
        client_id,
        client_secret,
        scopes=["https://servicebus.azure.net/.default"],
    )
    servicebus_client = ServiceBusClient(
        fully_qualified_namespace="https://lawson.servicebus.windows.net",
        credential=application_credential,
    )
    return servicebus_client


def main():
    login()
    sb_client = connect_to_service_bus()
    sb_sub_rcvr = sb_client.get_subscription_receiver(
        topic_name="testtopic", subscription_name="testsub"
    )
    print("Peeking messages from service bus...")
    print(sb_sub_rcvr.peek_messages())


if __name__ == "__main__":
    main()
