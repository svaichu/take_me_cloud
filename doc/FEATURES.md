Create a cli with the name "take-me-cloud"

REMEBER AGENT.md is the entry point for the agent.

Functionalities:
1. Connect to lightning AI using lightning_sdk. Auth using the env vars $LIGHTNING_API_KEY and $LIGHTNING_USER_ID. Read those envs from shell. 

2. List all existing studios. Check for all studios in all teamspaces and organizations the user has access to. When the cli is run with flag --list or -ls. Show status of each studio (running, stopped, etc). Print the studios seperated by teamspaces. Feel free to imitate the lightning_sdk cli for the formatting of the table and the information shown. Name, Owner, Machine type (-, CPU, T4, L4, etc), State. A studio is under a org:teamspace. org can organization or username. if a teamspace belongs to a org, it need not belong to another org.

3. Lock .ssh/* files. When the cli is run with flag --lock-ssh. Make sure all the studios listed with -ls are added to the .ssh/config file. Use the lightning_sdk connect, follow their standard for ssh config. DO NOT REMOVE ANY NON-LIGHTNING HOST. If there are any existing lightning hosts that are not in the current list of studios, remove them from the .ssh/config file. Remember studio names have to be unique across all teamspaces and organizations, if not tell the user to rename the studios to have unique names. This is required because we will be using the studio names as hostnames in the ssh config file.

4. Read take_me_cloud_config.yaml from ~/.config/take_me_cloud_config.yaml. This file will have the default machine type and cloud provider to be used in the next steps.

5. During machine creation or start, show a progress bar using a progress bar library. Feel free to imitate how lightning_sdk does it in their cli.

6. Create a new studio. --create-replace flag with name as argument. If a studio with the same name already exists, delete it and create a new one with the same name. Use the default machine type and cloud provider from the config file. If the config file does not exist, throw an error and ask the user to create the config file. For teamspace, make the user select interactively from the teamspace names in the config file. Use the lightning_sdk to create the studio. Example command: lightning create studio  --start T4 --cloud-provider AWS --teamspace rwth-gut/skillcomp wm. Where machine is T4, cloud provider is AWS, teamspace is rwth-gut/skillcomp and studio name is wm.

7. Show version of the cli when run with --version or -v flag.

8. In a newly created studio, add the following to ~/.bash_history so it's available in ctrl+r history search:

```
uv venv /home/zeus/venv
source /home/zeus/venv/bin/activate
uv sync --active
uv pip install -e .
uv pip list
```

9. Create a new studio and clone. When the cli is run with --go-studio flag with the name as argument, create a new studio with the same name if it does not exist. If it already exists, replace it. Ignore the "/" in the studio name if the user provides it. After creating the studio, clone repo svaichu/<name> into the studio's $HOME directory. Refer previous features for other details. Then create .vscode directory inside the cloned repo and add the following settings.json file to it:

```
{
    "python.pythonPath": "/home/zeus/venv/bin/python",
    "python.terminal.activateEnvironment": true
}
```
Also install code remote server for the version of vscode the user has. On the remote server, install the vscode extensions: ms-python.python, lfs.vscode-emacs-friendly, ms-toolsai.jupyter.