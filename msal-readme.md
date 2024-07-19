# Instructions for setting up MSAL with the event test harness

The Azure AD MSAL integration for the Producer test harness application
requires some setup in the azure portal.

You need to register the application, configure the redirect URI's and create and assign an app role
for the application.

In the azure portal:

1. create an app registration.
2. create a client secret.
3. create an app role (something like 'admin') and provide a **value** like
   `EventHarness.ReadWrite.All`
4. assign the app role to a user.

   > Found under enterprise apps > users and groups > add user/group

5. for your service bus instance, assign the 'Azure Service Bus Data Owner' role to the app registration.

   > Found under Service Bus > Access Control (IAM) > Role Assignments.
