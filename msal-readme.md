# Instructions for setting up MSAL with the event test harness

The Azure AD MSAL integration for the Producer test harness application
requires some setup in the azure portal.

You need to register the application, configure the redirect URI's and create and assign an app role
for the application.

In the azure portal:

1. create an app registration.
2. create a client secret.
3. create an app role (something like 'admin') and provide a **value** like
   `EventHarness.ReadWrite.All` which represents the scope of access for an administrator of the
   application.
4. assign the app role to a user.

   > Found under enterprise apps > users and groups > add user/group

5. for your service bus instance, assign the 'Azure Service Bus Data Owner' role to the app registration.

   > Found under Service Bus > Access Control (IAM) > Role Assignments.

6. configure the redirect URI's in the application registration. The redirect URI should be the URL
   of the Event Producer Test Harness plus the /token path. i.e.
   `https://producertestharness.azurewebsites.net/token`

   > Found under the authentication section of the app registration

This is all the configuration that is needed from the portal. After deploying the producer test
harness container you will need to provide the details of the app registration as environment variables.

## Environment Variables

| Variable      | Description                                                                                              | Example value                        |
| ------------- | -------------------------------------------------------------------------------------------------------- | ------------------------------------ |
| admin_scope   | The scope of access for an administrator of this application. <br /> as assigned in the App role `value` | EventHarness.ReadWrite.All           |
| tenant_id     | The ID of the azure tenancy in which this application is registered.                                     | a5e26782-03c7-4300-8df6-a88d143cb4e7 |
| client_id     | The client ID from the app registration created for this application.                                    | 825d3aac-a7e3-4421-8c1a-ee7dfcf3635c |
| client_secret | The client secret for the app registration                                                               | 9e3a8816-64d6-4a63-b6a0-112610d57220 |
