# Instructions for setting up MSAL with the event test harness

In the azure portal:

1. create an app registration.
2. create a client secret.
3. assign api permission AppRoleAssignment.ReadWrite.All to the app registration and grant admin
   consent.
4. create an app role (something like 'admin').
5. assign the app role to users / groups. (under enterprise apps / users and groups > add user/group)
6. for your service bus namespace assign the 'Azure Service Bus Data Owner' role to the app registration.

Then you need to set the following environment variables:

| Variable            | Example Value                              | Description                                         |
| ------------------- | ------------------------------------------ | --------------------------------------------------- |
| CLIENT_ID           | "25cf653a-bca1-42d1-be-03-ab6c0a810c10"    | client ID from the registered application           |
| CLIENT_SECRET       | "0jH8Q-Z~xJitEn8tHN-.2gfTycDuIteT7jCFnaio" | client secret value from the registered application |
| TENANT_ID           | "2ffb002c-f987-427d-7cbe-ea3edc4bf7a4"     | your tenant id                                      |
| APP_REGISTRATION_ID | "2509ef84-556d-4203-82a3-e1cfd8efe6dd"     | resource id of the app registration                 |
| ADMIN_APP_ROLE_ID   | "5dcee6ba-f6bb-4ca0-af6b-f542f76358be"     | id for the admin app role                           |
