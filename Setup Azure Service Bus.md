## Stand up Event Test Harness web app on Azure

The Event Test Harness (evt) container image can be built from the source at [github](https://github.com/Kurrawong/event-test-harness). Once you have the image you need to add it to your Azure Container Registry repository. Then you are ready to deploy it as a Web App on ASE.

- In the Azure portal search for Web App.
- Select Web App from the list of Marketplace results.
- Configure the Web App for Event Test Harness by setting:
  - Resource Group
  - Name
  - Publish (Container)
  - Operating System (Linux)
  - Region
- Click 'Container' from the tab menu at the top to go to the container settings.
- Set the container settings to:
  - Image source (Azure Container Registry),
  - Registry (the registry you added the Event Test Harness image to)
  - Image (the Event Test Harness image)
  - Tag (the latest tag or whatever tag you added to the image)
- Click 'Review + create'
- Click 'Create'
- Once the deployment has finished click 'Go to resource'
- Then from the navigation menu on the left, under Settings, click 'Environment variables'
  - You will need to setup the environment settings required for Service Bus as per the main README.md file


